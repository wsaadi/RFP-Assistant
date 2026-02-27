"""Anonymization service using GLiNER for NER-based pseudonymization."""
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.project import AnonymizationMapping, EntityType

logger = logging.getLogger(__name__)


# Entity labels GLiNER will search for
# Keep detection focused on truly sensitive data to avoid over-anonymization:
# names, companies, emails, addresses, project/RFP codes.
GLINER_LABELS = [
    "person",
    "organization",
    "company",
    "email address",
    "address",
    "project code",
]

# Mapping from GLiNER labels to our entity types
LABEL_TO_ENTITY_TYPE = {
    "person": EntityType.PERSON,
    "organization": EntityType.COMPANY,
    "company": EntityType.COMPANY,
    "email address": EntityType.EMAIL,
    "address": EntityType.ADDRESS,
    "project code": EntityType.PROJECT_CODE,
}

# Prefixes for anonymized placeholders
ENTITY_PREFIXES = {
    EntityType.COMPANY: "ENTREPRISE",
    EntityType.PERSON: "PERSONNE",
    EntityType.EMAIL: "EMAIL",
    EntityType.PHONE: "TELEPHONE",
    EntityType.ADDRESS: "ADRESSE",
    EntityType.PROJECT_CODE: "CODE_PROJET",
    EntityType.RFP_CODE: "CODE_AO",
    EntityType.SOLUTION_NAME: "SOLUTION",
    EntityType.DATE: "DATE",
    EntityType.AMOUNT: "MONTANT",
    EntityType.OTHER: "ENTITE",
}

# Reverse mapping: prefix string → EntityType
PREFIX_TO_ENTITY_TYPE = {v: k for k, v in ENTITY_PREFIXES.items()}

# Regex patterns for entities GLiNER might miss
REGEX_PATTERNS = {
    EntityType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
}


class AnonymizationService:
    """Service for anonymizing/pseudonymizing sensitive content."""

    _model = None
    _model_load_failed = False  # sentinel to avoid retrying a broken model
    _device = "cpu"  # "cpu", "mps" (Apple Silicon), or "cuda"
    _using_onnx = False

    @classmethod
    def _detect_device(cls) -> str:
        """Pick the best available device for inference."""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    @classmethod
    def _get_model(cls):
        """Lazy-load the GLiNER model. Returns None if unavailable."""
        if cls._model is not None:
            return cls._model
        if cls._model_load_failed:
            return None
        try:
            from gliner import GLiNER
            from ..config import settings

            cls._device = cls._detect_device()
            use_onnx = settings.gliner_use_onnx

            if use_onnx:
                cls._model = cls._load_onnx_model(GLiNER, settings.gliner_model)
            else:
                logger.info("Loading GLiNER model: %s on device: %s ...", settings.gliner_model, cls._device)
                cls._model = GLiNER.from_pretrained(settings.gliner_model)
                if cls._device != "cpu":
                    cls._model = cls._model.to(cls._device)
                logger.info("GLiNER model loaded successfully on %s", cls._device)
        except Exception as e:
            logger.error("Could not load GLiNER model: %s", e, exc_info=True)
            cls._model = None
            cls._model_load_failed = True
        return cls._model

    @classmethod
    def _load_onnx_model(cls, GLiNER, model_name: str):
        """Load GLiNER as ONNX, converting from PyTorch on first run."""
        from huggingface_hub import hf_hub_download, HfFileSystemResolvedPath
        import pathlib

        # Find the cached model snapshot dir
        try:
            # hf_hub_download returns the path to a file; we just need the snapshot dir
            config_path = hf_hub_download(model_name, "gliner_config.json")
            snapshot_dir = pathlib.Path(config_path).parent
        except Exception:
            # Fallback: load PyTorch model to trigger download, then find dir
            logger.info("Downloading model %s ...", model_name)
            tmp_model = GLiNER.from_pretrained(model_name)
            snapshot_dir = None
            # Try common HF cache locations
            import glob
            hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
            pattern = os.path.join(hf_home, "hub", f"models--{model_name.replace('/', '--')}", "snapshots", "*")
            dirs = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            if dirs:
                snapshot_dir = pathlib.Path(dirs[0])
            if not snapshot_dir:
                logger.warning("Could not find snapshot dir, falling back to PyTorch")
                return tmp_model

        onnx_path = snapshot_dir / "model.onnx"

        if not onnx_path.exists():
            logger.info("ONNX model not found at %s, converting from PyTorch (one-time)...", onnx_path)
            # Load PyTorch model to convert
            pt_model = GLiNER.from_pretrained(model_name)
            try:
                from gliner.model import convert_to_onnx
                convert_to_onnx(pt_model.model, str(snapshot_dir))
                logger.info("ONNX conversion complete: %s", onnx_path)
            except (ImportError, AttributeError):
                # Fallback: use save_pretrained with onnx flag if available
                try:
                    pt_model.save_pretrained(str(snapshot_dir), save_onnx=True)
                    logger.info("ONNX export via save_pretrained complete")
                except Exception as e2:
                    logger.warning("Could not convert to ONNX (%s), falling back to PyTorch", e2)
                    return pt_model

        logger.info("Loading GLiNER ONNX model from %s ...", snapshot_dir)
        model = GLiNER.from_pretrained(
            str(snapshot_dir),
            load_onnx_model=True,
            load_tokenizer=True,
        )
        cls._using_onnx = True
        logger.info("GLiNER ONNX model loaded successfully")
        return model

    @classmethod
    def is_ner_available(cls) -> bool:
        """Check if the NER model is loaded and available."""
        return cls._get_model() is not None

    @staticmethod
    async def get_mappings(
        db: AsyncSession, project_id: uuid.UUID
    ) -> Dict[str, AnonymizationMapping]:
        """Get all anonymization mappings for a project, keyed by original_value."""
        result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.is_active == True)
        )
        mappings = result.scalars().all()
        return {m.original_value: m for m in mappings}

    @staticmethod
    async def get_mappings_by_placeholder(
        db: AsyncSession, project_id: uuid.UUID
    ) -> Dict[str, str]:
        """Get mapping from anonymized placeholder to original value."""
        result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.is_active == True)
        )
        mappings = result.scalars().all()
        return {m.anonymized_value: m.original_value for m in mappings}

    # Max words per segment for GLiNER (DeBERTa tokenizer, max_position=384 tokens)
    # French/technical text can reach ~2.5 tokens/word, so 150 words ≈ 375 tokens
    _GLINER_SEGMENT_WORDS = 150
    _GLINER_OVERLAP_WORDS = 20
    # Confidence threshold for GLiNER predictions.
    # 0.3 gives better recall on short entities (acronyms like EDF, SNCF) while
    # keeping acceptable precision.
    _GLINER_THRESHOLD = 0.3

    @classmethod
    def _predict_on_segments(cls, model, text: str) -> List[Tuple[str, str, int, int]]:
        """Run GLiNER prediction on overlapping text segments to avoid truncation."""
        # Build word boundary list: [(word_start_char, word_end_char), ...]
        word_spans = [(m.start(), m.end()) for m in re.finditer(r'\S+', text)]

        if len(word_spans) <= cls._GLINER_SEGMENT_WORDS:
            predictions = model.predict_entities(text, GLINER_LABELS, threshold=cls._GLINER_THRESHOLD)
            return [
                (p["text"], p["label"], p["start"], p["end"])
                for p in predictions
            ]

        entities = []
        seen = set()
        step = cls._GLINER_SEGMENT_WORDS - cls._GLINER_OVERLAP_WORDS

        for i in range(0, len(word_spans), step):
            span_slice = word_spans[i: i + cls._GLINER_SEGMENT_WORDS]
            seg_char_start = span_slice[0][0]
            seg_char_end = span_slice[-1][1]
            segment_text = text[seg_char_start:seg_char_end]

            predictions = model.predict_entities(segment_text, GLINER_LABELS, threshold=cls._GLINER_THRESHOLD)
            for pred in predictions:
                abs_start = seg_char_start + pred["start"]
                abs_end = seg_char_start + pred["end"]
                key = (pred["text"], abs_start)
                if key not in seen:
                    seen.add(key)
                    entities.append((pred["text"], pred["label"], abs_start, abs_end))

        return entities

    @classmethod
    def _batch_detect_entities(
        cls,
        texts: List[str],
        progress_callback=None,
    ) -> List[List[Tuple[str, str, int, int]]]:
        """Detect entities across multiple texts using GLiNER inference.

        On CPU: uses ThreadPoolExecutor for parallel processing (PyTorch
        releases the GIL during tensor ops so threads give real speedup).
        On GPU/MPS: single-threaded (GPU inference is not thread-safe but
        is fast enough that parallelism isn't needed).

        Args:
            texts: List of texts to analyze.
            progress_callback: Optional callable(current_idx, total) called
                as texts are processed, for progress reporting.
        """
        results: List[List[Tuple[str, str, int, int]]] = [[] for _ in texts]
        seen: List[set] = [set() for _ in texts]

        model = cls._get_model()
        # GPU is not thread-safe → 1 worker.
        # ONNX Runtime handles its own parallelism internally → 1 worker.
        # CPU PyTorch benefits from thread-level parallelism → multiple workers.
        if cls._device != "cpu" or cls._using_onnx:
            n_workers = 1
        else:
            n_workers = min(os.cpu_count() or 4, 4)
        logger.debug("[batch_detect] GLiNER on %s (onnx=%s), processing %d texts with %d workers",
                     cls._device, cls._using_onnx, len(texts), n_workers)

        if model is not None:
            done_count = 0

            def _process_one(text_idx: int, text: str):
                """Run prediction for a single text (called from thread)."""
                return text_idx, cls._predict_on_segments(model, text)

            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                futures = {
                    pool.submit(_process_one, idx, text): idx
                    for idx, text in enumerate(texts)
                }
                for future in as_completed(futures):
                    text_idx = futures[future]
                    try:
                        _, text_entities = future.result()
                        for entity_text, label, start, end in text_entities:
                            key = (entity_text, start)
                            if key not in seen[text_idx]:
                                seen[text_idx].add(key)
                                results[text_idx].append((entity_text, label, start, end))
                    except Exception as e:
                        logger.error("GLiNER prediction error on text %d: %s", text_idx, e)

                    done_count += 1
                    if progress_callback is not None:
                        progress_callback(done_count, len(texts))

        total_entities = sum(len(r) for r in results)
        logger.debug("[batch_detect] Total entities detected: %d across %d texts", total_entities, len(texts))

        # Apply regex patterns per text
        for text_idx, text in enumerate(texts):
            for entity_type, pattern in REGEX_PATTERNS.items():
                for match in re.finditer(pattern, text):
                    matched_text = match.group()
                    if not any(e[0] == matched_text for e in results[text_idx]):
                        results[text_idx].append(
                            (matched_text, entity_type.value, match.start(), match.end())
                        )

            results[text_idx].sort(key=lambda x: x[2])

        return results

    @classmethod
    def detect_entities(cls, text: str) -> List[Tuple[str, str, int, int]]:
        """Detect named entities in text using GLiNER and regex.

        Returns list of (entity_text, entity_type_label, start, end).
        """
        entities = []

        # Try GLiNER first (split into segments to avoid truncation)
        model = cls._get_model()
        if model is not None:
            try:
                entities.extend(cls._predict_on_segments(model, text))
            except Exception as e:
                logger.error("GLiNER prediction error: %s", e, exc_info=True)

        # Also apply regex patterns for common entity types
        for entity_type, pattern in REGEX_PATTERNS.items():
            for match in re.finditer(pattern, text):
                matched_text = match.group()
                # Avoid duplicates
                if not any(e[0] == matched_text for e in entities):
                    entities.append((
                        matched_text,
                        entity_type.value,
                        match.start(),
                        match.end(),
                    ))

        # Sort by position for consistent processing
        entities.sort(key=lambda x: x[2])
        return entities

    @classmethod
    async def anonymize_text(
        cls,
        text: str,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """Anonymize text by replacing sensitive entities with placeholders.

        Creates new mappings for previously unseen entities.
        """
        if not text:
            return text

        # Get existing mappings
        existing_mappings = await cls.get_mappings(db, project_id)

        # Count per entity type for generating new placeholders
        type_counts = defaultdict(int)
        for mapping in existing_mappings.values():
            type_counts[mapping.entity_type] += 1

        # Detect entities
        entities = cls.detect_entities(text)

        # Build replacement list (process from end to start to preserve positions)
        replacements = []
        for entity_text, label, start, end in entities:
            entity_text_clean = entity_text.strip()
            if len(entity_text_clean) < 2:
                continue

            if entity_text_clean in existing_mappings:
                placeholder = existing_mappings[entity_text_clean].anonymized_value
            else:
                # Determine entity type
                entity_type = LABEL_TO_ENTITY_TYPE.get(label, EntityType.OTHER)
                prefix = ENTITY_PREFIXES.get(entity_type, "ENTITE")
                type_counts[entity_type] += 1
                placeholder = f"[{prefix}_{type_counts[entity_type]}]"

                # Create new mapping in DB
                new_mapping = AnonymizationMapping(
                    project_id=project_id,
                    entity_type=entity_type,
                    original_value=entity_text_clean,
                    anonymized_value=placeholder,
                )
                db.add(new_mapping)
                existing_mappings[entity_text_clean] = new_mapping

            replacements.append((start, end, placeholder))

        # Apply replacements from end to start
        result = text
        for start, end, placeholder in reversed(replacements):
            result = result[:start] + placeholder + result[end:]

        await db.flush()
        return result

    @classmethod
    async def anonymize_chunks_batch(
        cls,
        texts: List[str],
        project_id: uuid.UUID,
        db: AsyncSession,
        progress_callback=None,
    ) -> List[str]:
        """Anonymize multiple texts in one pass (batch NER + single DB round-trip).

        Args:
            progress_callback: Optional callable(current_idx, total) for progress.
        """
        if not texts:
            return []

        # Single DB read for existing mappings
        existing_mappings = await cls.get_mappings(db, project_id)
        type_counts: Dict[EntityType, int] = defaultdict(int)
        for mapping in existing_mappings.values():
            type_counts[mapping.entity_type] += 1

        # Batch NER across all texts
        all_entities = cls._batch_detect_entities(texts, progress_callback=progress_callback)

        # Process each text
        results = []
        for text, entities in zip(texts, all_entities):
            replacements = []
            for entity_text, label, start, end in entities:
                entity_text_clean = entity_text.strip()
                if len(entity_text_clean) < 2:
                    continue

                if entity_text_clean in existing_mappings:
                    placeholder = existing_mappings[entity_text_clean].anonymized_value
                else:
                    entity_type = LABEL_TO_ENTITY_TYPE.get(label, EntityType.OTHER)
                    prefix = ENTITY_PREFIXES.get(entity_type, "ENTITE")
                    type_counts[entity_type] += 1
                    placeholder = f"[{prefix}_{type_counts[entity_type]}]"

                    new_mapping = AnonymizationMapping(
                        project_id=project_id,
                        entity_type=entity_type,
                        original_value=entity_text_clean,
                        anonymized_value=placeholder,
                    )
                    db.add(new_mapping)
                    existing_mappings[entity_text_clean] = new_mapping

                replacements.append((start, end, placeholder))

            result = text
            for start, end, placeholder in reversed(replacements):
                result = result[:start] + placeholder + result[end:]
            results.append(result)

        await db.flush()
        return results

    # Regex matching any placeholder the AI might generate: [PREFIX_N]
    _PLACEHOLDER_RE = re.compile(
        r'\['
        r'(?:' + '|'.join(ENTITY_PREFIXES.values()) + r')'
        r'_\d+'
        r'\]'
    )

    @classmethod
    def find_unknown_placeholders(cls, text: str, known_placeholders: set) -> set:
        """Find all [PREFIX_N] placeholders in text that have no known mapping."""
        all_found = set(cls._PLACEHOLDER_RE.findall(text))
        return all_found - known_placeholders

    @classmethod
    async def register_unknown_placeholders(
        cls,
        text: str,
        project_id: uuid.UUID,
        db: AsyncSession,
        known_placeholders: set,
    ) -> None:
        """Create empty mappings for AI-invented placeholders so they appear in Statistics.

        Any [PREFIX_N] token in *text* not present in *known_placeholders*
        gets a new AnonymizationMapping with an empty original_value.
        The user can then fill in the real value from the Statistics page.
        """
        unknown = cls.find_unknown_placeholders(text, known_placeholders)
        if not unknown:
            return

        for token in unknown:
            inner = token.strip("[]")                    # e.g. "ENTREPRISE_3"
            prefix = inner.rsplit("_", 1)[0]             # e.g. "ENTREPRISE"
            entity_type = PREFIX_TO_ENTITY_TYPE.get(prefix, EntityType.OTHER)

            # Check it doesn't already exist (race condition guard)
            existing = await db.execute(
                select(AnonymizationMapping)
                .where(AnonymizationMapping.project_id == project_id)
                .where(AnonymizationMapping.anonymized_value == token)
            )
            if existing.scalars().first() is not None:
                continue

            new_mapping = AnonymizationMapping(
                project_id=project_id,
                entity_type=entity_type,
                original_value="",
                anonymized_value=token,
                is_active=True,
            )
            db.add(new_mapping)

        await db.flush()

    @classmethod
    async def deanonymize_text(
        cls,
        anonymized_text: str,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """Replace anonymized placeholders with original values.

        Any AI-invented placeholder without a mapping is registered in the
        database (with empty original_value) so it appears on the Statistics
        page for the user to complete. The placeholder is kept as-is in the
        text until the user provides a real value.
        """
        if not anonymized_text:
            return anonymized_text

        mappings = await cls.get_mappings_by_placeholder(db, project_id)
        result = anonymized_text

        # Register any unknown placeholders the AI invented
        await cls.register_unknown_placeholders(result, project_id, db, set(mappings.keys()))

        # Replace known placeholders that have a real original value
        for placeholder, original in mappings.items():
            if original:  # skip empty mappings (unresolved)
                result = result.replace(placeholder, original)

        return result

    @classmethod
    async def resolve_orphans_with_ai(
        cls,
        project_id: uuid.UUID,
        db: AsyncSession,
        ai_service,
    ) -> dict:
        """Use AI to analyze context around orphan placeholders and guess their real values.

        For each orphan mapping (empty original_value), we extract surrounding text
        and ask the AI to extrapolate the most likely real value.

        Returns: {"resolved": int, "suggestions": [{"mapping_id": str, "placeholder": str, "suggested_value": str, "confidence": str}]}
        """
        from ..models.project import AnonymizationMapping, EntityType

        # Get all orphan mappings (empty original_value)
        result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.original_value == "")
        )
        orphans = result.scalars().all()
        if not orphans:
            return {"resolved": 0, "suggestions": []}

        # Get all chapters content to find context around placeholders
        from ..models.chapter import Chapter
        chapters_result = await db.execute(
            select(Chapter).where(Chapter.project_id == project_id)
        )
        chapters = chapters_result.scalars().all()
        all_text = "\n\n".join(ch.content for ch in chapters if ch.content)

        if not all_text:
            return {"resolved": 0, "suggestions": []}

        # Also get existing resolved mappings as context for the AI
        all_mappings_result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.original_value != "")
        )
        resolved_mappings = all_mappings_result.scalars().all()
        known_context = "\n".join(
            f"  {m.anonymized_value} = {m.original_value}"
            for m in resolved_mappings
        )

        # Extract context around each orphan placeholder
        orphan_contexts = []
        for orphan in orphans:
            placeholder = orphan.anonymized_value
            contexts = []
            for match in re.finditer(re.escape(placeholder), all_text):
                start = max(0, match.start() - 200)
                end = min(len(all_text), match.end() + 200)
                snippet = all_text[start:end].strip()
                contexts.append(snippet)
                if len(contexts) >= 3:
                    break
            if contexts:
                orphan_contexts.append({
                    "id": str(orphan.id),
                    "placeholder": placeholder,
                    "entity_type": orphan.entity_type.value if isinstance(orphan.entity_type, EntityType) else orphan.entity_type,
                    "contexts": contexts,
                })

        if not orphan_contexts:
            return {"resolved": 0, "suggestions": []}

        # Build the AI prompt
        system_prompt = """Tu es un expert en analyse de documents d'appels d'offres.

On t'a fourni des textes contenant des marqueurs anonymisés ([ENTREPRISE_1], [PERSONNE_2], etc.).
Certains marqueurs n'ont pas de correspondance connue. Tu dois deviner la valeur réelle
en analysant le contexte où ils apparaissent.

Tu as aussi la liste des correspondances déjà connues pour t'aider.

Réponds UNIQUEMENT au format JSON suivant (sans markdown):
[
  {
    "placeholder": "[ENTREPRISE_3]",
    "suggested_value": "Capgemini",
    "confidence": "high|medium|low",
    "reasoning": "Brève explication"
  }
]

Règles:
- Si le contexte ne permet pas de deviner, mets confidence: "low" et suggested_value: ""
- Utilise les mappings connus pour identifier des patterns (ex: si [ENTREPRISE_1]=Acme, un contexte similaire peut aider)
- Sois prudent : mieux vaut ne pas deviner que deviner faux"""

        orphan_descriptions = []
        for oc in orphan_contexts:
            desc = f"Marqueur: {oc['placeholder']} (type: {oc['entity_type']})\n"
            for i, ctx in enumerate(oc["contexts"]):
                desc += f"  Contexte {i+1}: ...{ctx}...\n"
            orphan_descriptions.append(desc)

        user_prompt = f"""Correspondances connues:
{known_context if known_context else "(aucune)"}

Marqueurs orphelins à résoudre:
{"".join(orphan_descriptions)}

Analyse le contexte de chaque marqueur et propose une valeur réelle."""

        try:
            from .ai_service import _parse_json_array
            raw_response = await ai_service.generate(
                system_prompt, user_prompt,
                temperature=0.1, max_tokens=4000,
            )
            suggestions_data = _parse_json_array(raw_response) or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("AI orphan resolution failed: %s", e)
            return {"resolved": 0, "suggestions": []}

        # Map suggestions back to orphan mappings
        orphan_by_placeholder = {o.anonymized_value: o for o in orphans}
        suggestions = []
        resolved = 0

        for suggestion in suggestions_data:
            placeholder = suggestion.get("placeholder", "")
            value = suggestion.get("suggested_value", "").strip()
            confidence = suggestion.get("confidence", "low")

            if placeholder in orphan_by_placeholder and value and confidence in ("high", "medium"):
                orphan = orphan_by_placeholder[placeholder]
                orphan.original_value = value
                resolved += 1

            suggestions.append({
                "placeholder": placeholder,
                "suggested_value": value,
                "confidence": confidence,
                "reasoning": suggestion.get("reasoning", ""),
            })

        if resolved > 0:
            await db.flush()

        return {"resolved": resolved, "suggestions": suggestions}

    @classmethod
    async def consolidate_mappings(
        cls,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict:
        """Find and merge duplicate mappings that refer to the same real entity.

        When the same entity is anonymized under multiple slugs (e.g. [ENTREPRISE_1]
        and [ENTREPRISE_3] both mapping to "Capgemini"), merge them into one canonical
        placeholder and update all content.

        Returns: {"merged": int, "groups": [{"canonical": str, "merged_from": [str], "original_value": str}]}
        """
        from ..models.project import AnonymizationMapping
        from ..models.chapter import Chapter
        from ..models.document import Document, DocumentChunk

        # Get all active mappings with a real value
        result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.original_value != "")
            .where(AnonymizationMapping.is_active == True)
            .order_by(AnonymizationMapping.created_at)
        )
        mappings = result.scalars().all()

        # Group by normalized original_value (lowercase, stripped)
        groups: dict = defaultdict(list)
        for m in mappings:
            key = m.original_value.strip().lower()
            groups[key].append(m)

        merged_count = 0
        merge_results = []

        for key, group in groups.items():
            if len(group) < 2:
                continue

            # First mapping is canonical (oldest)
            canonical = group[0]
            duplicates = group[1:]

            # Build replacement map: duplicate placeholder -> canonical placeholder
            replacements = {}
            merged_from = []
            for dup in duplicates:
                replacements[dup.anonymized_value] = canonical.anonymized_value
                merged_from.append(dup.anonymized_value)

            # Update all chapter content
            chapters_result = await db.execute(
                select(Chapter).where(Chapter.project_id == project_id)
            )
            chapters = chapters_result.scalars().all()
            for ch in chapters:
                changed = False
                if ch.content:
                    new_content = ch.content
                    for old_ph, new_ph in replacements.items():
                        if old_ph in new_content:
                            new_content = new_content.replace(old_ph, new_ph)
                            changed = True
                    if changed:
                        ch.content = new_content
                        ch.anonymized_content = new_content

            # Update document chunks
            chunks_result = await db.execute(
                select(DocumentChunk)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(Document.project_id == project_id)
            )
            chunks = chunks_result.scalars().all()
            for chunk in chunks:
                if chunk.anonymized_content:
                    new_anon = chunk.anonymized_content
                    changed = False
                    for old_ph, new_ph in replacements.items():
                        if old_ph in new_anon:
                            new_anon = new_anon.replace(old_ph, new_ph)
                            changed = True
                    if changed:
                        chunk.anonymized_content = new_anon

            # Deactivate duplicate mappings
            for dup in duplicates:
                dup.is_active = False

            merged_count += len(duplicates)
            merge_results.append({
                "canonical": canonical.anonymized_value,
                "merged_from": merged_from,
                "original_value": canonical.original_value,
            })

        if merged_count > 0:
            await db.flush()

        return {"merged": merged_count, "groups": merge_results}

    @classmethod
    async def anonymize_prompt(
        cls,
        prompt: str,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """Anonymize a user prompt before sending to AI."""
        return await cls.anonymize_text(prompt, project_id, db)

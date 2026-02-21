"""Anonymization service using GLiNER for NER-based pseudonymization."""
import re
import uuid
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.project import AnonymizationMapping, EntityType


# Entity labels GLiNER will search for
GLINER_LABELS = [
    "person",
    "organization",
    "company",
    "email address",
    "phone number",
    "address",
    "project code",
    "solution name",
    "monetary amount",
]

# Mapping from GLiNER labels to our entity types
LABEL_TO_ENTITY_TYPE = {
    "person": EntityType.PERSON,
    "organization": EntityType.COMPANY,
    "company": EntityType.COMPANY,
    "email address": EntityType.EMAIL,
    "phone number": EntityType.PHONE,
    "address": EntityType.ADDRESS,
    "project code": EntityType.PROJECT_CODE,
    "solution name": EntityType.SOLUTION_NAME,
    "monetary amount": EntityType.AMOUNT,
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

# Regex patterns for entities GLiNER might miss
REGEX_PATTERNS = {
    EntityType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    EntityType.PHONE: r'(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}',
}


class AnonymizationService:
    """Service for anonymizing/pseudonymizing sensitive content."""

    _model = None

    @classmethod
    def _get_model(cls):
        """Lazy-load the GLiNER model."""
        if cls._model is None:
            try:
                from gliner import GLiNER
                from ..config import settings
                cls._model = GLiNER.from_pretrained(settings.gliner_model)
            except Exception as e:
                print(f"Warning: Could not load GLiNER model: {e}")
                cls._model = None
        return cls._model

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

    @classmethod
    def _predict_on_segments(cls, model, text: str) -> List[Tuple[str, str, int, int]]:
        """Run GLiNER prediction on overlapping text segments to avoid truncation."""
        # Build word boundary list: [(word_start_char, word_end_char), ...]
        word_spans = [(m.start(), m.end()) for m in re.finditer(r'\S+', text)]

        if len(word_spans) <= cls._GLINER_SEGMENT_WORDS:
            predictions = model.predict_entities(text, GLINER_LABELS, threshold=0.4)
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

            predictions = model.predict_entities(segment_text, GLINER_LABELS, threshold=0.4)
            for pred in predictions:
                abs_start = seg_char_start + pred["start"]
                abs_end = seg_char_start + pred["end"]
                key = (pred["text"], abs_start)
                if key not in seen:
                    seen.add(key)
                    entities.append((pred["text"], pred["label"], abs_start, abs_end))

        return entities

    @classmethod
    def _batch_detect_entities(cls, texts: List[str]) -> List[List[Tuple[str, str, int, int]]]:
        """Detect entities across multiple texts using batched GLiNER inference.

        Much faster than calling detect_entities() per text, because GLiNER
        batches the transformer forward pass across all segments.
        """
        results: List[List[Tuple[str, str, int, int]]] = [[] for _ in texts]
        seen: List[set] = [set() for _ in texts]

        model = cls._get_model()
        if model is not None:
            # Build all segments from all texts
            all_segments: List[Tuple[int, int, str]] = []  # (text_idx, seg_char_start, segment_text)
            for text_idx, text in enumerate(texts):
                word_spans = [(m.start(), m.end()) for m in re.finditer(r'\S+', text)]
                if not word_spans:
                    continue
                if len(word_spans) <= cls._GLINER_SEGMENT_WORDS:
                    all_segments.append((text_idx, 0, text))
                else:
                    step = cls._GLINER_SEGMENT_WORDS - cls._GLINER_OVERLAP_WORDS
                    for i in range(0, len(word_spans), step):
                        span_slice = word_spans[i: i + cls._GLINER_SEGMENT_WORDS]
                        seg_start = span_slice[0][0]
                        seg_end = span_slice[-1][1]
                        all_segments.append((text_idx, seg_start, text[seg_start:seg_end]))

            if all_segments:
                segment_texts = [s[2] for s in all_segments]
                try:
                    batch_predictions = model.predict_entities(
                        segment_texts, GLINER_LABELS, threshold=0.4
                    )
                    # predict_entities returns list-of-lists when given a list input
                    for (text_idx, seg_start, _), preds in zip(all_segments, batch_predictions):
                        for pred in preds:
                            abs_start = seg_start + pred["start"]
                            abs_end = seg_start + pred["end"]
                            key = (pred["text"], abs_start)
                            if key not in seen[text_idx]:
                                seen[text_idx].add(key)
                                results[text_idx].append(
                                    (pred["text"], pred["label"], abs_start, abs_end)
                                )
                except Exception as e:
                    print(f"GLiNER batch prediction error: {e}")

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
                print(f"GLiNER prediction error: {e}")

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
    ) -> List[str]:
        """Anonymize multiple texts in one pass (batch NER + single DB round-trip).

        Much faster than calling anonymize_text() per chunk.
        """
        if not texts:
            return []

        # Single DB read for existing mappings
        existing_mappings = await cls.get_mappings(db, project_id)
        type_counts: Dict[EntityType, int] = defaultdict(int)
        for mapping in existing_mappings.values():
            type_counts[mapping.entity_type] += 1

        # Batch NER across all texts
        all_entities = cls._batch_detect_entities(texts)

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

    @classmethod
    async def deanonymize_text(
        cls,
        anonymized_text: str,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """Replace anonymized placeholders with original values."""
        if not anonymized_text:
            return anonymized_text

        mappings = await cls.get_mappings_by_placeholder(db, project_id)
        result = anonymized_text

        for placeholder, original in mappings.items():
            result = result.replace(placeholder, original)

        return result

    @classmethod
    async def anonymize_prompt(
        cls,
        prompt: str,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """Anonymize a user prompt before sending to AI."""
        return await cls.anonymize_text(prompt, project_id, db)

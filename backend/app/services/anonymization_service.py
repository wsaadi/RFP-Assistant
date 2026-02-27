"""Anonymization service using a local LLM (Gemma 2B via Ollama) for NER-based pseudonymization.

Replaces GLiNER with a small LLM that understands context, drastically reducing
false positives (e.g., "Business Développement Manager" detected as a person name).

Architecture:
- Primary: Ollama running on the host machine (GPU-accelerated via Metal on Mac)
- Fallback: Regex-only detection if Ollama is unavailable

The LLM receives a focused prompt asking it to extract ONLY real sensitive entities
from French RFP documents, with explicit instructions to ignore job titles, roles,
legal terms, etc.
"""
import asyncio
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.project import AnonymizationMapping, EntityType

logger = logging.getLogger(__name__)

# ── Ollama configuration ──
# On Docker Desktop for Mac: host.docker.internal points to the Mac host
# where Ollama runs natively with Metal GPU acceleration.
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
_OLLAMA_MODEL = os.environ.get("OLLAMA_NER_MODEL", "gemma3:4b")
_OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_NER_TIMEOUT", "60"))
# Maximum concurrent requests to Ollama (avoid overloading)
_OLLAMA_CONCURRENCY = int(os.environ.get("OLLAMA_NER_CONCURRENCY", "3"))

# ── NER Prompt ──
# This prompt is the core of the anonymization quality. It tells the LLM
# exactly what to extract and what to ignore, leveraging its contextual
# understanding to avoid false positives.
_NER_SYSTEM_PROMPT = """\
Tu es un système d'extraction d'entités nommées spécialisé dans les documents d'appels d'offres français.

Ta mission : extraire UNIQUEMENT les vraies données sensibles qui doivent être anonymisées.

EXTRAIRE (entités sensibles réelles) :
- "person" : Vrais noms et prénoms de personnes physiques (ex: "Jean Dupont", "Marie-Claire Martin"). Un nom de personne contient TOUJOURS au minimum un prénom ET un nom de famille, tous deux avec une majuscule.
- "company" : Vrais noms d'entreprises et organisations privées (ex: "Capgemini", "Sopra Steria", "Orange Business Services"). PAS les institutions publiques connues.
- "email" : Adresses email complètes
- "address" : Adresses postales physiques complètes (avec numéro, rue, ville)
- "project_code" : Codes de référence de projet ou d'appel d'offres spécifiques (ex: "AO-2024-0847", "PRJ-FR-2025")

NE PAS EXTRAIRE (liste non exhaustive) :
- Titres et fonctions : directeur, chef de projet, responsable, DPO, DSI, RSSI, Business Development Manager, consultant, architecte, ingénieur, pilote, référent, coordinateur...
- Rôles contractuels : titulaire, prestataire, candidat, sous-traitant, bénéficiaire, attributaire, mandataire, acheteur, maître d'ouvrage, cotraitant...
- Termes génériques : personne, client, fournisseur, partenaire, membre, tiers, autorité, entité, structure, service, direction, utilisateur...
- Institutions publiques : CNIL, ANSSI, DINUM, ARCEP, Légifrance, État, République française, Union européenne...
- Termes juridiques : CCAG, CCAP, CCTP, RGPD, RGAA, code du travail, code de la commande publique, article X...
- Standards et normes : ISO 27001, NF EN, AFNOR, W3C, RGS, RGI...
- Technologies : IaaS, PaaS, SaaS, TMA, AMOA, cloud, datacenter...
- Termes civilités seuls : Monsieur, Madame, M., Mme (sauf si suivis d'un vrai nom)
- Noms de pays/villes courants : France, Paris, Europe...
- Mots en minuscules : un vrai nom propre commence TOUJOURS par une majuscule

IMPORTANT :
- En cas de doute, NE PAS extraire. Mieux vaut rater une entité que créer un faux positif.
- "Responsable de la sécurité" → NE PAS extraire (c'est un rôle)
- "Pierre Durand, responsable de la sécurité" → extraire UNIQUEMENT "Pierre Durand"
- "le prestataire" → NE PAS extraire
- "la société Atos" → extraire "Atos"

Réponds UNIQUEMENT avec un tableau JSON (sans markdown, sans explication) :
[{"text": "texte exact trouvé", "type": "person|company|email|address|project_code"}]

Si aucune entité sensible n'est trouvée, réponds : []"""

# Mapping from LLM entity types to our internal EntityType
LABEL_TO_ENTITY_TYPE = {
    "person": EntityType.PERSON,
    "organization": EntityType.COMPANY,
    "company": EntityType.COMPANY,
    "email": EntityType.EMAIL,
    "email address": EntityType.EMAIL,
    "address": EntityType.ADDRESS,
    "project_code": EntityType.PROJECT_CODE,
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

# Regex patterns for entities the LLM might miss (deterministic fallback)
REGEX_PATTERNS = {
    EntityType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
}

# ---------------------------------------------------------------------------
# Post-detection filtering (safety net on top of LLM output)
# ---------------------------------------------------------------------------

_STOPLIST_LOWER: set = {
    # Generic role nouns often misdetected as person names
    "personne", "personnes", "personne physique", "personnes physiques",
    "titulaire", "le titulaire", "la titulaire", "titulaires",
    "candidat", "candidats", "candidate", "candidates", "le candidat",
    "sous-traitant", "sous-traitants", "sous-traitance", "le sous-traitant",
    "bénéficiaire", "bénéficiaires", "projet bénéficiaire",
    "facilitateur", "facilitateurs",
    "éditeur", "éditeurs", "partenaires éditeurs", "l'éditeur",
    "prestataire", "prestataires", "le prestataire",
    "fournisseur", "fournisseurs",
    "attributaire", "attributaires",
    "demandeur", "demandeurs",
    "destinataire", "destinataires",
    "utilisateur", "utilisateurs", "l'utilisateur",
    "interlocuteur", "interlocuteurs",
    "correspondant", "correspondants",
    "mandataire", "mandataires",
    "signataire", "signataires",
    "transitaire", "transitaires",
    "cocontractant", "cocontractants",
    "cotraitant", "cotraitants",
    "adjudicataire", "adjudicataires",
    "acheteur", "acheteurs", "l'acheteur",
    "pouvoir adjudicateur", "le pouvoir adjudicateur",
    "maître d'ouvrage", "maître d'oeuvre", "maître d'œuvre",
    "maîtrise d'ouvrage", "maîtrise d'oeuvre", "maîtrise d'œuvre",
    "client", "clients", "le client",
    "membre", "membres",
    "partie", "parties", "les parties",
    "tiers", "le tiers",
    "autorité", "autorités",
    "entité", "entités",
    "organisme", "organismes",
    "structure", "structures",
    "service", "services",
    "direction", "directions",
    "division", "divisions",
    "département", "départements",
    "pôle", "pôles",
    "bureau", "bureaux",
    # Gender terms
    "femme", "homme", "femme/homme", "homme/femme", "h/f", "f/h",
    "madame", "monsieur", "mesdames", "messieurs",
    # Job titles / functions
    "directeur", "directrice", "directeurs",
    "responsable", "responsables",
    "chef de projet", "chefs de projet",
    "dsi", "dpo", "rssi", "rsi", "dga", "dgs",
    "délégué à la protection des données",
    "administrateur", "administrateurs",
    "gestionnaire", "gestionnaires",
    "ingénieur", "ingénieurs",
    "technicien", "techniciens",
    "consultant", "consultants",
    "expert", "experts",
    "analyste", "analystes",
    "architecte", "architectes",
    "développeur", "développeurs",
    "coordonnateur", "coordinateur",
    "pilote", "pilotes",
    "référent", "référents",
    "rapporteur", "rapporteurs",
    "business development manager", "business développement manager",
    "account manager", "project manager", "delivery manager",
    "product owner", "scrum master", "tech lead",
    # Generic IT / business terms
    "infrastructure as a service", "iaas",
    "platform as a service", "paas",
    "software as a service", "saas",
    "tierce maintenance applicative", "tma",
    "assistance à maîtrise d'ouvrage", "amoa", "amoe",
    "centre de services", "centres de services",
    "cloud", "datacenter", "data center",
    "lot", "lots", "tranche", "tranches",
    "marché", "marchés", "accord-cadre",
    "promesse web",
    # Legal / regulatory references
    "code du travail", "code de la commande publique",
    "code des marchés publics", "code civil", "code pénal",
    "code général des collectivités territoriales",
    "ccag", "ccag/tic", "ccag-tic", "ccag tic", "ccag-fcs", "ccag-pi",
    "ccap", "cctp", "rc", "ae", "bpu", "dpgf", "aqe",
    "rgpd", "rgaa", "rgs", "rgi",
    "règlement général sur la protection des données",
    "numéro de la commande",
    # Public institutions / international bodies (not sensitive)
    "cnil", "w3c", "iso", "afnor", "iana",
    "unece", "united nations economic commission for europe",
    "united nations", "nations unies",
    "union européenne", "commission européenne", "parlement européen",
    "aife", "dgfip", "dinum", "anssi", "arcep", "cnam", "cpam",
    "cerfa", "légifrance",
    "état", "l'état", "france", "république française",
    # Well-known public product/system names
    "helios", "chorus", "chorus pro",
}

_REJECT_PATTERNS: list = [
    re.compile(r"^ISO\s*\d", re.IGNORECASE),
    re.compile(r"^NF\s", re.IGNORECASE),
    re.compile(r"^J\s*[+-]\s*\d+$", re.IGNORECASE),
    re.compile(r"^\d{4,5}$"),
    re.compile(r"^\d+$"),
    re.compile(r"^(article|articles)\s+\d", re.IGNORECASE),
    re.compile(r"^(annexe|annexes)\s+\d", re.IGNORECASE),
    re.compile(r"^(chapitre|chapitres)\s+\d", re.IGNORECASE),
    re.compile(r"^(alinéa|alinéas)\s+\d", re.IGNORECASE),
    re.compile(r"^n°\s*\d", re.IGNORECASE),
    re.compile(r"^v\d+(\.\d+)*$", re.IGNORECASE),
]

_MIN_ENTITY_LENGTH = 3


def _should_keep_entity(entity_text: str, label: str) -> bool:
    """Return True if the detected entity is likely a real sensitive entity.

    This is a safety net on top of the LLM output — the LLM should already
    filter most false positives, but we keep the stoplist for defense in depth.
    """
    cleaned = entity_text.strip()

    if len(cleaned) < _MIN_ENTITY_LENGTH:
        return False

    if cleaned.lower() in _STOPLIST_LOWER:
        return False

    for pattern in _REJECT_PATTERNS:
        if pattern.search(cleaned):
            return False

    # For "person" label: reject if all words start lowercase
    if label in ("person",):
        words = cleaned.split()
        if all(w[0].islower() for w in words if w):
            return False

    return True


class AnonymizationService:
    """Service for anonymizing/pseudonymizing sensitive content.

    Uses a local LLM (Gemma via Ollama) for context-aware NER detection,
    with regex fallback for deterministic patterns (emails).
    """

    _ollama_available: Optional[bool] = None
    _http_client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def _get_http_client(cls) -> httpx.AsyncClient:
        """Get or create a reusable async HTTP client for Ollama."""
        if cls._http_client is None or cls._http_client.is_closed:
            cls._http_client = httpx.AsyncClient(
                base_url=_OLLAMA_BASE_URL,
                timeout=httpx.Timeout(_OLLAMA_TIMEOUT, connect=10.0),
            )
        return cls._http_client

    @classmethod
    async def _check_ollama(cls) -> bool:
        """Check if Ollama is reachable and the model is available."""
        if cls._ollama_available is not None:
            return cls._ollama_available

        try:
            client = await cls._get_http_client()
            resp = await client.get("/api/tags", timeout=5.0)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                # Check if our model (or a variant) is available
                base_model = _OLLAMA_MODEL.split(":")[0]
                available = any(base_model in name for name in model_names)
                if available:
                    logger.info("Ollama available at %s with model %s", _OLLAMA_BASE_URL, _OLLAMA_MODEL)
                    cls._ollama_available = True
                else:
                    logger.warning(
                        "Ollama reachable but model '%s' not found. Available: %s. "
                        "Run 'ollama pull %s' on the host to download it.",
                        _OLLAMA_MODEL, model_names, _OLLAMA_MODEL,
                    )
                    cls._ollama_available = False
            else:
                logger.warning("Ollama returned status %d", resp.status_code)
                cls._ollama_available = False
        except Exception as e:
            logger.warning(
                "Ollama not reachable at %s: %s. "
                "Falling back to regex-only anonymization. "
                "To enable LLM-based NER, install Ollama on your host and run: "
                "ollama pull %s",
                _OLLAMA_BASE_URL, e, _OLLAMA_MODEL,
            )
            cls._ollama_available = False

        return cls._ollama_available

    @classmethod
    def is_ner_available(cls) -> bool:
        """Check if NER is available (sync wrapper for backward compatibility)."""
        # Optimistic: if we haven't checked yet, assume it might be available
        if cls._ollama_available is None:
            return True
        return cls._ollama_available

    @classmethod
    async def _detect_entities_llm(cls, text: str) -> List[Tuple[str, str, int, int]]:
        """Detect entities using the local LLM via Ollama.

        Returns list of (entity_text, label, start_char, end_char).
        """
        if not text.strip():
            return []

        client = await cls._get_http_client()

        try:
            resp = await client.post(
                "/api/chat",
                json={
                    "model": _OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _NER_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Texte à analyser :\n\n{text}"},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 2048,
                    },
                    "format": "json",
                },
            )
            resp.raise_for_status()
            result = resp.json()
            raw_content = result.get("message", {}).get("content", "[]")

            # Parse the JSON response
            entities_data = _parse_llm_json(raw_content)
            if not entities_data:
                return []

            # Map LLM output to (text, label, start, end) tuples
            entities = []
            for item in entities_data:
                entity_text = item.get("text", "").strip()
                entity_type = item.get("type", "").lower().strip()

                if not entity_text or not entity_type:
                    continue

                if entity_type not in LABEL_TO_ENTITY_TYPE:
                    continue

                if not _should_keep_entity(entity_text, entity_type):
                    continue

                # Find all occurrences in the original text
                start = 0
                while True:
                    idx = text.find(entity_text, start)
                    if idx == -1:
                        break
                    entities.append((entity_text, entity_type, idx, idx + len(entity_text)))
                    start = idx + len(entity_text)

            # Deduplicate by (text, start)
            seen = set()
            unique_entities = []
            for e in entities:
                key = (e[0], e[2])
                if key not in seen:
                    seen.add(key)
                    unique_entities.append(e)

            unique_entities.sort(key=lambda x: x[2])
            return unique_entities

        except httpx.TimeoutException:
            logger.warning("Ollama request timed out after %ds", _OLLAMA_TIMEOUT)
            return []
        except httpx.HTTPStatusError as e:
            logger.warning("Ollama HTTP error: %s", e)
            return []
        except Exception as e:
            logger.error("LLM entity detection failed: %s", e, exc_info=True)
            return []

    @classmethod
    async def _batch_detect_entities(
        cls,
        texts: List[str],
        progress_callback=None,
    ) -> List[List[Tuple[str, str, int, int]]]:
        """Detect entities across multiple texts using the LLM.

        Uses a semaphore to limit concurrent Ollama requests.
        Falls back to regex-only if Ollama is unavailable.
        """
        results: List[List[Tuple[str, str, int, int]]] = [[] for _ in texts]

        ollama_ok = await cls._check_ollama()

        if ollama_ok:
            semaphore = asyncio.Semaphore(_OLLAMA_CONCURRENCY)
            done_count = 0

            async def _process_one(idx: int, text: str):
                nonlocal done_count
                async with semaphore:
                    entities = await cls._detect_entities_llm(text)
                    results[idx] = entities
                    done_count += 1
                    if progress_callback:
                        progress_callback(done_count, len(texts))

            # Process all texts concurrently (limited by semaphore)
            tasks = [_process_one(idx, text) for idx, text in enumerate(texts)]
            await asyncio.gather(*tasks, return_exceptions=True)

            total_entities = sum(len(r) for r in results)
            logger.info(
                "[batch_detect] LLM NER: %d entities across %d texts",
                total_entities, len(texts),
            )
        else:
            logger.info("[batch_detect] Ollama unavailable, using regex-only fallback")
            if progress_callback:
                progress_callback(len(texts), len(texts))

        # Always apply regex patterns (deterministic fallback for emails etc.)
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
    async def detect_entities(cls, text: str) -> List[Tuple[str, str, int, int]]:
        """Detect named entities in text using LLM and regex.

        Returns list of (entity_text, entity_type_label, start, end).
        """
        entities = []

        ollama_ok = await cls._check_ollama()
        if ollama_ok:
            try:
                entities.extend(await cls._detect_entities_llm(text))
            except Exception as e:
                logger.error("LLM prediction error: %s", e, exc_info=True)

        # Also apply regex patterns for common entity types
        for entity_type, pattern in REGEX_PATTERNS.items():
            for match in re.finditer(pattern, text):
                matched_text = match.group()
                if not any(e[0] == matched_text for e in entities):
                    entities.append((
                        matched_text,
                        entity_type.value,
                        match.start(),
                        match.end(),
                    ))

        entities.sort(key=lambda x: x[2])
        return entities

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

        existing_mappings = await cls.get_mappings(db, project_id)

        type_counts = defaultdict(int)
        for mapping in existing_mappings.values():
            type_counts[mapping.entity_type] += 1

        entities = await cls.detect_entities(text)

        replacements = []
        for entity_text, label, start, end in entities:
            entity_text_clean = entity_text.strip()
            if not _should_keep_entity(entity_text_clean, label):
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
        """Anonymize multiple texts in one pass (batch NER + single DB round-trip)."""
        if not texts:
            return []

        existing_mappings = await cls.get_mappings(db, project_id)
        type_counts: Dict[EntityType, int] = defaultdict(int)
        for mapping in existing_mappings.values():
            type_counts[mapping.entity_type] += 1

        # Batch NER across all texts
        all_entities = await cls._batch_detect_entities(texts, progress_callback)

        results = []
        for text, entities in zip(texts, all_entities):
            replacements = []
            for entity_text, label, start, end in entities:
                entity_text_clean = entity_text.strip()
                if not _should_keep_entity(entity_text_clean, label):
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
        """Create empty mappings for AI-invented placeholders so they appear in Statistics."""
        unknown = cls.find_unknown_placeholders(text, known_placeholders)
        if not unknown:
            return

        for token in unknown:
            inner = token.strip("[]")
            prefix = inner.rsplit("_", 1)[0]
            entity_type = PREFIX_TO_ENTITY_TYPE.get(prefix, EntityType.OTHER)

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
        """Replace anonymized placeholders with original values."""
        if not anonymized_text:
            return anonymized_text

        mappings = await cls.get_mappings_by_placeholder(db, project_id)
        result = anonymized_text

        await cls.register_unknown_placeholders(result, project_id, db, set(mappings.keys()))

        for placeholder, original in mappings.items():
            if original:
                result = result.replace(placeholder, original)

        return result

    @classmethod
    async def resolve_orphans_with_ai(
        cls,
        project_id: uuid.UUID,
        db: AsyncSession,
        ai_service,
    ) -> dict:
        """Use AI to analyze context around orphan placeholders and guess their real values."""
        from ..models.project import AnonymizationMapping, EntityType

        result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.original_value == "")
        )
        orphans = result.scalars().all()
        if not orphans:
            return {"resolved": 0, "suggestions": []}

        from ..models.chapter import Chapter
        chapters_result = await db.execute(
            select(Chapter).where(Chapter.project_id == project_id)
        )
        chapters = chapters_result.scalars().all()
        all_text = "\n\n".join(ch.content for ch in chapters if ch.content)

        if not all_text:
            return {"resolved": 0, "suggestions": []}

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
            logger.warning("AI orphan resolution failed: %s", e)
            return {"resolved": 0, "suggestions": []}

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
        """Find and merge duplicate mappings that refer to the same real entity."""
        from ..models.project import AnonymizationMapping
        from ..models.chapter import Chapter
        from ..models.document import Document, DocumentChunk

        result = await db.execute(
            select(AnonymizationMapping)
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.original_value != "")
            .where(AnonymizationMapping.is_active == True)
            .order_by(AnonymizationMapping.created_at)
        )
        mappings = result.scalars().all()

        groups: dict = defaultdict(list)
        for m in mappings:
            key = m.original_value.strip().lower()
            groups[key].append(m)

        merged_count = 0
        merge_results = []

        for key, group in groups.items():
            if len(group) < 2:
                continue

            canonical = group[0]
            duplicates = group[1:]

            replacements = {}
            merged_from = []
            for dup in duplicates:
                replacements[dup.anonymized_value] = canonical.anonymized_value
                merged_from.append(dup.anonymized_value)

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
    async def apply_existing_mappings(
        cls,
        text: str,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> str:
        """Replace known entities in text using existing DB mappings only (no NER)."""
        if not text:
            return text

        existing_mappings = await cls.get_mappings(db, project_id)
        if not existing_mappings:
            return text

        result = text
        for original, mapping in sorted(
            existing_mappings.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if original:
                result = result.replace(original, mapping.anonymized_value)

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


def _parse_llm_json(raw: str) -> Optional[list]:
    """Parse JSON from LLM response, handling common formatting issues."""
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Remove markdown code block wrappers if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (``` markers)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try direct parse first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        # Some models wrap in {"entities": [...]} or {"results": [...]}
        if isinstance(data, dict):
            for key in ("entities", "results", "data", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return None
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from the response
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None

"""Anonymization service using a local LLM (Qwen2.5 14B via Ollama) for NER-based pseudonymization.

Uses a capable 14B-parameter model for accurate context-aware entity detection,
including short company names/acronyms (e.g., "EDF" alone, not just "EDF SA").

Architecture:
- Primary: Ollama running on DGX Spark (GPU-accelerated)
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
# Ollama runs on the DGX Spark — Docker containers reach it via
# host.docker.internal (Mac host forwards port 11434 to DGX via socat).
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
_OLLAMA_MODEL = os.environ.get("OLLAMA_NER_MODEL", "qwen2.5:14b")
_OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_NER_TIMEOUT", "120"))
# Maximum concurrent requests to Ollama (avoid overloading)
_OLLAMA_CONCURRENCY = int(os.environ.get("OLLAMA_NER_CONCURRENCY", "2"))
# Number of chunks grouped into a single LLM call.
# 4 chunks × ~300 words = ~1200 words ≈ 1600 tokens — well within model capacity.
# Reduces total LLM calls by ~75% since the system prompt is only sent once per group.
_CHUNKS_PER_GROUP = int(os.environ.get("OLLAMA_NER_CHUNKS_PER_GROUP", "4"))
# Separator between grouped chunks in the prompt
_CHUNK_SEPARATOR = "\n\n---\n\n"

# ── NER Prompt ──
# This prompt is the core of the anonymization quality. It tells the LLM
# exactly what to extract and what to ignore, leveraging its contextual
# understanding to avoid false positives.
_NER_SYSTEM_PROMPT = """\
Tu es un système d'extraction d'entités nommées spécialisé dans les documents d'appels d'offres français.

Ta mission : extraire UNIQUEMENT les vraies données sensibles qui doivent être anonymisées.

EXTRAIRE (entités sensibles réelles) :
- "person" : Vrais noms et prénoms de personnes physiques (ex: "Jean Dupont", "Marie-Claire Martin"). Un nom de personne contient TOUJOURS au minimum un prénom ET un nom de famille, tous deux avec une majuscule.
- "company" : Vrais noms d'entreprises et organisations privées, Y COMPRIS les noms courts, acronymes et sigles d'entreprises. Exemples :
  - Noms complets : "Capgemini", "Sopra Steria", "Orange Business Services", "Accenture"
  - Noms courts / sigles : "EDF", "SFR", "Atos", "Engie", "SNCF", "TotalEnergies", "BNP Paribas"
  - Avec forme juridique OU sans : "EDF SA" ET "EDF" doivent TOUS DEUX être extraits
  - Groupements hospitaliers, centrales d'achat : "RESAH", "UniHA", "UGAP" (sauf s'ils sont le client de l'AO en cours)
  - Media / autres : "MediaTV", "TF1", "Canal+"
  IMPORTANT : si "EDF SA" apparaît, extrais AUSSI "EDF" quand il apparaît seul. Ne rate pas les formes courtes d'un nom d'entreprise.
  PAS les institutions publiques connues de l'État (CNIL, ANSSI, DINUM, etc.).
- "email" : Adresses email complètes
- "address" : Adresses postales physiques complètes (avec numéro, rue, ville)
- "project_code" : Codes de référence de projet ou d'appel d'offres spécifiques (ex: "AO-2024-0847", "PRJ-FR-2025")

NE PAS EXTRAIRE (liste non exhaustive) :
- Titres et fonctions : directeur, chef de projet, responsable, DPO, DSI, RSSI, Business Development Manager, consultant, architecte, ingénieur, pilote, référent, coordinateur...
- Rôles contractuels : titulaire, prestataire, candidat, sous-traitant, bénéficiaire, attributaire, mandataire, acheteur, maître d'ouvrage, cotraitant...
- Termes génériques : personne, client, fournisseur, partenaire, membre, tiers, autorité, entité, structure, service, direction, utilisateur...
- Institutions publiques d'État : CNIL, ANSSI, DINUM, ARCEP, Légifrance, État, République française, Union européenne...
- Termes juridiques : CCAG, CCAP, CCTP, RGPD, RGAA, code du travail, code de la commande publique, article X...
- Standards et normes : ISO 27001, NF EN, AFNOR, W3C, RGS, RGI...
- Technologies et acronymes techniques : IaaS, PaaS, SaaS, TMA, AMOA, cloud, datacenter, API, SQL, CRM, ERP...
- Termes civilités seuls : Monsieur, Madame, M., Mme (sauf si suivis d'un vrai nom)
- Noms de pays/villes courants : France, Paris, Europe...
- Mots en minuscules : un vrai nom propre commence TOUJOURS par une majuscule

IMPORTANT :
- Pour les entreprises : extrais TOUTES les formes du nom (courte ET longue). "EDF SA" et "EDF" sont deux occurrences à extraire séparément.
- En cas de doute sur une entreprise connue, EXTRAIRE. Mieux vaut un faux positif entreprise qu'un oubli.
- En cas de doute sur un rôle/titre, NE PAS extraire.
- "Responsable de la sécurité" → NE PAS extraire (c'est un rôle)
- "Pierre Durand, responsable de la sécurité" → extraire UNIQUEMENT "Pierre Durand"
- "le prestataire" → NE PAS extraire
- "la société Atos" → extraire "Atos"
- "un contrat avec EDF" → extraire "EDF"
- "EDF SA, filiale du groupe EDF" → extraire "EDF SA" ET "EDF"

Le texte peut contenir plusieurs blocs séparés par "--- BLOC N ---".
Dans ce cas, ajoute le numéro du bloc dans ta réponse.

Réponds UNIQUEMENT avec un tableau JSON (sans markdown, sans explication) :
[{"text": "texte exact trouvé", "type": "person|company|email|address|project_code", "block": 1}]

Si aucune entité sensible n'est trouvée, réponds : []"""

# Mapping from LLM entity types to our internal EntityType.
# Must accept both the English labels asked in the prompt AND French
# variants / synonyms that small models (Gemma, Mistral, etc.) commonly return.
LABEL_TO_ENTITY_TYPE = {
    # English (prompt canonical labels)
    "person": EntityType.PERSON,
    "company": EntityType.COMPANY,
    "email": EntityType.EMAIL,
    "address": EntityType.ADDRESS,
    "project_code": EntityType.PROJECT_CODE,
    # English synonyms/variants
    "organization": EntityType.COMPANY,
    "organisation": EntityType.COMPANY,
    "email address": EntityType.EMAIL,
    "email_address": EntityType.EMAIL,
    "phone": EntityType.PHONE,
    "phone_number": EntityType.PHONE,
    "telephone": EntityType.PHONE,
    # French variants (models sometimes answer in French despite the prompt)
    "personne": EntityType.PERSON,
    "nom": EntityType.PERSON,
    "nom_personne": EntityType.PERSON,
    "prénom": EntityType.PERSON,
    "entreprise": EntityType.COMPANY,
    "société": EntityType.COMPANY,
    "societe": EntityType.COMPANY,
    "organisation": EntityType.COMPANY,
    "adresse": EntityType.ADDRESS,
    "adresse_postale": EntityType.ADDRESS,
    "adresse postale": EntityType.ADDRESS,
    "téléphone": EntityType.PHONE,
    "telephone": EntityType.PHONE,
    "numéro de téléphone": EntityType.PHONE,
    "code_projet": EntityType.PROJECT_CODE,
    "code projet": EntityType.PROJECT_CODE,
    "code_ao": EntityType.RFP_CODE,
    "code ao": EntityType.RFP_CODE,
    "rfp_code": EntityType.RFP_CODE,
    "solution": EntityType.SOLUTION_NAME,
    "solution_name": EntityType.SOLUTION_NAME,
    "nom_solution": EntityType.SOLUTION_NAME,
    "date": EntityType.DATE,
    "montant": EntityType.AMOUNT,
    "amount": EntityType.AMOUNT,
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
    # French phone numbers: 01 23 45 67 89, +33 1 23 45 67 89, 0123456789
    EntityType.PHONE: r'(?:\+33\s*|0)[1-9](?:[\s.-]?\d{2}){4}\b',
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

    Uses a local LLM (Qwen via Ollama) for context-aware NER detection,
    with regex fallback for deterministic patterns (emails).
    """

    _ollama_available: Optional[bool] = None
    _http_client: Optional[httpx.AsyncClient] = None
    # Track the *last* NER run outcome so callers can report it to the user.
    # None = not run yet, True = last run produced entities, False = last run
    # returned nothing (Ollama might be up but model returned empty).
    _last_ner_produced_entities: Optional[bool] = None
    # Human-readable reason when NER fails/returns nothing
    _last_ner_failure_reason: Optional[str] = None

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
        """Check if Ollama is reachable and the model is available.

        Only caches *success* permanently.  Failures are retried each time
        so that a temporary network issue doesn't permanently disable LLM NER
        for the lifetime of the process.
        """
        if cls._ollama_available is True:
            return True

        try:
            client = await cls._get_http_client()
            resp = await client.get("/api/tags", timeout=10.0)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                # Check if our model (or a variant) is available
                base_model = _OLLAMA_MODEL.split(":")[0]
                available = any(base_model in name for name in model_names)
                if available:
                    logger.info("Ollama available at %s with model %s", _OLLAMA_BASE_URL, _OLLAMA_MODEL)
                    cls._ollama_available = True
                    cls._last_ner_failure_reason = None
                else:
                    reason = (
                        f"Ollama joignable mais le modèle '{_OLLAMA_MODEL}' n'est pas chargé. "
                        f"Modèles disponibles: {model_names}. "
                        f"Lancez 'ollama pull {_OLLAMA_MODEL}' sur le serveur Ollama."
                    )
                    logger.warning(
                        "Ollama reachable but model '%s' not found. Available: %s. "
                        "Run 'ollama pull %s' on the host to download it.",
                        _OLLAMA_MODEL, model_names, _OLLAMA_MODEL,
                    )
                    cls._last_ner_failure_reason = reason
                    # Don't cache — model might be pulled later
            else:
                reason = f"Ollama a retourné le status HTTP {resp.status_code}"
                logger.warning("Ollama returned status %d", resp.status_code)
                cls._last_ner_failure_reason = reason
        except Exception as e:
            reason = (
                f"Ollama non joignable à {_OLLAMA_BASE_URL}: {e}. "
                f"Vérifiez que le serveur Ollama est démarré et accessible depuis les containers Docker."
            )
            logger.warning(
                "Ollama not reachable at %s: %s. "
                "Falling back to regex-only anonymization for this batch. "
                "Will retry on next request.",
                _OLLAMA_BASE_URL, e,
            )
            cls._last_ner_failure_reason = reason

        return cls._ollama_available is True

    @classmethod
    def get_ner_diagnostic(cls) -> dict:
        """Return diagnostic info about NER availability for user-facing endpoints."""
        return {
            "ollama_reachable": cls._ollama_available is True,
            "ollama_url": _OLLAMA_BASE_URL,
            "ollama_model": _OLLAMA_MODEL,
            "last_ner_produced_entities": cls._last_ner_produced_entities,
            "failure_reason": cls._last_ner_failure_reason,
        }

    @classmethod
    def is_ner_available(cls) -> bool:
        """Check if NER is available (sync wrapper for backward compatibility)."""
        # Optimistic: if we haven't checked yet, assume it might be available
        if cls._ollama_available is None:
            return True
        return cls._ollama_available

    # ── Regex for extracting "interesting" words (potential proper nouns) ──
    _CAPITALIZED_WORD_RE = re.compile(r'\b[A-ZÀ-ÖÙ-Ý][a-zà-öù-ÿ]{2,}(?:\s+[A-ZÀ-ÖÙ-Ý][a-zà-öù-ÿ]{2,})*\b')

    @classmethod
    def _can_skip_llm(cls, text: str, known_originals: set) -> bool:
        """Check if we can skip the LLM call for this text.

        Returns True if all capitalized word sequences (potential proper nouns)
        are either already in the known mappings or in the stoplist.
        This means the LLM would find nothing new — we can just apply
        existing mappings directly and save an API call.
        """
        if not known_originals:
            return False

        # Find all capitalized word sequences (potential proper nouns)
        candidates = cls._CAPITALIZED_WORD_RE.findall(text)
        if not candidates:
            # No capitalized words at all → nothing to anonymize
            return True

        for candidate in candidates:
            candidate_clean = candidate.strip()
            if len(candidate_clean) < _MIN_ENTITY_LENGTH:
                continue
            if candidate_clean.lower() in _STOPLIST_LOWER:
                continue
            if candidate_clean in known_originals:
                continue
            # Check partial matches (e.g., "Jean" is part of "Jean Dupont")
            if any(candidate_clean in orig for orig in known_originals):
                continue
            # Found a capitalized sequence not in mappings or stoplist
            # → might be a new entity, need LLM
            return False

        return True

    @classmethod
    async def _detect_entities_llm(cls, text: str) -> List[Tuple[str, str, int, int]]:
        """Detect entities in a single text using the local LLM via Ollama.

        Returns list of (entity_text, label, start_char, end_char).
        """
        if not text.strip():
            return []

        results = await cls._detect_entities_llm_grouped([text])
        return results[0] if results else []

    @classmethod
    async def _detect_entities_llm_grouped(
        cls,
        texts: List[str],
    ) -> List[List[Tuple[str, str, int, int]]]:
        """Detect entities across multiple texts in a single LLM call.

        Groups texts with delimiters so the LLM processes them all at once,
        paying the system prompt cost only once per group instead of per chunk.
        With 4 chunks per group, this reduces LLM calls by ~75%.

        Returns a list of entity lists, one per input text.
        """
        results: List[List[Tuple[str, str, int, int]]] = [[] for _ in texts]

        if not any(t.strip() for t in texts):
            return results

        # Build the grouped prompt with block delimiters
        if len(texts) == 1:
            user_content = f"Texte à analyser :\n\n{texts[0]}"
        else:
            parts = []
            for i, text in enumerate(texts, 1):
                parts.append(f"--- BLOC {i} ---\n{text}")
            user_content = "Textes à analyser :\n\n" + _CHUNK_SEPARATOR.join(parts)

        client = await cls._get_http_client()

        try:
            # NOTE: Do NOT use "format": "json" — it forces some models (Qwen,
            # Gemma) to wrap output in a root JSON *object* (e.g. {"entities":
            # [...]}) instead of the plain array the prompt asks for. The prompt
            # already instructs the model to reply with a JSON array.
            resp = await client.post(
                "/api/chat",
                json={
                    "model": _OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _NER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 4096,
                    },
                },
            )
            resp.raise_for_status()
            result = resp.json()
            raw_content = result.get("message", {}).get("content", "[]")

            logger.info(
                "[NER-LLM] Raw model response (%d chars): %s",
                len(raw_content),
                raw_content[:500],
            )

            entities_data = _parse_llm_json(raw_content)
            if not entities_data:
                logger.warning(
                    "[NER-LLM] Model returned no parseable entities. "
                    "Full raw response (%d chars): %s",
                    len(raw_content), raw_content[:1000],
                )
                cls._last_ner_failure_reason = (
                    f"Le modèle Ollama a répondu mais sans entités exploitables. "
                    f"Réponse brute ({len(raw_content)} chars): {raw_content[:200]}"
                )
                return results

            logger.info("[NER-LLM] Model returned %d raw entities", len(entities_data))
            cls._last_ner_produced_entities = True
            cls._last_ner_failure_reason = None

            for item in entities_data:
                entity_text = item.get("text", "").strip()
                entity_type = item.get("type", "").lower().strip()
                # Default to block 1 for single-text mode
                block_num = item.get("block", 1)

                if not entity_text or not entity_type:
                    logger.debug("[NER-LLM] Skipped empty entity: %s", item)
                    continue
                if entity_type not in LABEL_TO_ENTITY_TYPE:
                    logger.warning(
                        "[NER-LLM] Unknown entity type '%s' for '%s' — add it to LABEL_TO_ENTITY_TYPE?",
                        entity_type, entity_text,
                    )
                    continue
                if not _should_keep_entity(entity_text, entity_type):
                    logger.debug("[NER-LLM] Filtered out entity '%s' (type=%s)", entity_text, entity_type)
                    continue

                # Determine which text(s) this entity belongs to
                if len(texts) == 1:
                    target_indices = [0]
                elif isinstance(block_num, int) and 1 <= block_num <= len(texts):
                    target_indices = [block_num - 1]
                else:
                    # Block not specified or invalid — search all texts
                    target_indices = list(range(len(texts)))

                for text_idx in target_indices:
                    text = texts[text_idx]
                    start = 0
                    while True:
                        idx = text.find(entity_text, start)
                        if idx == -1:
                            break
                        results[text_idx].append(
                            (entity_text, entity_type, idx, idx + len(entity_text))
                        )
                        start = idx + len(entity_text)

            # Deduplicate per text
            for text_idx in range(len(texts)):
                seen = set()
                unique = []
                for e in results[text_idx]:
                    key = (e[0], e[2])
                    if key not in seen:
                        seen.add(key)
                        unique.append(e)
                unique.sort(key=lambda x: x[2])
                results[text_idx] = unique

            return results

        except httpx.TimeoutException:
            reason = f"Ollama NER timeout après {_OLLAMA_TIMEOUT}s sur {len(texts)} texte(s)"
            logger.warning("[NER-LLM] %s", reason)
            cls._last_ner_failure_reason = reason
            cls._last_ner_produced_entities = False
            return results
        except httpx.HTTPStatusError as e:
            reason = f"Ollama HTTP error: {e.response.status_code} — {e.response.text[:300]}"
            logger.warning("[NER-LLM] %s", reason)
            cls._last_ner_failure_reason = reason
            cls._last_ner_produced_entities = False
            return results
        except Exception as e:
            reason = f"NER LLM call failed: {type(e).__name__}: {e}"
            logger.error("[NER-LLM] %s", reason, exc_info=True)
            cls._last_ner_failure_reason = reason
            cls._last_ner_produced_entities = False
            return results

    @classmethod
    async def _batch_detect_entities(
        cls,
        texts: List[str],
        progress_callback=None,
        known_originals: Optional[set] = None,
    ) -> List[List[Tuple[str, str, int, int]]]:
        """Detect entities across multiple texts using the LLM.

        Optimizations applied:
        1. Smart cache: chunks where all proper nouns are already known are
           skipped (no LLM call needed).
        2. Chunk grouping: remaining chunks are grouped N-at-a-time into
           single LLM calls, reducing total calls by ~75%.
        3. Concurrency: groups are processed concurrently via semaphore.

        Falls back to regex-only if Ollama is unavailable.
        """
        results: List[List[Tuple[str, str, int, int]]] = [[] for _ in texts]
        known = known_originals or set()

        ollama_ok = await cls._check_ollama()

        if ollama_ok:
            # ── Step 1: Identify which chunks need LLM analysis ──
            needs_llm: List[int] = []  # indices of chunks that need LLM
            skipped_count = 0

            for idx, text in enumerate(texts):
                if cls._can_skip_llm(text, known):
                    skipped_count += 1
                else:
                    needs_llm.append(idx)

            if skipped_count > 0:
                logger.info(
                    "[batch_detect] Smart cache: skipped %d/%d chunks (all entities already known)",
                    skipped_count, len(texts),
                )

            # ── Step 2: Group remaining chunks into batches of N ──
            groups: List[List[int]] = []
            for i in range(0, len(needs_llm), _CHUNKS_PER_GROUP):
                groups.append(needs_llm[i:i + _CHUNKS_PER_GROUP])

            total_groups = len(groups)
            logger.info(
                "[batch_detect] Processing %d chunks in %d LLM calls (group size=%d, skipped=%d)",
                len(needs_llm), total_groups, _CHUNKS_PER_GROUP, skipped_count,
            )

            # ── Step 3: Process groups concurrently ──
            semaphore = asyncio.Semaphore(_OLLAMA_CONCURRENCY)
            done_groups = 0

            async def _process_group(group_indices: List[int]):
                nonlocal done_groups
                async with semaphore:
                    group_texts = [texts[idx] for idx in group_indices]
                    group_results = await cls._detect_entities_llm_grouped(group_texts)
                    for i, idx in enumerate(group_indices):
                        results[idx] = group_results[i]
                    done_groups += 1
                    if progress_callback:
                        # Report progress based on chunks done
                        chunks_done = skipped_count + min(
                            done_groups * _CHUNKS_PER_GROUP, len(needs_llm)
                        )
                        progress_callback(chunks_done, len(texts))

            tasks = [_process_group(group) for group in groups]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Final progress report
            if progress_callback:
                progress_callback(len(texts), len(texts))

            total_entities = sum(len(r) for r in results)
            logger.info(
                "[batch_detect] LLM NER done: %d entities across %d texts "
                "(%d LLM calls, %d skipped via cache)",
                total_entities, len(texts), total_groups, skipped_count,
            )
            if total_entities == 0 and total_groups > 0:
                logger.warning(
                    "[batch_detect] WARNING: %d LLM calls made but 0 entities detected. "
                    "This may indicate the model is not responding correctly. "
                    "Last failure reason: %s",
                    total_groups, cls._last_ner_failure_reason,
                )
                cls._last_ner_produced_entities = False
        else:
            logger.warning(
                "[batch_detect] Ollama unavailable — using regex-only fallback. "
                "NER entities (company names, person names, etc.) will NOT be detected. "
                "Reason: %s",
                cls._last_ner_failure_reason,
            )
            cls._last_ner_produced_entities = False
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

        # Safety-net: apply all known mappings by string replacement
        # to catch anything the LLM missed.
        for original, mapping in sorted(
            existing_mappings.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if original and mapping.is_active:
                result = result.replace(original, mapping.anonymized_value)

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

        # Build set of known original values for the smart cache
        known_originals = set(existing_mappings.keys())

        # Batch NER across all texts (smart cache + chunk grouping + concurrency)
        all_entities = await cls._batch_detect_entities(
            texts, progress_callback, known_originals=known_originals,
        )

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

            # Second pass: apply ALL known mappings by string replacement.
            # This catches entities in chunks that were skipped by the smart
            # cache (no LLM call) or that the LLM missed. Longest-first
            # prevents partial replacements (e.g., "Jean" inside "Jean Dupont").
            for original, mapping in sorted(
                existing_mappings.items(), key=lambda x: len(x[0]), reverse=True
            ):
                if original and mapping.is_active:
                    result = result.replace(original, mapping.anonymized_value)

            results.append(result)

        await db.flush()
        return results

    # Regex matching any placeholder the AI might generate: [WORD_N] or [WORD_WORD_N]
    # Catches BOTH our known prefixes (ENTREPRISE_1) AND arbitrary ones invented by
    # the AI (FILIALE_1, VILLE_SIEGE, NOMBRE_EMPLOYES, CLIENT_1, etc.).
    _PLACEHOLDER_RE = re.compile(
        r'\[([A-ZÀ-Ü][A-ZÀ-Ü0-9_]*_\d+)\]'
    )

    @classmethod
    def find_unknown_placeholders(cls, text: str, known_placeholders: set) -> set:
        """Find all [PREFIX_N] placeholders in text that have no known mapping."""
        all_found = set(f"[{m}]" for m in cls._PLACEHOLDER_RE.findall(text))
        return all_found - known_placeholders

    # Generic replacement terms for AI-invented placeholders, keyed by prefix.
    _GENERIC_TERMS: Dict[str, str] = {
        "ENTREPRISE": "l'entreprise",
        "PERSONNE": "le responsable",
        "SOLUTION": "la solution proposée",
        "EMAIL": "l'adresse de contact",
        "TELEPHONE": "le numéro de contact",
        "ADRESSE": "l'adresse indiquée",
        "CODE_PROJET": "le projet",
        "CODE_AO": "l'appel d'offres",
        "DATE": "la date prévue",
        "MONTANT": "le montant",
        "ENTITE": "l'entité concernée",
        # Common AI-invented prefixes (Mistral tends to generate these)
        "FILIALE": "la filiale",
        "CLIENT": "le client",
        "VILLE": "la ville",
        "VILLE_SIEGE": "la ville",
        "NOMBRE_EMPLOYES": "le nombre d'employés",
        "NOMBRE": "le nombre indiqué",
        "SOCIETE": "la société",
        "GROUPE": "le groupe",
        "SIEGE": "le siège",
        "PROJET": "le projet",
        "NOM": "le nom",
        "PRENOM": "le prénom",
        "REFERENCE": "la référence",
        "REF": "la référence",
        "MARCHE": "le marché",
        "BUDGET": "le budget",
        "EFFECTIF": "l'effectif",
        "CHIFFRE_AFFAIRES": "le chiffre d'affaires",
        "CA": "le chiffre d'affaires",
        "SITE": "le site",
        "REGION": "la région",
        "PAYS": "le pays",
        "CONTACT": "le contact",
        "RESPONSABLE": "le responsable",
        "DIRECTEUR": "le directeur",
        "INTERLOCUTEUR": "l'interlocuteur",
    }

    @classmethod
    def strip_invented_placeholders(cls, text: str, known_placeholders: set) -> str:
        """Replace AI-invented placeholders with generic French terms.

        When Mistral invents a new placeholder (e.g. [ENTREPRISE_2], [FILIALE_1],
        [VILLE_SIEGE], etc.) that does not exist in our mappings, replace it with
        a generic term instead of leaving an unresolved placeholder in the output.
        """
        unknown = cls.find_unknown_placeholders(text, known_placeholders)
        if not unknown:
            return text

        for token in unknown:
            inner = token.strip("[]")
            prefix = inner.rsplit("_", 1)[0]
            generic = cls._GENERIC_TERMS.get(prefix, "l'entité concernée")
            text = text.replace(token, generic)
            logger.info(
                "[deanonymize] Stripped AI-invented placeholder %s → '%s'", token, generic,
            )

        return text

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

        # Replace known placeholders with their real values
        for placeholder, original in mappings.items():
            if original:
                result = result.replace(placeholder, original)

        # Strip any AI-invented placeholders that we don't know about —
        # replace them with generic terms instead of creating orphan mappings.
        result = cls.strip_invented_placeholders(result, set(mappings.keys()))

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
    """Parse JSON from LLM response, handling common formatting issues.

    Models (especially with/without ``format: json``) may return:
    - A plain JSON array:  ``[{...}, ...]``
    - A wrapper object:    ``{"entities": [...]}``
    - An object with *any* key whose value is a list of dicts
    - Markdown fences around JSON
    - Text before/after the JSON payload
    """
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
            return data if data else None
        # Models often wrap the array in a dict — check well-known keys first,
        # then fall back to *any* key whose value is a list of dicts.
        if isinstance(data, dict):
            # Well-known keys
            for key in ("entities", "results", "data", "items", "entités",
                         "entites", "named_entities", "response"):
                if key in data and isinstance(data[key], list):
                    return data[key] if data[key] else None
            # Fallback: take the first list-of-dicts value we find
            for val in data.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    logger.info(
                        "[_parse_llm_json] Found entities under unexpected key in dict: %s",
                        list(data.keys()),
                    )
                    return val
            # Empty dict or dict with no list values
            logger.warning(
                "[_parse_llm_json] Parsed valid JSON dict but no entity list found. "
                "Keys: %s. Full response: %s",
                list(data.keys()), text[:500],
            )
        return None
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from the response (model may add text around it)
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed if parsed else None
        except json.JSONDecodeError:
            pass

    # Try to extract a JSON object that wraps an array
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        return val
        except json.JSONDecodeError:
            pass

    logger.warning(
        "[_parse_llm_json] Could not parse any JSON from response (%d chars): %s",
        len(text), text[:500],
    )

    return None

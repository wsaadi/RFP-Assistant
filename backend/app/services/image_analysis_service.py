"""Image analysis service using configurable Vision LLM providers.

Architecture (privacy-by-design):
1. Images extracted from documents are sent to the configured vision model
2. The vision model generates structured metadata: description, type, key info, PII detection
3. OCR text extracted from images is anonymized using the existing anonymization pipeline
4. Mistral receives ONLY the anonymized metadata — never the original images
5. Original images are inserted into the final Word document based on Mistral's placement markers

Supported providers:
- **Ollama** (local): Privacy-first — images never leave local infrastructure
- **Mistral** (cloud): Uses Pixtral vision models via Mistral API
- **Scaleway** (cloud): Uses Scaleway Generative APIs (OpenAI-compatible)
"""
import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Callable, Dict, List, Optional

import httpx

from ..config import settings
from . import image_providers

logger = logging.getLogger(__name__)

# ── Default Vision configuration (from environment, used when no DB config) ──
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", settings.ollama_vision_model)
_VISION_TIMEOUT = int(os.environ.get("OLLAMA_VISION_TIMEOUT", str(settings.ollama_vision_timeout)))
_VISION_CONCURRENCY = int(os.environ.get("OLLAMA_VISION_CONCURRENCY", str(settings.ollama_vision_concurrency)))

# ── Vision analysis prompts ──
_VISION_SYSTEM_PROMPT = """\
Tu es un analyseur d'images de documents professionnels (appels d'offres, mémoires techniques).
Tu réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après."""

_VISION_USER_PROMPT = """\
Analyse cette image et réponds uniquement avec un JSON au format suivant :

{{
  "type": "<diagramme|graphique|tableau|capture_ecran|photo|logo|schema_technique|carte|illustration|autre>",
  "description": "<description factuelle de ce que tu vois, 2-4 phrases>",
  "key_information": ["<données clés visibles : chiffres, technologies, métriques>"],
  "pii_detected": [{{"type": "person|email|phone|address", "value": "<valeur exacte lue>"}}],
  "ocr_text": "<tout texte lisible dans l'image, transcrit fidèlement>",
  "suggested_usage": "<section pertinente : architecture technique, méthodologie, équipe, références, etc>",
  "is_informative": true
}}

Règles :
- pii_detected : UNIQUEMENT noms de personnes, emails, téléphones, adresses. PAS les noms d'entreprises/produits.
- is_informative : false si l'image est purement décorative (logo générique, séparateur, icône).
- Décris ce que tu VOIS, pas ce que tu devines.
- Réponds UNIQUEMENT avec le JSON."""


class ImageAnalysisService:
    """Analyze document images using a configurable Vision LLM provider.

    Supports Ollama (local), Mistral API, and Scaleway Generative API.
    """

    _semaphore: Optional[asyncio.Semaphore] = None
    _http_client: Optional[httpx.AsyncClient] = None

    # ── Active provider configuration ──
    _vision_config: Optional[image_providers.ProviderConfig] = None

    @classmethod
    def configure_vision(cls, config: image_providers.ProviderConfig):
        """Set the vision provider configuration.

        Resets the semaphore to apply new concurrency settings.
        """
        cls._vision_config = config
        cls._semaphore = None  # Reset to pick up new concurrency
        logger.info(
            "Vision provider configured: %s / model=%s",
            config.provider, config.model,
        )

    @classmethod
    def _get_vision_config(cls) -> image_providers.ProviderConfig:
        """Get the active vision config, falling back to env-var defaults."""
        if cls._vision_config is not None:
            return cls._vision_config
        return image_providers.ProviderConfig(
            provider="ollama",
            model=_VISION_MODEL,
            ollama_base_url=_OLLAMA_BASE_URL,
            timeout=_VISION_TIMEOUT,
            concurrency=_VISION_CONCURRENCY,
        )

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        """Lazy-init semaphore (must be created inside an event loop)."""
        if cls._semaphore is None:
            cfg = cls._get_vision_config()
            concurrency = cfg.concurrency if cfg.concurrency > 0 else _VISION_CONCURRENCY
            cls._semaphore = asyncio.Semaphore(concurrency)
        return cls._semaphore

    @classmethod
    def _get_http_client(cls) -> httpx.AsyncClient:
        """Get or create a reusable async HTTP client for Ollama vision."""
        if cls._http_client is None or cls._http_client.is_closed:
            cls._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(_VISION_TIMEOUT, connect=30),
            )
        return cls._http_client

    @staticmethod
    def _image_to_base64(file_path: str) -> Optional[str]:
        """Read an image file and return its base64-encoded content."""
        try:
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error("Failed to read image %s: %s", file_path, e)
            return None

    @classmethod
    async def analyze_image(
        cls,
        file_path: str,
        page_context: str = "",
        section_title: str = "",
    ) -> Dict:
        """Analyze a single image using the configured vision provider.

        Args:
            file_path: Path to the image file on disk.
            page_context: Surrounding text from the document page.
            section_title: Section/heading the image appears under.

        Returns:
            Structured analysis dict with description, type, PII, etc.
        """
        image_b64 = cls._image_to_base64(file_path)
        if not image_b64:
            return cls._empty_analysis("Impossible de lire le fichier image")

        # Build the user prompt with context appended
        user_prompt = _VISION_USER_PROMPT
        if section_title or page_context:
            ctx_parts = []
            if section_title:
                ctx_parts.append(f"Section du document : {section_title}")
            if page_context:
                ctx_parts.append(f"Texte environnant : {page_context[:500]}")
            user_prompt += "\n\nContexte :\n" + "\n".join(ctx_parts)

        # Call vision API with concurrency control
        sem = cls._get_semaphore()
        async with sem:
            try:
                result = await cls._call_vision(image_b64, user_prompt)
                return result
            except Exception as e:
                logger.error("Vision analysis failed for %s: %s", file_path, e)
                return cls._empty_analysis(f"Erreur d'analyse: {str(e)[:100]}")

    @classmethod
    async def analyze_images_batch(
        cls,
        images_data: List[Dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        """Analyze multiple images concurrently with progress tracking.

        Args:
            images_data: List of dicts with keys: file_path, context, section_title
            progress_callback: Optional callback(done, total) for progress reporting.

        Returns:
            List of analysis results in the same order as input.
        """
        total = len(images_data)
        if total == 0:
            return []

        cfg = cls._get_vision_config()
        logger.info(
            "Starting batch image analysis: %d images (provider=%s, model=%s)",
            total, cfg.provider, cfg.model,
        )
        results = [None] * total
        done_count = 0

        async def _analyze_one(idx: int, img: Dict):
            nonlocal done_count
            r = await cls.analyze_image(
                file_path=img["file_path"],
                page_context=img.get("context", ""),
                section_title=img.get("section_title", ""),
            )
            results[idx] = r
            done_count += 1
            if progress_callback:
                progress_callback(done_count, total)

        # Launch all analyses concurrently (semaphore controls parallelism)
        tasks = [
            asyncio.create_task(_analyze_one(i, img))
            for i, img in enumerate(images_data)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Replace any None results (from exceptions) with empty analysis
        for i in range(total):
            if results[i] is None:
                results[i] = cls._empty_analysis("Analyse échouée")

        logger.info("Batch image analysis completed: %d/%d successful",
                     sum(1 for r in results if r.get("type")), total)
        return results

    @classmethod
    async def _call_vision(cls, image_b64: str, user_prompt: str) -> Dict:
        """Call the vision model via the configured provider.

        Uses the image_providers abstraction layer. If the first attempt
        returns no usable JSON, retries once with a simpler prompt.
        """
        cfg = cls._get_vision_config()

        raw_content = await image_providers.call_vision(
            config=cfg,
            system_prompt=_VISION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            image_b64=image_b64,
        )

        if raw_content is None:
            return cls._empty_analysis(
                f"Le provider {cfg.provider} n'a pas retourné de réponse"
            )

        result = cls._parse_vision_response(raw_content)

        if result.get("type") != "autre" or result.get("description", "").startswith("Type:"):
            return result

        # Retry with minimal prompt if model returned garbage/refusal
        logger.info("Vision model returned empty/refusal — retrying with minimal prompt")
        fallback = (
            'Décris cette image en JSON : '
            '{"type":"diagramme|tableau|photo|logo|autre",'
            '"description":"ce que tu vois",'
            '"ocr_text":"texte lisible",'
            '"is_informative":true}'
        )

        raw_retry = await image_providers.call_vision(
            config=cfg,
            system_prompt="",
            user_prompt=fallback,
            image_b64=image_b64,
        )
        if raw_retry is None:
            return result  # Return first attempt result
        return cls._parse_vision_response(raw_retry)

    # Normalize type values — accepts both French (preferred) and English (fallback)
    _TYPE_MAP = {
        # French (expected from llama3.2-vision)
        "diagramme": "diagramme",
        "graphique": "graphique",
        "tableau": "tableau",
        "capture_ecran": "capture_ecran",
        "capture_écran": "capture_ecran",
        "photo": "photo",
        "logo": "logo",
        "schema_technique": "schema_technique",
        "schéma_technique": "schema_technique",
        "carte": "carte",
        "illustration": "illustration",
        "autre": "autre",
        # English fallback (in case model responds in English)
        "diagram": "diagramme",
        "chart": "graphique",
        "table": "tableau",
        "screenshot": "capture_ecran",
        "schema": "schema_technique",
        "map": "carte",
        "other": "autre",
    }

    @classmethod
    def _parse_vision_response(cls, raw: str) -> Dict:
        """Parse the JSON response from the vision model."""
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```")
            text = text.removesuffix("```")
            text = text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from the response
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.warning("Vision response JSON parse failed. Raw: %s", text[:300])
                    return cls._empty_analysis("Réponse JSON invalide du modèle vision")
            else:
                logger.warning("No JSON found in vision response. Raw: %s", text[:300])
                return cls._empty_analysis("Réponse non-JSON du modèle vision")

        # Normalize the type from English to French
        raw_type = str(result.get("type", "other")).lower().strip()
        norm_type = cls._TYPE_MAP.get(raw_type, raw_type)
        # Fallback: if the model returned a French type already, keep it
        valid_fr_types = set(cls._TYPE_MAP.values())
        if norm_type not in valid_fr_types:
            norm_type = "autre"

        return {
            "type": norm_type,
            "description": result.get("description", ""),
            "key_information": result.get("key_information") if isinstance(result.get("key_information"), list) else [],
            "pii_detected": result.get("pii_detected") if isinstance(result.get("pii_detected"), list) else [],
            "ocr_text": result.get("ocr_text", ""),
            "suggested_usage": result.get("suggested_usage", ""),
            "is_informative": bool(result.get("is_informative", True)),
        }

    @staticmethod
    def _empty_analysis(reason: str = "") -> Dict:
        """Return an empty analysis result."""
        return {
            "type": "autre",
            "description": reason or "",
            "key_information": [],
            "pii_detected": [],
            "ocr_text": "",
            "suggested_usage": "",
            "is_informative": False,
        }

    @classmethod
    def build_anonymized_description(cls, analysis: Dict, anonymized_ocr: str = "") -> str:
        """Build an anonymized description from the analysis result.

        This is the text that Mistral will receive instead of the actual image.
        PII detected in the image is replaced with type markers.
        """
        parts = []

        img_type = analysis.get("type", "autre")
        description = analysis.get("description", "")
        key_info = analysis.get("key_information", [])
        pii_list = analysis.get("pii_detected", [])
        suggested = analysis.get("suggested_usage", "")

        # Replace PII in description
        anonymized_desc = description
        for pii in pii_list:
            pii_value = pii.get("value", "")
            pii_type = pii.get("type", "")
            if pii_value and len(pii_value) > 2:
                placeholder = f"[{pii_type.upper()}_REDACTED]"
                anonymized_desc = anonymized_desc.replace(pii_value, placeholder)

        parts.append(f"Type: {img_type}")
        if anonymized_desc:
            parts.append(f"Description: {anonymized_desc}")
        if key_info:
            # Also anonymize key information
            clean_info = []
            for info in key_info:
                clean = info
                for pii in pii_list:
                    pii_value = pii.get("value", "")
                    if pii_value and len(pii_value) > 2:
                        clean = clean.replace(pii_value, f"[{pii.get('type', '').upper()}_REDACTED]")
                clean_info.append(clean)
            parts.append(f"Informations clés: {', '.join(clean_info)}")
        if anonymized_ocr:
            parts.append(f"Texte extrait (anonymisé): {anonymized_ocr[:500]}")
        if suggested:
            parts.append(f"Usage suggéré: {suggested}")

        return " | ".join(parts)

    @classmethod
    async def check_vision_model_available(cls) -> Dict:
        """Check if the vision model is available on the configured provider."""
        cfg = cls._get_vision_config()
        result = await image_providers.check_provider_available(cfg)

        # Backward-compatible response format
        return {
            "vision_provider": cfg.provider,
            "ollama_reachable": result.get("available", False) if cfg.provider == "ollama" else None,
            "vision_model": cfg.model,
            "vision_available": result.get("available", False),
            "available_models": result.get("models_list", []),
            "failure_reason": result.get("reason", ""),
        }

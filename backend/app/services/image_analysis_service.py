"""Image analysis service using a local Vision LLM (Llama 3.2 Vision via Ollama) on DGX Spark.

Architecture (privacy-by-design):
1. Images extracted from documents are sent to a LOCAL vision model (never to Mistral)
2. The vision model generates structured metadata: description, type, key info, PII detection
3. OCR text extracted from images is anonymized using the existing anonymization pipeline
4. Mistral receives ONLY the anonymized metadata — never the original images
5. Original images are inserted into the final Word document based on Mistral's placement markers

This ensures that sensitive visual content (names, emails, screenshots with PII) never
leaves the local infrastructure while still allowing intelligent image placement.
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

logger = logging.getLogger(__name__)

# ── Ollama Vision configuration ──
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", settings.ollama_vision_model)
_VISION_TIMEOUT = int(os.environ.get("OLLAMA_VISION_TIMEOUT", str(settings.ollama_vision_timeout)))
_VISION_CONCURRENCY = int(os.environ.get("OLLAMA_VISION_CONCURRENCY", str(settings.ollama_vision_concurrency)))

# ── Vision analysis prompts ──
# Llama 3.2 Vision supports system messages and handles French natively.
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
    """Analyze document images using a local Vision LLM via Ollama.

    The vision model runs on the DGX Spark, ensuring images never leave
    the local infrastructure. Only structured metadata is produced and
    later shared with external AI models.
    """

    _semaphore: Optional[asyncio.Semaphore] = None
    _http_client: Optional[httpx.AsyncClient] = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        """Lazy-init semaphore (must be created inside an event loop)."""
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(_VISION_CONCURRENCY)
        return cls._semaphore

    @classmethod
    def _get_http_client(cls) -> httpx.AsyncClient:
        """Get or create a reusable async HTTP client for Ollama vision."""
        if cls._http_client is None or cls._http_client.is_closed:
            cls._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(_VISION_TIMEOUT, connect=30),
            )
        return cls._http_client

    @classmethod
    def _reset(cls):
        """Reset cached state for a fresh event loop.

        Must be called at the start of each Celery task to avoid reusing
        asyncio primitives (Semaphore, HTTP client) from a previous
        (now-closed) event loop created by ``asyncio.run()``.
        """
        cls._semaphore = None
        cls._http_client = None

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
        """Analyze a single image using the local vision model.

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

        # Call Ollama vision API with concurrency control
        sem = cls._get_semaphore()
        async with sem:
            try:
                result = await cls._call_ollama_vision(image_b64, user_prompt)
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

        logger.info("Starting batch image analysis: %d images", total)
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
    async def _call_ollama_vision(cls, image_b64: str, user_prompt: str) -> Dict:
        """Call the Ollama vision model API with an image.

        Ollama's vision API accepts images as base64-encoded strings in the
        ``images`` field of the message payload.

        Llama 3.2 Vision supports system messages natively. If the first
        attempt returns no usable JSON, we retry once with a simpler prompt.
        """
        result = await cls._call_ollama_once(image_b64, user_prompt, use_system=True)
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
        return await cls._call_ollama_once(image_b64, fallback, use_system=False)

    # Max retries for transient Ollama errors (model swap, server disconnect)
    _MAX_RETRIES = 2

    @classmethod
    async def _call_ollama_once(
        cls, image_b64: str, user_prompt: str, use_system: bool = True,
    ) -> Dict:
        """Single call to the Ollama vision API with retry on transient errors.

        Retries with exponential backoff when Ollama disconnects (common when
        the GPU is swapping between NER and vision models).
        """
        messages = []
        if use_system:
            messages.append({"role": "system", "content": _VISION_SYSTEM_PROMPT})
        messages.append({
            "role": "user",
            "content": user_prompt,
            "images": [image_b64],
        })

        payload = {
            "model": _VISION_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 2048,
            },
        }

        client = cls._get_http_client()
        last_exc = None

        for attempt in range(1 + cls._MAX_RETRIES):
            try:
                resp = await client.post(f"{_OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_content = data.get("message", {}).get("content", "")
                return cls._parse_vision_response(raw_content)
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
                last_exc = e
                if attempt < cls._MAX_RETRIES:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    logger.warning(
                        "Vision call attempt %d/%d failed (%s), retrying in %ds",
                        attempt + 1, 1 + cls._MAX_RETRIES, type(e).__name__, wait,
                    )
                    await asyncio.sleep(wait)

        raise last_exc

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
        """Check if the vision model is available on Ollama."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
                resp = await client.get(f"{_OLLAMA_BASE_URL}/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Check if our vision model is available
                vision_available = any(
                    _VISION_MODEL.split(":")[0] in name
                    for name in model_names
                )

                return {
                    "ollama_reachable": True,
                    "vision_model": _VISION_MODEL,
                    "vision_available": vision_available,
                    "available_models": model_names,
                }
        except httpx.ConnectError:
            return {
                "ollama_reachable": False,
                "vision_model": _VISION_MODEL,
                "vision_available": False,
                "failure_reason": f"Cannot connect to Ollama at {_OLLAMA_BASE_URL}",
            }
        except Exception as e:
            return {
                "ollama_reachable": False,
                "vision_model": _VISION_MODEL,
                "vision_available": False,
                "failure_reason": str(e)[:200],
            }

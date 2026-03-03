"""Abstraction layer for image processing providers (NER and Vision).

Supports three providers:
- **Ollama** (local): Sends requests to a local Ollama server via its /api/chat endpoint.
- **Mistral** (cloud): Uses Mistral's chat completions API. Vision uses Pixtral models.
- **Scaleway** (cloud): Uses Scaleway Generative APIs (OpenAI-compatible endpoint).

Each provider implements the same interface for NER (text-only chat completion)
and Vision (chat completion with base64 image).
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Default configuration from environment ──
_DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
_DEFAULT_SCALEWAY_URL = "https://api.scaleway.ai/v1"
_DEFAULT_MISTRAL_URL = "https://api.mistral.ai/v1"


@dataclass
class ProviderConfig:
    """Configuration for an image processing provider."""
    provider: str = "ollama"  # "ollama", "mistral", "scaleway"
    model: str = ""
    # Ollama
    ollama_base_url: str = _DEFAULT_OLLAMA_URL
    # Mistral
    mistral_api_key: str = ""
    # Scaleway
    scaleway_api_key: str = ""
    scaleway_base_url: str = _DEFAULT_SCALEWAY_URL
    # Timeouts
    timeout: int = 120
    concurrency: int = 2


def ner_config_from_ai_config(ai_config) -> ProviderConfig:
    """Build a ProviderConfig for NER from an AIConfig database object."""
    return ProviderConfig(
        provider=getattr(ai_config, "ner_provider", "ollama") or "ollama",
        model=getattr(ai_config, "ner_model", "qwen2.5:14b") or "qwen2.5:14b",
        ollama_base_url=getattr(ai_config, "ollama_base_url", _DEFAULT_OLLAMA_URL) or _DEFAULT_OLLAMA_URL,
        mistral_api_key=getattr(ai_config, "mistral_api_key_encrypted", "") or "",
        scaleway_api_key=getattr(ai_config, "scaleway_api_key_encrypted", "") or "",
        scaleway_base_url=getattr(ai_config, "scaleway_base_url", _DEFAULT_SCALEWAY_URL) or _DEFAULT_SCALEWAY_URL,
    )


def vision_config_from_ai_config(ai_config) -> ProviderConfig:
    """Build a ProviderConfig for Vision from an AIConfig database object."""
    return ProviderConfig(
        provider=getattr(ai_config, "vision_provider", "ollama") or "ollama",
        model=getattr(ai_config, "vision_model", "llama3.2-vision:11b") or "llama3.2-vision:11b",
        ollama_base_url=getattr(ai_config, "ollama_base_url", _DEFAULT_OLLAMA_URL) or _DEFAULT_OLLAMA_URL,
        mistral_api_key=getattr(ai_config, "mistral_api_key_encrypted", "") or "",
        scaleway_api_key=getattr(ai_config, "scaleway_api_key_encrypted", "") or "",
        scaleway_base_url=getattr(ai_config, "scaleway_base_url", _DEFAULT_SCALEWAY_URL) or _DEFAULT_SCALEWAY_URL,
    )


# ── Shared HTTP clients (one per provider base URL to reuse connections) ──
_http_clients: Dict[str, httpx.AsyncClient] = {}


def _get_client(base_url: str, timeout: int = 120) -> httpx.AsyncClient:
    """Get or create a reusable async HTTP client for a given base URL."""
    key = base_url
    if key not in _http_clients or _http_clients[key].is_closed:
        _http_clients[key] = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=30),
        )
    return _http_clients[key]


# ── Max retries for transient errors ──
_MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# NER (text-only chat completion)
# ---------------------------------------------------------------------------

async def call_ner(
    config: ProviderConfig,
    system_prompt: str,
    user_content: str,
) -> Optional[str]:
    """Call a chat completion endpoint for NER (text-only).

    Returns the raw text response from the model, or None on failure.
    """
    if config.provider == "ollama":
        return await _call_ollama_chat(config, system_prompt, user_content)
    elif config.provider == "mistral":
        return await _call_openai_compatible_chat(
            base_url=_DEFAULT_MISTRAL_URL,
            api_key=config.mistral_api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_content=user_content,
            timeout=config.timeout,
            provider_name="Mistral",
        )
    elif config.provider == "scaleway":
        return await _call_openai_compatible_chat(
            base_url=config.scaleway_base_url,
            api_key=config.scaleway_api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_content=user_content,
            timeout=config.timeout,
            provider_name="Scaleway",
        )
    else:
        logger.error("Unknown NER provider: %s", config.provider)
        return None


# ---------------------------------------------------------------------------
# Vision (chat completion with image)
# ---------------------------------------------------------------------------

async def call_vision(
    config: ProviderConfig,
    system_prompt: str,
    user_prompt: str,
    image_b64: str,
) -> Optional[str]:
    """Call a vision model endpoint with an image.

    Returns the raw text response from the model, or None on failure.
    """
    if config.provider == "ollama":
        return await _call_ollama_vision(config, system_prompt, user_prompt, image_b64)
    elif config.provider == "mistral":
        return await _call_openai_compatible_vision(
            base_url=_DEFAULT_MISTRAL_URL,
            api_key=config.mistral_api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_b64=image_b64,
            timeout=config.timeout,
            provider_name="Mistral",
        )
    elif config.provider == "scaleway":
        return await _call_openai_compatible_vision(
            base_url=config.scaleway_base_url,
            api_key=config.scaleway_api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_b64=image_b64,
            timeout=config.timeout,
            provider_name="Scaleway",
        )
    else:
        logger.error("Unknown vision provider: %s", config.provider)
        return None


# ---------------------------------------------------------------------------
# Provider availability checks
# ---------------------------------------------------------------------------

async def check_provider_available(config: ProviderConfig) -> Dict:
    """Check if the configured provider and model are available."""
    if config.provider == "ollama":
        return await _check_ollama_model(config)
    elif config.provider == "mistral":
        return await _check_api_key(config.mistral_api_key, "Mistral", config.model)
    elif config.provider == "scaleway":
        return await _check_api_key(config.scaleway_api_key, "Scaleway", config.model)
    return {"available": False, "reason": f"Provider inconnu: {config.provider}"}


async def _check_ollama_model(config: ProviderConfig) -> Dict:
    """Check if an Ollama model is available."""
    try:
        client = _get_client(config.ollama_base_url, timeout=10)
        resp = await client.get(f"{config.ollama_base_url}/api/tags", timeout=10.0)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        base_model = config.model.split(":")[0]
        available = any(base_model in name for name in model_names)
        return {
            "available": available,
            "provider": "ollama",
            "model": config.model,
            "models_list": model_names,
            "reason": "" if available else f"Modèle '{config.model}' non trouvé. Disponibles: {model_names}",
        }
    except Exception as e:
        return {
            "available": False,
            "provider": "ollama",
            "model": config.model,
            "reason": f"Ollama non joignable à {config.ollama_base_url}: {e}",
        }


async def _check_api_key(api_key: str, provider_name: str, model: str) -> Dict:
    """Check if an API key is configured."""
    if api_key:
        return {
            "available": True,
            "provider": provider_name.lower(),
            "model": model,
            "reason": "",
        }
    return {
        "available": False,
        "provider": provider_name.lower(),
        "model": model,
        "reason": f"Clé API {provider_name} non configurée",
    }


# ---------------------------------------------------------------------------
# Ollama implementations
# ---------------------------------------------------------------------------

async def _call_ollama_chat(
    config: ProviderConfig,
    system_prompt: str,
    user_content: str,
) -> Optional[str]:
    """Call Ollama /api/chat for text-only chat completion."""
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 4096},
    }
    client = _get_client(config.ollama_base_url, config.timeout)
    return await _ollama_post_with_retry(
        client, f"{config.ollama_base_url}/api/chat", payload, config.timeout,
    )


async def _call_ollama_vision(
    config: ProviderConfig,
    system_prompt: str,
    user_prompt: str,
    image_b64: str,
) -> Optional[str]:
    """Call Ollama /api/chat with an image for vision analysis."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": user_prompt,
        "images": [image_b64],
    })

    payload = {
        "model": config.model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
    }
    client = _get_client(config.ollama_base_url, config.timeout)
    return await _ollama_post_with_retry(
        client, f"{config.ollama_base_url}/api/chat", payload, config.timeout,
    )


async def _ollama_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    timeout: int,
) -> Optional[str]:
    """POST to Ollama with retry on transient errors."""
    last_exc = None
    for attempt in range(1 + _MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Ollama call attempt %d/%d failed (%s), retrying in %ds",
                    attempt + 1, 1 + _MAX_RETRIES, type(e).__name__, wait,
                )
                await asyncio.sleep(wait)
    if last_exc:
        raise last_exc
    return None


# ---------------------------------------------------------------------------
# OpenAI-compatible implementations (Mistral & Scaleway)
# ---------------------------------------------------------------------------

async def _call_openai_compatible_chat(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_content: str,
    timeout: int = 120,
    provider_name: str = "API",
) -> Optional[str]:
    """Call an OpenAI-compatible chat completion endpoint (text-only)."""
    if not api_key:
        logger.error("%s API key not configured for NER", provider_name)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    client = _get_client(base_url, timeout)
    url = f"{base_url}/chat/completions"

    last_exc = None
    for attempt in range(1 + _MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "%s chat call attempt %d/%d failed (%s), retrying in %ds",
                    provider_name, attempt + 1, 1 + _MAX_RETRIES,
                    type(e).__name__, wait,
                )
                await asyncio.sleep(wait)
        except httpx.HTTPStatusError as e:
            logger.error(
                "%s API error: %d — %s",
                provider_name, e.response.status_code, e.response.text[:300],
            )
            return None

    if last_exc:
        raise last_exc
    return None


async def _call_openai_compatible_vision(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_b64: str,
    timeout: int = 120,
    provider_name: str = "API",
) -> Optional[str]:
    """Call an OpenAI-compatible chat completion endpoint with a vision image."""
    if not api_key:
        logger.error("%s API key not configured for vision", provider_name)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": user_prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_b64}",
                },
            },
        ],
    })

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2048,
    }

    client = _get_client(base_url, timeout)
    url = f"{base_url}/chat/completions"

    last_exc = None
    for attempt in range(1 + _MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "%s vision call attempt %d/%d failed (%s), retrying in %ds",
                    provider_name, attempt + 1, 1 + _MAX_RETRIES,
                    type(e).__name__, wait,
                )
                await asyncio.sleep(wait)
        except httpx.HTTPStatusError as e:
            logger.error(
                "%s vision API error: %d — %s",
                provider_name, e.response.status_code, e.response.text[:300],
            )
            return None

    if last_exc:
        raise last_exc
    return None

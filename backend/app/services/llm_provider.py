"""LLM provider abstraction for NER (anonymization) and Vision (image analysis).

Supports three providers:
- **ollama**: Local Ollama server (default) — data stays on-premises
- **mistral**: Mistral AI cloud API (OpenAI-compatible)
- **scaleway**: Scaleway Generative APIs (OpenAI-compatible, EU-hosted)

Both Mistral and Scaleway use the OpenAI chat completions format, so they
share the same calling logic.  Ollama uses its own ``/api/chat`` format.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Default timeout for API calls (seconds)
_DEFAULT_TIMEOUT = 300
_MAX_RETRIES = 4
_RATE_LIMIT_STATUSES = (429, 503)


@dataclass
class LLMResponse:
    """Response from an LLM call, including token usage for cost tracking."""
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

# Well-known base URLs (used when the user doesn't override)
PROVIDER_DEFAULTS = {
    "ollama": {"base_url": "http://host.docker.internal:11434"},
    "mistral": {"base_url": "https://api.mistral.ai/v1"},
    "scaleway": {"base_url": "https://api.scaleway.ai/v1"},
}


class ProviderConfig:
    """Configuration for a single LLM call (NER or Vision)."""

    __slots__ = ("provider", "base_url", "api_key", "model", "timeout", "concurrency", "scaleway_project_id")

    def __init__(
        self,
        provider: str = "ollama",
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int = _DEFAULT_TIMEOUT,
        concurrency: int = 2,
        scaleway_project_id: str = "",
    ):
        self.provider = provider
        self.scaleway_project_id = scaleway_project_id.strip() if scaleway_project_id else ""
        self.base_url = base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")
        self.api_key = api_key.strip() if api_key else ""
        self.model = model
        self.timeout = timeout
        self.concurrency = concurrency

    @property
    def is_openai_compatible(self) -> bool:
        return self.provider in ("mistral", "scaleway")


async def call_llm_chat(
    config: ProviderConfig,
    messages: List[Dict],
    temperature: float = 0.0,
    max_tokens: int = 4096,
    client: Optional[httpx.AsyncClient] = None,
) -> LLMResponse:
    """Send a chat completion request and return the assistant's text response with usage.

    Works with Ollama (``/api/chat``) and OpenAI-compatible providers
    (``/v1/chat/completions``).

    Retries on transient network errors with exponential backoff.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(config.timeout, connect=30))

    try:
        return await _call_with_retries(config, messages, temperature, max_tokens, client)
    finally:
        if own_client:
            await client.aclose()


async def call_llm_vision(
    config: ProviderConfig,
    image_b64: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    client: Optional[httpx.AsyncClient] = None,
    use_system: bool = True,
) -> LLMResponse:
    """Send a vision request (image + text) and return the assistant's response with usage.

    Handles the different image formats between Ollama and OpenAI-compatible APIs.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(config.timeout, connect=30))

    try:
        messages = _build_vision_messages(
            config, image_b64, system_prompt, user_prompt, use_system,
        )
        return await _call_with_retries(config, messages, temperature, max_tokens, client)
    finally:
        if own_client:
            await client.aclose()


def _build_vision_messages(
    config: ProviderConfig,
    image_b64: str,
    system_prompt: str,
    user_prompt: str,
    use_system: bool,
) -> List[Dict]:
    """Build the messages array for a vision request."""
    messages = []

    if use_system and system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if config.is_openai_compatible:
        # OpenAI format: content is a list with text + image_url
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
            ],
        })
    else:
        # Ollama format: images field in the message
        messages.append({
            "role": "user",
            "content": user_prompt,
            "images": [image_b64],
        })

    return messages


async def _call_with_retries(
    config: ProviderConfig,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    client: httpx.AsyncClient,
) -> LLMResponse:
    """Call the appropriate API endpoint with retry logic.

    Retries on:
    - Transient network errors (connect, read, protocol)
    - Rate-limit responses (429) and server overload (503)
      Uses Retry-After header when available, otherwise exponential backoff.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1 + _MAX_RETRIES):
        try:
            if config.is_openai_compatible:
                return await _call_openai_compatible(
                    config, messages, temperature, max_tokens, client,
                )
            else:
                return await _call_ollama(
                    config, messages, temperature, max_tokens, client,
                )
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in _RATE_LIMIT_STATUSES:
                raise  # 400, 401, etc. — don't retry
            last_exc = e
            if attempt < _MAX_RETRIES:
                retry_after = e.response.headers.get("retry-after")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt + 1)
                wait = min(wait, 60)  # cap at 60s
                logger.warning(
                    "LLM rate-limited (%d) attempt %d/%d, retrying in %ds",
                    e.response.status_code, attempt + 1, 1 + _MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError,
                httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "LLM call attempt %d/%d failed (%s: %s), retrying in %ds",
                    attempt + 1, 1 + _MAX_RETRIES, type(e).__name__, str(e)[:100], wait,
                )
                await asyncio.sleep(wait)

    raise last_exc  # type: ignore[misc]


async def _call_openai_compatible(
    config: ProviderConfig,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    client: httpx.AsyncClient,
) -> LLMResponse:
    """Call an OpenAI-compatible chat completions endpoint (Mistral / Scaleway)."""
    url = f"{config.base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code in (401, 403):
        key_hint = f"{config.api_key[:4]}...{config.api_key[-4:]}" if len(config.api_key) > 8 else "(empty/short)"
        logger.error(
            "Auth failed (%d) for %s provider=%s model=%s key=%s",
            resp.status_code, url, config.provider, config.model, key_hint,
        )
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return LLMResponse(
        content=content,
        input_tokens=usage.get("prompt_tokens", 0) or 0,
        output_tokens=usage.get("completion_tokens", 0) or 0,
    )


async def _call_ollama(
    config: ProviderConfig,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    client: httpx.AsyncClient,
) -> LLMResponse:
    """Call the Ollama ``/api/chat`` endpoint."""
    url = f"{config.base_url.rstrip('/')}/api/chat"

    payload = {
        "model": config.model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()

    content = data.get("message", {}).get("content", "")
    return LLMResponse(
        content=content,
        input_tokens=data.get("prompt_eval_count", 0) or 0,
        output_tokens=data.get("eval_count", 0) or 0,
    )


async def check_provider_available(config: ProviderConfig) -> Dict:
    """Check if a provider is reachable and the model is available."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
            if config.is_openai_compatible:
                # OpenAI-compatible: try listing models
                url = f"{config.base_url.rstrip('/')}/models"
                headers = {"Authorization": f"Bearer {config.api_key}"}
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return {
                    "reachable": True,
                    "provider": config.provider,
                    "model": config.model,
                    "model_available": config.model in models,
                    "available_models": models[:20],
                }
            else:
                # Ollama: /api/tags
                url = f"{config.base_url.rstrip('/')}/api/tags"
                resp = await client.get(url)
                resp.raise_for_status()
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                model_available = any(
                    config.model.split(":")[0] in name for name in models
                )
                return {
                    "reachable": True,
                    "provider": config.provider,
                    "model": config.model,
                    "model_available": model_available,
                    "available_models": models,
                }
    except Exception as e:
        return {
            "reachable": False,
            "provider": config.provider,
            "model": config.model,
            "model_available": False,
            "failure_reason": str(e)[:200],
        }

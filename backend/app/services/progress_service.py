"""Redis-backed progress tracker for all background tasks.

Replaces the old in-memory dictionaries with Redis hashes so that:
- Progress survives worker/API restarts
- Multiple workers can update progress concurrently
- The API process reads progress from the same Redis instance
- Progress entries auto-expire after 1 hour to avoid stale data

Resilience:
- Connection pool with retry on timeout
- Graceful degradation: if Redis is down, operations log and return defaults
- Health check endpoint for monitoring
"""
import json
import logging
import os
from typing import Dict, List, Optional

import redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_redis: Optional[redis.Redis] = None

# TTL for progress keys (1 hour — enough for any task + polling)
_TTL_SECONDS = 3600


def _get_redis() -> redis.Redis:
    """Lazy-connect to Redis with connection pooling and retry."""
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _redis


def _safe_redis_op(operation, default=None):
    """Execute a Redis operation with graceful error handling.

    If Redis is temporarily unavailable, log the error and return default
    instead of crashing the caller.
    """
    try:
        return operation()
    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        logger.warning("Redis operation failed (returning default): %s", e)
        return default
    except Exception as e:
        logger.error("Unexpected Redis error: %s", e, exc_info=True)
        return default


def redis_health_check() -> bool:
    """Check if Redis is reachable. Returns True/False."""
    try:
        return _get_redis().ping()
    except Exception:
        return False


def _key(namespace: str, task_id: str) -> str:
    """Build a Redis key: progress:<namespace>:<task_id>"""
    return f"progress:{namespace}:{task_id}"


# ── Generic progress API (used by all task types) ──

def set_progress(namespace: str, task_id: str, data: dict) -> None:
    """Store progress data for a task."""
    def _op():
        r = _get_redis()
        key = _key(namespace, task_id)
        r.set(key, json.dumps(data, default=str), ex=_TTL_SECONDS)
    _safe_redis_op(_op)


def get_progress(namespace: str, task_id: str) -> Optional[dict]:
    """Read progress data for a task. Returns None if not found."""
    def _op():
        r = _get_redis()
        raw = r.get(_key(namespace, task_id))
        if raw:
            return json.loads(raw)
        return None
    return _safe_redis_op(_op, default=None)


def delete_progress(namespace: str, task_id: str) -> None:
    """Remove progress data for a task."""
    def _op():
        _get_redis().delete(_key(namespace, task_id))
    _safe_redis_op(_op)


def get_many(namespace: str, task_ids: List[str]) -> List[dict]:
    """Read progress for multiple tasks at once (pipeline)."""
    if not task_ids:
        return []

    def _op():
        r = _get_redis()
        pipe = r.pipeline()
        for tid in task_ids:
            pipe.get(_key(namespace, tid))
        results = pipe.execute()
        return [json.loads(raw) for raw in results if raw]

    return _safe_redis_op(_op, default=[])


# ── Convenience wrappers with default idle state ──

_IDLE = {"status": "idle", "step": "idle", "progress": 0, "message": ""}


def get_or_idle(namespace: str, task_id: str) -> dict:
    """Return progress or a default idle state."""
    return get_progress(namespace, task_id) or dict(_IDLE)


# ── Document processing specific (backward-compatible with ProgressTracker) ──

DOCUMENT_STEPS = [
    {"key": "reading", "label": "Lecture du fichier", "pct": 10},
    {"key": "extracting_text", "label": "Extraction du texte", "pct": 30},
    {"key": "extracting_images", "label": "Extraction des images", "pct": 50},
    {"key": "chunking", "label": "Découpage en chunks", "pct": 65},
    {"key": "anonymizing", "label": "Anonymisation", "pct": 75},
    {"key": "indexing", "label": "Indexation vectorielle", "pct": 90},
    {"key": "completed", "label": "Terminé", "pct": 100},
    {"key": "failed", "label": "Échec", "pct": -1},
]


class ProgressTracker:
    """Document processing progress tracker (Redis-backed).

    Preserves the same API as the old in-memory version so callers
    (documents.py, progress polling endpoint) don't need changes.
    """
    STEPS = DOCUMENT_STEPS

    @classmethod
    def start(cls, document_id: str, filename: str) -> None:
        set_progress("document", document_id, {
            "document_id": document_id,
            "filename": filename,
            "step": "reading",
            "step_label": "Lecture du fichier",
            "progress": 10,
        })

    @classmethod
    def update(cls, document_id: str, step_key: str) -> None:
        step = next((s for s in cls.STEPS if s["key"] == step_key), None)
        if not step:
            return
        current = get_progress("document", document_id)
        if current:
            current.update({
                "step": step["key"],
                "step_label": step["label"],
                "progress": step["pct"],
            })
            set_progress("document", document_id, current)

    @classmethod
    def fail(cls, document_id: str, error: str) -> None:
        current = get_progress("document", document_id)
        if current:
            current.update({
                "step": "failed",
                "step_label": f"Échec: {error[:120]}",
                "progress": -1,
            })
            set_progress("document", document_id, current)

    @classmethod
    def get(cls, document_id: str) -> Optional[Dict]:
        return get_progress("document", document_id)

    @classmethod
    def get_for_project(cls, project_docs: list) -> list:
        return get_many("document", project_docs)

    @classmethod
    def remove(cls, document_id: str) -> None:
        delete_progress("document", document_id)


# ── Export results stored temporarily in Redis ──
# Word/backup exports produce file bytes that need to survive until download.
# Store in Redis with a 30-minute TTL.

_EXPORT_TTL = 1800  # 30 minutes


def store_export_result(export_type: str, task_id: str, file_bytes: bytes, filename: str) -> None:
    """Store export file bytes in Redis for later download."""
    def _op():
        r = _get_redis()
        key = f"export_result:{export_type}:{task_id}"
        import base64
        data = {
            "bytes_b64": base64.b64encode(file_bytes).decode("ascii"),
            "filename": filename,
        }
        r.set(key, json.dumps(data), ex=_EXPORT_TTL)
    _safe_redis_op(_op)


def get_export_result(export_type: str, task_id: str) -> Optional[dict]:
    """Retrieve export file bytes. Returns {"bytes": bytes, "filename": str} or None."""
    def _op():
        r = _get_redis()
        key = f"export_result:{export_type}:{task_id}"
        raw = r.get(key)
        if not raw:
            return None
        import base64
        data = json.loads(raw)
        return {
            "bytes": base64.b64decode(data["bytes_b64"]),
            "filename": data["filename"],
        }
    return _safe_redis_op(_op, default=None)


def delete_export_result(export_type: str, task_id: str) -> None:
    """Remove export result from Redis."""
    def _op():
        _get_redis().delete(f"export_result:{export_type}:{task_id}")
    _safe_redis_op(_op)

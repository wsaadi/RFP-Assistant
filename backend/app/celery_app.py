"""Celery application configuration.

All background tasks (document processing, AI generation, exports) run
as Celery tasks in separate worker processes, giving true multi-process
parallelism and persistence via Redis.

Reliability features:
- Late ack + reject on worker lost: tasks survive worker crashes
- Dedicated queues: document processing vs quick tasks
- Visibility timeout: prevents message loss on long tasks
- Exponential retry backoff: avoids thundering herd on transient errors
- Model preloading: embedding model loaded once per worker at startup
"""
import logging
import os

from celery import Celery
from celery.signals import worker_process_init
from kombu import Exchange, Queue

_logger = logging.getLogger(__name__)


def _build_redis_url(env_var: str) -> str:
    """Build a Redis URL from an env var, falling back to constructing one from REDIS_PASSWORD."""
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit
    password = os.environ.get("REDIS_PASSWORD", "")
    if password:
        return f"redis://:{password}@redis:6379/0"
    return "redis://redis:6379/0"


# Read broker/backend from environment; auto-inject REDIS_PASSWORD when the
# full URL vars are missing (common cause of "Authentication required" errors).
broker_url = _build_redis_url("CELERY_BROKER_URL")
result_backend = _build_redis_url("CELERY_RESULT_BACKEND")

celery = Celery(
    "rfp_assistant",
    broker=broker_url,
    backend=result_backend,
)

# ── Queue definitions ──
# Three dedicated queues for different workload profiles:
# - documents: heavy CPU-bound processing (NER, embedding, image analysis)
# - default: lightweight tasks (exports, backups)
# - ai: LLM-powered tasks (I/O-bound, waiting on external AI APIs)
default_exchange = Exchange("default", type="direct")
document_exchange = Exchange("documents", type="direct")
ai_exchange = Exchange("ai", type="direct")

celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # ── Timeouts ──
    # Document processing can be long (large PDFs + NER on CPU).
    # Soft limit gives the task a chance to save partial progress.
    task_soft_time_limit=900,    # 15 min soft limit (SoftTimeLimitExceeded)
    task_time_limit=1200,        # 20 min hard kill (SIGKILL)

    # ── Reliability ──
    # Acknowledge tasks only AFTER they complete.
    # If a worker dies mid-task, the message returns to the queue.
    task_acks_late=True,
    # Prevent infinite redelivery when a worker is killed (OOM, SIGKILL).
    task_reject_on_worker_lost=True,
    # Fetch one task at a time per worker process — prevents a single
    # worker from hogging tasks it can't process concurrently.
    worker_prefetch_multiplier=1,

    # ── Redis broker hardening ──
    # Visibility timeout must exceed the longest task_time_limit so that
    # Redis doesn't redeliver a message while a task is still running.
    # analyze_images has time_limit=7500 (2h05), so 9000 (2h30) is safe.
    broker_transport_options={
        "visibility_timeout": 9000,      # 2 h 30 (> analyze_images time_limit)
        "retry_on_timeout": True,
        "socket_keepalive": True,
        "socket_connect_timeout": 10,
        "socket_timeout": 120,
        # Priority support: 10 levels (0=highest) for the ai queue.
        # Redis creates a sub-queue per priority level; list them low→high.
        "priority_steps": list(range(10)),
    },

    # ── Redis connection pool ──
    # Limit connections to avoid exhausting Redis under load.
    broker_pool_limit=10,

    # ── Result expiry ──
    result_expires=86400,  # 24h TTL

    # ── Retry policy for broker connection ──
    # If Redis is temporarily unavailable, retry with backoff.
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,

    # ── Task queues ──
    # The ai queue supports 10 priority levels (0=highest, 9=lowest) so that
    # pipeline-critical tasks (structure generation) run before later stages
    # (compliance, soutenance) when the queue is congested.
    task_queues=(
        Queue("default", default_exchange, routing_key="default"),
        Queue("documents", document_exchange, routing_key="documents"),
        Queue("ai", ai_exchange, routing_key="ai",
              queue_arguments={"x-max-priority": 10}),
    ),
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # ── Task routing ──
    # Three queue strategy:
    # - documents: CPU-bound processing (NER, embedding, image analysis)
    # - ai: I/O-bound LLM calls (external API wait, high concurrency safe)
    # - default: lightweight tasks (exports, backups)
    task_routes={
        # CPU-bound document processing → documents queue
        "tasks.process_document": {"queue": "documents"},
        "tasks.reanonymize": {"queue": "documents"},
        "tasks.analyze_images": {"queue": "documents"},
        "tasks.vector_search": {"queue": "documents"},
        # I/O-bound AI/LLM tasks → ai queue (high concurrency)
        "tasks.generate_chapter_content": {"queue": "ai"},
        "tasks.gap_analysis": {"queue": "ai"},
        "tasks.generate_structure": {"queue": "ai"},
        "tasks.prefill_chapters": {"queue": "ai"},
        "tasks.detect_deliverables": {"queue": "ai"},
        "tasks.fill_deliverables": {"queue": "ai"},
        "tasks.compliance_analysis": {"queue": "ai"},
        "tasks.generate_recommendation": {"queue": "ai"},
        "tasks.export_soutenance": {"queue": "ai"},
        "tasks.preview_chat": {"queue": "ai"},
        "tasks.document_qa": {"queue": "ai"},
        # Lightweight tasks → default queue
        "tasks.export_word": {"queue": "default"},
        "tasks.export_backup": {"queue": "default"},
    },

    # ── Worker startup timeout ──
    # The default worker_proc_alive_timeout is 4s, which is too short when
    # the worker_process_init signal preloads the embedding model (weight
    # materialisation + HuggingFace HTTP requests can take 10-30s).
    # If the child doesn't send its UP message before this timeout, the
    # main process kills it with SIGKILL ("Timed out waiting for UP message").
    # With concurrency=1 no stagger is needed, but we keep a generous timeout
    # for slow networks / cold HuggingFace cache.
    worker_proc_alive_timeout=120,

    # ── Worker event emission (for monitoring) ──
    worker_send_task_events=True,
    task_send_sent_event=True,

    # ── Auto-discover tasks ──
    include=[
        "app.tasks.document_tasks",
        "app.tasks.chapter_tasks",
        "app.tasks.project_tasks",
        "app.tasks.export_tasks",
        "app.tasks.qa_tasks",
    ],
)


# ── Embedding model preloading ──
# The SentenceTransformer model (~800MB) is loaded lazily by VectorService.
# We preload it at worker startup so the first task doesn't pay the loading cost.
#
# Only the DOCUMENTS worker needs the model in memory:
# - It indexes chunks (VectorService.index_chunks) during document processing
# - It serves vector_search requests from AI workers via a dedicated Celery task
#
# AI workers no longer load the model — they delegate searches to the documents
# worker via tasks.vector_search.  This saves ~800MB per AI child process
# (~9.6GB total with 2×6 concurrency).

@worker_process_init.connect
def _preload_embedding_model(**kwargs):
    """Preload the embedding model only on the documents worker."""
    import sys
    argv_str = " ".join(sys.argv)
    if "--queues=documents" not in argv_str and "--queues documents" not in argv_str:
        _logger.info("Worker PID %d: skipping embedding preload (not documents worker)", os.getpid())
        return
    try:
        from .services.vector_service import VectorService
        _logger.info("Worker PID %d: preloading embedding model...", os.getpid())
        VectorService.get_embedding_function()
        _logger.info("Worker PID %d: embedding model loaded", os.getpid())
    except Exception as e:
        _logger.warning("Worker PID %d: failed to preload embedding model: %s", os.getpid(), e)

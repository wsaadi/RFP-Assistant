"""Celery application configuration.

All background tasks (document processing, AI generation, exports) run
as Celery tasks in separate worker processes, giving true multi-process
parallelism and persistence via Redis.

Reliability features:
- Late ack + reject on worker lost: tasks survive worker crashes
- Dedicated queues: document processing vs quick tasks
- Visibility timeout: prevents message loss on long tasks
- Exponential retry backoff: avoids thundering herd on transient errors
"""
import os

from celery import Celery
from kombu import Exchange, Queue

# Read broker/backend from environment (same vars as config.py)
broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

celery = Celery(
    "rfp_assistant",
    broker=broker_url,
    backend=result_backend,
)

# ── Queue definitions ──
# Separate heavy document processing from lighter AI / export tasks
# so that a large PDF doesn't block chapter generation.
default_exchange = Exchange("default", type="direct")
document_exchange = Exchange("documents", type="direct")

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
    # Visibility timeout must exceed task_time_limit so that Redis doesn't
    # redeliver a message while a task is still running.
    broker_transport_options={
        "visibility_timeout": 1800,      # 30 min (> task_time_limit)
        "retry_on_timeout": True,
        "socket_keepalive": True,
        "socket_connect_timeout": 10,
        "socket_timeout": 30,
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
    task_queues=(
        Queue("default", default_exchange, routing_key="default"),
        Queue("documents", document_exchange, routing_key="documents"),
    ),
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # ── Task routing ──
    # Route heavy document tasks to the dedicated 'documents' queue.
    task_routes={
        "tasks.process_document": {"queue": "documents"},
        "tasks.generate_chapter_content": {"queue": "default"},
        "tasks.gap_analysis": {"queue": "default"},
        "tasks.generate_structure": {"queue": "default"},
        "tasks.prefill_chapters": {"queue": "default"},
        "tasks.detect_deliverables": {"queue": "default"},
        "tasks.fill_deliverables": {"queue": "default"},
        "tasks.compliance_analysis": {"queue": "default"},
        "tasks.generate_recommendation": {"queue": "default"},
        "tasks.reanonymize": {"queue": "documents"},
        "tasks.export_word": {"queue": "default"},
        "tasks.export_backup": {"queue": "default"},
    },

    # ── Worker event emission (for monitoring) ──
    worker_send_task_events=True,
    task_send_sent_event=True,

    # ── Auto-discover tasks ──
    include=[
        "app.tasks.document_tasks",
        "app.tasks.chapter_tasks",
        "app.tasks.project_tasks",
        "app.tasks.export_tasks",
    ],
)

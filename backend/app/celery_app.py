"""Celery application configuration.

All background tasks (document processing, AI generation, exports) run
as Celery tasks in separate worker processes, giving true multi-process
parallelism and persistence via Redis.
"""
import os

from celery import Celery

# Read broker/backend from environment (same vars as config.py)
broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

celery = Celery(
    "rfp_assistant",
    broker=broker_url,
    backend=result_backend,
)

celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timeouts
    task_soft_time_limit=600,   # 10 min soft limit
    task_time_limit=900,        # 15 min hard kill

    # Reliability: acknowledge tasks only AFTER they complete.
    # If a worker dies mid-task, the message returns to the queue.
    task_acks_late=True,
    # Prevent infinite redelivery when a worker is killed (OOM, SIGKILL).
    # Without this, task_acks_late causes the message to loop forever.
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Result expiry (24h)
    result_expires=86400,

    # Auto-discover tasks in app.tasks package
    include=[
        "app.tasks.document_tasks",
        "app.tasks.chapter_tasks",
        "app.tasks.project_tasks",
        "app.tasks.export_tasks",
    ],
)

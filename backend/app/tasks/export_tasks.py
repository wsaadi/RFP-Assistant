"""Celery tasks for export operations (Word, backup, preview chat)."""
import asyncio
import uuid

from ..celery_app import celery


@celery.task(name="tasks.export_word", bind=True, max_retries=1)
def export_word_task(self, project_id: str, filename: str):
    from ..api.export import _run_word_export
    asyncio.run(_run_word_export(uuid.UUID(project_id), filename))


@celery.task(name="tasks.export_backup", bind=True, max_retries=1)
def export_backup_task(self, project_id: str, filename: str):
    from ..api.export import _run_backup_export
    asyncio.run(_run_backup_export(uuid.UUID(project_id), filename))


@celery.task(name="tasks.preview_chat", bind=True, max_retries=1)
def preview_chat_task(self, project_id: str, workspace_id: str, message: str):
    from ..api.export import _run_preview_chat
    asyncio.run(_run_preview_chat(uuid.UUID(project_id), uuid.UUID(workspace_id), message))


@celery.task(name="tasks.export_soutenance", bind=True, max_retries=1)
def export_soutenance_task(self, project_id: str, workspace_id: str, slide_count: int = 35):
    from ..api.export import _run_soutenance_export
    asyncio.run(_run_soutenance_export(uuid.UUID(project_id), uuid.UUID(workspace_id), slide_count))

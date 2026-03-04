"""Celery tasks for project-level background operations.

Each task is a thin wrapper that runs the corresponding async function
(which remains in projects.py) via asyncio.run(). This avoids duplicating
complex business logic while gaining Celery process isolation and Redis
progress persistence.
"""
import asyncio
import uuid

from ..celery_app import celery


@celery.task(name="tasks.gap_analysis", bind=True, max_retries=1)
def gap_analysis_task(self, project_id: str, workspace_id: str):
    from ..api.projects import _run_gap_analysis
    asyncio.run(_run_gap_analysis(uuid.UUID(project_id), uuid.UUID(workspace_id)))


@celery.task(name="tasks.generate_structure", bind=True, max_retries=1)
def generate_structure_task(self, project_id: str, workspace_id: str):
    from ..api.projects import _run_structure_generation
    asyncio.run(_run_structure_generation(uuid.UUID(project_id), uuid.UUID(workspace_id)))


@celery.task(name="tasks.prefill_chapters", bind=True, max_retries=1)
def prefill_chapters_task(self, project_id: str, workspace_id: str, chapter_ids: list):
    from ..api.projects import _run_prefill
    asyncio.run(_run_prefill(uuid.UUID(project_id), uuid.UUID(workspace_id), chapter_ids))


@celery.task(name="tasks.detect_deliverables", bind=True, max_retries=1)
def detect_deliverables_task(self, project_id: str, workspace_id: str):
    from ..api.projects import _run_detect_deliverables
    asyncio.run(_run_detect_deliverables(uuid.UUID(project_id), uuid.UUID(workspace_id)))


@celery.task(name="tasks.fill_deliverables", bind=True, max_retries=1)
def fill_deliverables_task(self, project_id: str, workspace_id: str):
    from ..api.projects import _run_fill_deliverables
    asyncio.run(_run_fill_deliverables(uuid.UUID(project_id), uuid.UUID(workspace_id)))


@celery.task(name="tasks.compliance_analysis", bind=True, max_retries=1)
def compliance_analysis_task(self, project_id: str, workspace_id: str, target_scope: str = "all"):
    from ..api.projects import _run_compliance_analysis
    asyncio.run(_run_compliance_analysis(uuid.UUID(project_id), uuid.UUID(workspace_id), target_scope))


@celery.task(name="tasks.generate_recommendation", bind=True, max_retries=1)
def generate_recommendation_task(
    self, task_id: str, project_id: str, workspace_id: str,
    recommendation: str, missing_description: str,
    chapter_id_override: str, inject: bool,
):
    from ..api.projects import _run_rec_generation
    asyncio.run(_run_rec_generation(
        task_id, uuid.UUID(project_id), uuid.UUID(workspace_id),
        recommendation, missing_description, chapter_id_override, inject,
    ))


@celery.task(name="tasks.reanonymize", bind=True, max_retries=1)
def reanonymize_task(self, project_id: str):
    from ..api.projects import _run_reanonymize
    asyncio.run(_run_reanonymize(uuid.UUID(project_id)))

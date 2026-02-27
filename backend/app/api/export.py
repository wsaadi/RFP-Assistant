"""Export/Import API routes."""
import asyncio
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject
from ..models.chapter import Chapter
from ..models.document import Document, DocumentImage
from ..services.word_service import RFPWordService
from ..services.export_service import ExportService
from ..services.anonymization_service import AnonymizationService
from ..services.progress_service import (
    set_progress, get_or_idle, delete_progress,
    store_export_result, get_export_result, delete_export_result,
)
from .deps import get_current_user

router = APIRouter(prefix="/export", tags=["Export/Import"])
logger = logging.getLogger(__name__)

# Redis progress namespaces
_NS_WORD = "word_export"
_NS_BACKUP = "backup_export"


@router.post("/{project_id}/word")
async def export_word(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch Word export as a Celery background task."""
    pid = str(project_id)

    existing = get_or_idle(_NS_WORD, pid)
    if existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Export Word deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    filename = f"reponse_ao_{project.rfp_reference or project.name}.docx"
    filename = filename.replace(" ", "_").replace("/", "_")

    set_progress(_NS_WORD, pid, {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de l'export Word...",
    })
    delete_export_result("word", pid)

    from ..tasks.export_tasks import export_word_task
    export_word_task.delay(pid, filename)

    return {"success": True, "message": "Export Word lance en arriere-plan"}


@router.get("/{project_id}/word-status")
async def get_word_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of Word export."""
    return get_or_idle(_NS_WORD, str(project_id))


@router.get("/{project_id}/word-download")
async def download_word(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Download the completed Word document."""
    pid = str(project_id)
    result = get_export_result("word", pid)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun export Word disponible. Lancez d'abord l'export.")

    import io
    file_buffer = io.BytesIO(result["bytes"])
    file_buffer.seek(0)
    filename = result["filename"]

    delete_export_result("word", pid)

    return StreamingResponse(
        file_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _run_word_export(project_id: uuid.UUID, filename: str):
    """Background task for Word export (called by Celery worker)."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        set_progress(_NS_WORD, pid, {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        })

    try:
        _update("loading", 10, "Chargement des chapitres...")

        async with async_session() as db:
            result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
            project = result.scalar_one()

            chapters_result = await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.order)
            )
            all_chapters = chapters_result.scalars().all()

            _update("building", 25, "Construction du document...")

            children_map = {}
            root_chapters = []
            for c in all_chapters:
                if c.parent_id:
                    children_map.setdefault(c.parent_id, []).append(c)
                else:
                    root_chapters.append(c)

            docs_result = await db.execute(
                select(Document).where(Document.project_id == project_id)
            )
            docs = docs_result.scalars().all()
            doc_ids = [d.id for d in docs]

            images_by_doc = {}
            if doc_ids:
                img_result = await db.execute(
                    select(DocumentImage).where(DocumentImage.document_id.in_(doc_ids))
                )
                for img in img_result.scalars().all():
                    images_by_doc.setdefault(str(img.document_id), []).append({
                        "file_path": img.file_path,
                        "description": img.description,
                        "tags": img.tags or [],
                    })

            deanon_map = await AnonymizationService.get_mappings_by_placeholder(db, project_id)

            def _deanon(text: str) -> str:
                if not text or not deanon_map:
                    return text
                for placeholder, original in deanon_map.items():
                    text = text.replace(placeholder, original)
                return text

            def build_chapter_data(chapter: Chapter) -> dict:
                children = children_map.get(chapter.id, [])
                return {
                    "title": chapter.title,
                    "content": _deanon(chapter.content or ""),
                    "chapter_type": chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
                    "numbering": chapter.numbering,
                    "images": chapter.image_references or [],
                    "children": [
                        build_chapter_data(child) for child in sorted(children, key=lambda x: x.order)
                    ],
                }

            chapters_data = [build_chapter_data(c) for c in root_chapters]

        _update("generating", 40, "Generation du document Word...")

        def _generate_word():
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            try:
                return loop.run_until_complete(RFPWordService.generate_full_document(
                    project_name=project.name,
                    client_name=project.client_name,
                    rfp_reference=project.rfp_reference,
                    chapters=chapters_data,
                ))
            finally:
                loop.close()

        file_stream = await asyncio.to_thread(_generate_word)

        _update("finalizing", 90, "Finalisation...")

        word_bytes = file_stream.getvalue()
        store_export_result("word", pid, word_bytes, filename)

        set_progress(_NS_WORD, pid, {
            "status": "completed", "step": "done", "progress": 100,
            "message": f"Export Word termine ({len(word_bytes) // 1024} KB)",
        })

    except Exception as e:
        logger.exception("Word export failed for project %s", project_id)
        set_progress(_NS_WORD, pid, {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        })


@router.post("/{project_id}/backup")
async def export_project_backup(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch backup export as a Celery background task."""
    pid = str(project_id)

    existing = get_or_idle(_NS_BACKUP, pid)
    if existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Export deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    filename = f"backup_{project.name}_{project.rfp_reference or 'export'}.zip"
    filename = filename.replace(" ", "_").replace("/", "_")

    set_progress(_NS_BACKUP, pid, {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de l'export...",
    })
    delete_export_result("backup", pid)

    from ..tasks.export_tasks import export_backup_task
    export_backup_task.delay(pid, filename)

    return {"success": True, "message": "Export lance en arriere-plan"}


@router.get("/{project_id}/backup-status")
async def get_backup_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of the backup export."""
    return get_or_idle(_NS_BACKUP, str(project_id))


@router.get("/{project_id}/backup-download")
async def download_backup(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Download the completed backup ZIP."""
    pid = str(project_id)
    result = get_export_result("backup", pid)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun backup disponible. Lancez d'abord l'export.")

    import io
    zip_buffer = io.BytesIO(result["bytes"])
    zip_buffer.seek(0)
    filename = result["filename"]

    delete_export_result("backup", pid)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _run_backup_export(project_id: uuid.UUID, filename: str):
    """Background task for backup export (called by Celery worker)."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        set_progress(_NS_BACKUP, pid, {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        })

    try:
        _update("loading", 5, "Chargement des donnees du projet...")

        async with async_session() as db:
            export_data, documents, images = await ExportService.collect_project_data(db, project_id)

        _update("packaging", 30, "Preparation des fichiers...")

        def _create_zip():
            return ExportService.create_zip_archive(export_data, documents, images, _update)

        zip_buffer = await asyncio.to_thread(_create_zip)

        zip_bytes = zip_buffer.getvalue()
        store_export_result("backup", pid, zip_bytes, filename)

        set_progress(_NS_BACKUP, pid, {
            "status": "completed", "step": "done", "progress": 100,
            "message": f"Export termine ({len(zip_bytes) // 1024} KB)",
        })

    except Exception as e:
        logger.exception("Backup export failed for project %s", project_id)
        set_progress(_NS_BACKUP, pid, {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        })


@router.delete("/{project_id}/backup-progress")
async def clear_backup_progress(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Clear backup progress state after download is complete."""
    pid = str(project_id)
    delete_progress(_NS_BACKUP, pid)
    delete_export_result("backup", pid)
    return {"cleared": True}


@router.delete("/{project_id}/word-progress")
async def clear_word_progress(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Clear word export progress state after download is complete."""
    pid = str(project_id)
    delete_progress(_NS_WORD, pid)
    delete_export_result("word", pid)
    return {"cleared": True}


@router.post("/import/{workspace_id}")
async def import_project_backup(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a project from a ZIP backup."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Fichier ZIP requis")

    content = await file.read()

    try:
        project = await ExportService.import_project(
            db, content, workspace_id, current_user.id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur d'import: {str(e)}")

    return {
        "success": True,
        "project_id": str(project.id),
        "project_name": project.name,
        "message": "Projet importé avec succès",
    }


@router.get("/{project_id}/preview")
async def preview_document(
    project_id: uuid.UUID,
    anonymized: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a full preview of the document content.

    Pass ``?anonymized=true`` to get the anonymized view (what the AI sees).
    Default returns the de-anonymized (final) content.
    """
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order)
    )
    all_chapters = chapters_result.scalars().all()

    # Build anonymization and de-anonymization maps
    anon_mappings = await AnonymizationService.get_mappings(db, project_id)
    deanon_map = await AnonymizationService.get_mappings_by_placeholder(db, project_id)

    def anonymize(text: str) -> str:
        """Apply all active mappings to produce the anonymized view."""
        if not text or not anon_mappings:
            return text
        # Replace longest originals first to avoid partial matches
        for original, mapping in sorted(
            anon_mappings.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if original and mapping.is_active:
                text = text.replace(original, mapping.anonymized_value)
        return text

    def deanonymize(text: str) -> str:
        if not text or not deanon_map:
            return text
        for placeholder, original in deanon_map.items():
            if original:
                text = text.replace(placeholder, original)
        return text

    transform = anonymize if anonymized else deanonymize

    children_map = {}
    root_chapters = []
    for c in all_chapters:
        if c.parent_id:
            children_map.setdefault(c.parent_id, []).append(c)
        else:
            root_chapters.append(c)

    def build_preview(chapter, level=1, prefix=""):
        numbering = f"{prefix}" if prefix else ""
        children = children_map.get(chapter.id, [])
        return {
            "id": str(chapter.id),
            "title": chapter.title,
            "numbering": numbering,
            "level": level,
            "content": transform(chapter.content or ""),
            "status": chapter.status.value if hasattr(chapter.status, 'value') else str(chapter.status),
            "chapter_type": chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
            "children": [
                build_preview(child, level + 1, f"{numbering}.{i+1}" if numbering else str(i+1))
                for i, child in enumerate(sorted(children, key=lambda x: x.order))
            ],
        }

    preview = {
        "project_name": project.name,
        "client_name": project.client_name,
        "rfp_reference": project.rfp_reference,
        "chapters": [
            build_preview(c, 1, str(i+1))
            for i, c in enumerate(root_chapters)
        ],
    }

    return preview

"""Export/Import API routes."""
import uuid
import logging
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.chapter import Chapter
from ..models.document import Document, DocumentImage
from ..services.word_service import RFPWordService
from ..services.export_service import ExportService
from ..services.anonymization_service import AnonymizationService
from .deps import get_current_user

router = APIRouter(prefix="/export", tags=["Export/Import"])
logger = logging.getLogger(__name__)

# In-memory progress tracking for exports
_backup_progress: Dict[str, dict] = {}
_backup_results: Dict[str, dict] = {}  # Stores {bytes, filename} when done
_word_progress: Dict[str, dict] = {}
_word_results: Dict[str, dict] = {}  # Stores {bytes, filename} when done


@router.post("/{project_id}/word")
async def export_word(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch Word export as a background task (returns immediately)."""
    pid = str(project_id)

    existing = _word_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Export Word deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    filename = f"reponse_ao_{project.rfp_reference or project.name}.docx"
    filename = filename.replace(" ", "_").replace("/", "_")

    _word_progress[pid] = {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de l'export Word...",
    }
    _word_results.pop(pid, None)

    background_tasks.add_task(_run_word_export, project_id, filename)

    return {"success": True, "message": "Export Word lance en arriere-plan"}


@router.get("/{project_id}/word-status")
async def get_word_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of Word export."""
    pid = str(project_id)
    return _word_progress.get(pid, {
        "status": "idle", "step": "idle", "progress": 0, "message": "",
    })


@router.get("/{project_id}/word-download")
async def download_word(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Download the completed Word document (once export is done)."""
    pid = str(project_id)
    result = _word_results.get(pid)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun export Word disponible. Lancez d'abord l'export.")

    import io
    file_buffer = io.BytesIO(result["bytes"])
    file_buffer.seek(0)
    filename = result["filename"]

    _word_results.pop(pid, None)
    _word_progress.pop(pid, None)

    return StreamingResponse(
        file_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _run_word_export(project_id: uuid.UUID, filename: str):
    """Background task for Word export."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _word_progress[pid] = {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        }

    try:
        async with async_session() as db:
            _update("loading", 10, "Chargement des chapitres...")

            result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
            project = result.scalar_one()

            chapters_result = await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.order)
            )
            all_chapters = chapters_result.scalars().all()

            _update("building", 30, "Construction du document...")

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

            def build_chapter_data(chapter: Chapter) -> dict:
                children = children_map.get(chapter.id, [])
                return {
                    "title": chapter.title,
                    "content": chapter.content or "",
                    "chapter_type": chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
                    "numbering": chapter.numbering,
                    "images": chapter.image_references or [],
                    "children": [
                        build_chapter_data(child) for child in sorted(children, key=lambda x: x.order)
                    ],
                }

            chapters_data = [build_chapter_data(c) for c in root_chapters]

            _update("generating", 50, "Generation du document Word...")
            file_stream = await RFPWordService.generate_full_document(
                project_name=project.name,
                client_name=project.client_name,
                rfp_reference=project.rfp_reference,
                chapters=chapters_data,
            )

        _update("finalizing", 90, "Finalisation...")
        word_bytes = file_stream.getvalue()
        _word_results[pid] = {"bytes": word_bytes, "filename": filename}

        _word_progress[pid] = {
            "status": "completed", "step": "done", "progress": 100,
            "message": f"Export Word termine ({len(word_bytes) // 1024} KB)",
        }

    except Exception as e:
        logger.exception("Word export failed for project %s", project_id)
        _word_progress[pid] = {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


@router.post("/{project_id}/backup")
async def export_project_backup(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch backup export as a background task (returns immediately)."""
    pid = str(project_id)

    # Check if already running
    existing = _backup_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Export deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    filename = f"backup_{project.name}_{project.rfp_reference or 'export'}.zip"
    filename = filename.replace(" ", "_").replace("/", "_")

    _backup_progress[pid] = {
        "status": "running",
        "step": "starting",
        "progress": 0,
        "message": "Demarrage de l'export...",
    }
    # Clear any previous result
    _backup_results.pop(pid, None)

    background_tasks.add_task(_run_backup_export, project_id, filename)

    return {"success": True, "message": "Export lance en arriere-plan"}


@router.get("/{project_id}/backup-status")
async def get_backup_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of the backup export."""
    pid = str(project_id)
    return _backup_progress.get(pid, {
        "status": "idle",
        "step": "idle",
        "progress": 0,
        "message": "",
    })


@router.get("/{project_id}/backup-download")
async def download_backup(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Download the completed backup ZIP (once export is done)."""
    pid = str(project_id)
    result = _backup_results.get(pid)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun backup disponible. Lancez d'abord l'export.")

    import io
    zip_buffer = io.BytesIO(result["bytes"])
    zip_buffer.seek(0)
    filename = result["filename"]

    # Clean up after download
    _backup_results.pop(pid, None)
    _backup_progress.pop(pid, None)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _run_backup_export(project_id: uuid.UUID, filename: str):
    """Background task for backup export."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _backup_progress[pid] = {
            "status": "running",
            "step": step,
            "progress": progress,
            "message": message,
        }

    try:
        async with async_session() as db:
            _update("loading", 10, "Chargement des donnees du projet...")
            zip_buffer = await ExportService.export_project(db, project_id)
            _update("packaging", 80, "Compression des fichiers...")

        # Store the result in memory for download
        zip_bytes = zip_buffer.getvalue()
        _backup_results[pid] = {
            "bytes": zip_bytes,
            "filename": filename,
        }

        _backup_progress[pid] = {
            "status": "completed",
            "step": "done",
            "progress": 100,
            "message": f"Export termine ({len(zip_bytes) // 1024} KB)",
        }

    except Exception as e:
        logger.exception("Backup export failed for project %s", project_id)
        _backup_progress[pid] = {
            "status": "error",
            "step": "error",
            "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a full preview of the document content."""
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

    # Build tree
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
            "content": chapter.content or "",
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

"""Export/Import API routes."""
import asyncio
import uuid
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.chapter import Chapter
from ..models.document import Document, DocumentImage
from ..models.response_document import ResponseDocument
from ..services.word_service import RFPWordService
from ..services.export_service import ExportService
from ..services.anonymization_service import AnonymizationService
from ..services.pptx_service import RFPPptxService
from ..services.soutenance_service import build_soutenance_prompt, _parse_json_response as parse_soutenance_json
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
_NS_PREVIEW_CHAT = "preview_chat"
_NS_SOUTENANCE = "soutenance_export"


class PreviewChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class DocumentQARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    document_ids: Optional[List[str]] = Field(None, description="Optional list of document UUIDs to restrict search scope")
    categories: Optional[List[str]] = Field(None, description="Optional list of document categories to restrict search scope")
    include_generated_content: bool = Field(False, description="Whether to include generated chapters as context")


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
    """Download the completed Word document (or ZIP if multiple documents)."""
    pid = str(project_id)
    result = get_export_result("word", pid)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun export Word disponible. Lancez d'abord l'export.")

    import io
    file_buffer = io.BytesIO(result["bytes"])
    file_buffer.seek(0)
    filename = result["filename"]

    delete_export_result("word", pid)

    if filename.endswith(".zip"):
        media_type = "application/zip"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return StreamingResponse(
        file_buffer,
        media_type=media_type,
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

            # Fetch response documents
            rd_result = await db.execute(
                select(ResponseDocument)
                .where(ResponseDocument.project_id == project_id)
                .order_by(ResponseDocument.order)
            )
            response_docs = rd_result.scalars().all()

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

            # Build image lookup for [INSERT_IMAGE:id] marker resolution
            # Maps image UUID → {file_path, description, image_type}
            image_lookup = {}
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
                    # Add to global lookup for marker resolution
                    image_lookup[str(img.id)] = {
                        "file_path": img.file_path,
                        "description": img.description or "",
                        "image_type": getattr(img, "image_type", "") or "",
                    }

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

            # Collect metadata needed for generation (before session closes)
            project_name = project.name
            client_name = project.client_name
            rfp_reference = project.rfp_reference
            company_name = getattr(project, 'company_name', '') or ''

            # Group chapters by response document if multiple docs exist
            if len(response_docs) > 1:
                doc_groups = []
                for rd in response_docs:
                    rd_chapters = [c for c in root_chapters if c.response_document_id == rd.id]
                    if rd_chapters:
                        doc_groups.append({
                            "title": rd.title,
                            "chapters": [build_chapter_data(c) for c in rd_chapters],
                        })
                # Orphan chapters (no response_document_id)
                orphan_chapters = [c for c in root_chapters if not c.response_document_id]
                if orphan_chapters:
                    doc_groups.append({
                        "title": "Autres sections",
                        "chapters": [build_chapter_data(c) for c in orphan_chapters],
                    })
            else:
                doc_groups = None
                chapters_data = [build_chapter_data(c) for c in root_chapters]

        _update("generating", 40, "Generation du document Word...")

        if doc_groups and len(doc_groups) > 1:
            # Multiple response documents → generate separate DOCX files in a ZIP
            import io as _io
            import zipfile as _zipfile

            def _generate_multi_word():
                import asyncio as _asyncio
                loop = _asyncio.new_event_loop()
                try:
                    results = []
                    for idx, group in enumerate(doc_groups):
                        doc_stream = loop.run_until_complete(
                            RFPWordService.generate_full_document(
                                project_name=group["title"],
                                client_name=client_name,
                                rfp_reference=rfp_reference,
                                chapters=group["chapters"],
                                company_name=company_name,
                                image_lookup=image_lookup,
                            )
                        )
                        safe_title = group["title"].replace(" ", "_").replace("/", "_").replace("\\", "_")
                        doc_filename = f"{safe_title}.docx"
                        results.append((doc_filename, doc_stream.getvalue()))
                    return results
                finally:
                    loop.close()

            doc_files = await asyncio.to_thread(_generate_multi_word)

            _update("finalizing", 90, "Finalisation...")

            # Package into a ZIP
            zip_buffer = _io.BytesIO()
            with _zipfile.ZipFile(zip_buffer, "w", _zipfile.ZIP_DEFLATED) as zf:
                for doc_filename, doc_bytes in doc_files:
                    zf.writestr(doc_filename, doc_bytes)
            zip_buffer.seek(0)

            zip_bytes = zip_buffer.getvalue()
            zip_filename = filename.replace(".docx", ".zip")
            store_export_result("word", pid, zip_bytes, zip_filename)

            set_progress(_NS_WORD, pid, {
                "status": "completed", "step": "done", "progress": 100,
                "message": f"Export Word termine - {len(doc_files)} documents ({len(zip_bytes) // 1024} KB)",
                "multi_document": True,
                "document_count": len(doc_files),
            })
        else:
            # Single document → generate a single DOCX as before
            if doc_groups and len(doc_groups) == 1:
                chapters_data = doc_groups[0]["chapters"]

            def _generate_word():
                import asyncio as _asyncio
                loop = _asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(RFPWordService.generate_full_document(
                        project_name=project_name,
                        client_name=client_name,
                        rfp_reference=rfp_reference,
                        chapters=chapters_data,
                        company_name=company_name,
                        image_lookup=image_lookup,
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


@router.post("/{project_id}/word-cancel")
async def cancel_word_export(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Cancel a running Word export: revoke Celery task and clear Redis state."""
    pid = str(project_id)

    # Try to revoke the Celery task (terminate if already executing)
    try:
        from ..celery_app import celery as celery_app
        celery_app.control.revoke(
            f"word-export-{pid}", terminate=True, signal="SIGTERM",
        )
    except Exception as e:
        logger.warning("Could not revoke Celery task for word export %s: %s", pid, e)

    # Clear progress and any partial result in Redis
    delete_progress(_NS_WORD, pid)
    delete_export_result("word", pid)

    return {"cancelled": True}


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

    MAX_BACKUP_SIZE = 500 * 1024 * 1024  # 500 MB
    content = await file.read()

    if len(content) > MAX_BACKUP_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Le fichier est trop volumineux ({len(content) // (1024*1024)} Mo). Taille maximale : {MAX_BACKUP_SIZE // (1024*1024)} Mo.",
        )

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

    # Fetch response documents to group chapters by deliverable
    rd_result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.project_id == project_id)
        .order_by(ResponseDocument.order)
    )
    response_docs = rd_result.scalars().all()

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

    # Group chapters by response_document_id
    if len(response_docs) > 1:
        rd_map = {rd.id: rd for rd in response_docs}
        # Build groups: chapters belonging to each response document
        doc_groups = []
        for rd in response_docs:
            rd_chapters = [c for c in root_chapters if c.response_document_id == rd.id]
            if rd_chapters:
                doc_groups.append({
                    "id": str(rd.id),
                    "title": rd.title,
                    "description": rd.description or "",
                    "chapters": [
                        build_preview(c, 1, str(i+1))
                        for i, c in enumerate(rd_chapters)
                    ],
                })
        # Chapters without a response_document_id (orphans)
        orphan_chapters = [c for c in root_chapters if not c.response_document_id]
        if orphan_chapters:
            doc_groups.append({
                "id": None,
                "title": "Autres sections",
                "description": "",
                "chapters": [
                    build_preview(c, 1, str(i+1))
                    for i, c in enumerate(orphan_chapters)
                ],
            })
    else:
        doc_groups = []

    preview = {
        "project_name": project.name,
        "client_name": project.client_name,
        "company_name": getattr(project, 'company_name', '') or '',
        "rfp_reference": project.rfp_reference,
        "chapters": [
            build_preview(c, 1, str(i+1))
            for i, c in enumerate(root_chapters)
        ],
        "documents": doc_groups,
    }

    return preview


# ── Preview Chat (general AI instructions on the whole document) ──


@router.post("/{project_id}/preview-chat")
async def preview_chat(
    project_id: uuid.UUID,
    request: PreviewChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a general instruction to the AI to modify chapters across the document."""
    pid = str(project_id)

    existing = get_or_idle(_NS_PREVIEW_CHAT, pid)
    if existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Une instruction est deja en cours de traitement")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouve")

    config_result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
    )
    config = config_result.scalar_one_or_none()
    if not config or not config.mistral_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Configuration IA non definie")

    set_progress(_NS_PREVIEW_CHAT, pid, {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Analyse de l'instruction...",
    })

    from ..tasks.export_tasks import preview_chat_task
    preview_chat_task.apply_async(
        args=(pid, str(project.workspace_id), request.message), priority=7,
    )

    return {"success": True, "message": "Instruction envoyee a l'IA"}


@router.get("/{project_id}/preview-chat-status")
async def get_preview_chat_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of preview chat AI processing."""
    return get_or_idle(_NS_PREVIEW_CHAT, str(project_id))


@router.post("/{project_id}/preview-chat-cancel")
async def cancel_preview_chat(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Cancel a running preview chat task."""
    pid = str(project_id)
    delete_progress(_NS_PREVIEW_CHAT, pid)
    return {"cancelled": True}


async def _run_preview_chat(project_id: uuid.UUID, workspace_id: uuid.UUID, user_message: str):
    """Background task: apply a general AI instruction across all chapters.

    Uses a 2-pass approach to avoid timeout on large documents:
      Pass 1 (fast): send chapter titles + short excerpts → AI returns IDs of chapters to modify
      Pass 2 (targeted): for each identified chapter, send its full content → AI returns modified version
    """
    from ..database import create_task_engine
    from ..services.ai_service import create_ai_service
    import json as _json
    import re as _re

    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        set_progress(_NS_PREVIEW_CHAT, pid, {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        })

    def _parse_json(raw: str):
        cleaned = raw.strip()
        cleaned = _re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = _re.sub(r'\n?```\s*$', '', cleaned)
        try:
            return _json.loads(cleaned)
        except _json.JSONDecodeError:
            match = _re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                return _json.loads(match.group())
            match_arr = _re.search(r'\[[\s\S]*\]', cleaned)
            if match_arr:
                return _json.loads(match_arr.group())
            raise ValueError("L'IA n'a pas retourne un JSON valide")

    task_engine, TaskSession = create_task_engine()

    try:
        _update("loading", 5, "Chargement du document...")

        async with TaskSession() as db:
            config_result = await db.execute(
                select(AIConfig).where(AIConfig.workspace_id == workspace_id)
            )
            config = config_result.scalar_one()
            ai_service = create_ai_service(config)

            project_result = await db.execute(
                select(RFPProject).where(RFPProject.id == project_id)
            )
            project = project_result.scalar_one()

            chapters_result = await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.order)
            )
            all_chapters = chapters_result.scalars().all()

            chapters_data = []
            for ch in all_chapters:
                if ch.content and ch.content.strip():
                    anon_content = await AnonymizationService.anonymize_text(
                        ch.content, project_id, db,
                    )
                    chapters_data.append({
                        "id": str(ch.id),
                        "title": ch.title,
                        "numbering": ch.numbering or "",
                        "content": anon_content,
                    })

            anon_message = await AnonymizationService.anonymize_text(
                user_message, project_id, db,
            )

            deanon_map = await AnonymizationService.get_mappings_by_placeholder(db, project_id)
            ai_context = project.ai_context or ""
            proj_company_name = getattr(project, 'company_name', '') or ''
            proj_client_name = project.client_name or ''

        if not chapters_data:
            set_progress(_NS_PREVIEW_CHAT, pid, {
                "status": "completed", "step": "done", "progress": 100,
                "message": "Aucun chapitre avec du contenu a modifier.",
                "changed_chapters": [],
            })
            return

        # ── PASS 1: Identify which chapters need modification ──
        _update("analyzing", 15, "Analyse des chapitres concernes...")

        toc_lines = []
        for ch in chapters_data:
            excerpt = ch["content"][:200].replace("\n", " ")
            toc_lines.append(f'- ID: "{ch["id"]}" | {ch["numbering"]} {ch["title"]} | Extrait: {excerpt}...')
        toc_text = "\n".join(toc_lines)

        identify_system = """Tu es un assistant expert en redaction de reponses aux appels d'offres.
L'utilisateur donne une instruction a appliquer sur un document.
Tu recois la liste des chapitres avec un court extrait.

Ton role: identifier TOUS les chapitres qui doivent etre modifies pour appliquer l'instruction.

Reponds UNIQUEMENT avec un JSON valide:
{
  "chapter_ids": ["uuid-1", "uuid-2"],
  "summary": "Explication courte de ce qui va etre modifie"
}

Si aucun chapitre n'est concerne:
{"chapter_ids": [], "summary": "Aucune modification necessaire."}"""

        identify_user = f"""Liste des chapitres du document:

{toc_text}

--- INSTRUCTION ---
{anon_message}

Quels chapitres doivent etre modifies? Retourne le JSON."""

        raw_identify = await ai_service.generate_streaming(
            identify_system, identify_user, temperature=0.1, timeout=300,
        )

        # Log AI usage for preview chat - pass 1 (identify)
        from ..services.ai_service import log_ai_usage_from_service
        async with TaskSession() as usage_db:
            await log_ai_usage_from_service(usage_db, project_id, "preview_chat_identify", ai_service)

        identify_result = _parse_json(raw_identify)

        target_ids = set()
        if isinstance(identify_result, dict):
            target_ids = set(identify_result.get("chapter_ids", []))
            summary_intro = identify_result.get("summary", "")
        elif isinstance(identify_result, list):
            target_ids = set(identify_result)
            summary_intro = ""
        else:
            target_ids = set()
            summary_intro = ""

        if not target_ids:
            set_progress(_NS_PREVIEW_CHAT, pid, {
                "status": "completed", "step": "done", "progress": 100,
                "message": summary_intro or "Aucune modification necessaire.",
                "changed_chapters": [],
            })
            return

        # Filter to only targeted chapters
        targeted_chapters = [ch for ch in chapters_data if ch["id"] in target_ids]
        if not targeted_chapters:
            set_progress(_NS_PREVIEW_CHAT, pid, {
                "status": "completed", "step": "done", "progress": 100,
                "message": "Aucun chapitre correspondant trouve.",
                "changed_chapters": [],
            })
            return

        total = len(targeted_chapters)
        _update("generating", 25, f"Modification de {total} chapitre(s)...")

        # ── PASS 2: Modify each chapter individually ──
        modify_system = """Tu es un assistant expert en redaction de reponses aux appels d'offres.
L'utilisateur te donne une instruction et le contenu d'un chapitre.
Applique l'instruction au chapitre et retourne le contenu COMPLET modifie.

Anonymisation:
- Le texte peut contenir des marqueurs comme [ENTREPRISE_1], [SOLUTION_1], [PERSONNE_1], etc.
- Tu DOIS reutiliser EXACTEMENT les memes marqueurs. Ne JAMAIS en inventer de nouveaux.

Formatage:
- Utilise des sous-titres avec ## pour les sections
- Utilise **gras** pour les termes importants
- Utilise des listes a puces avec - pour les enumerations

Retourne UNIQUEMENT le contenu modifie du chapitre, sans explication ni JSON."""

        # Add identity and anti-hallucination guardrails
        from ..services.ai_service import _build_identity_block
        modify_system += _build_identity_block(proj_company_name, proj_client_name)

        if ai_context:
            modify_system += f"""

Contexte de redaction:
{ai_context}"""

        def _deanon(text: str) -> str:
            if not text or not deanon_map:
                return text
            for placeholder, original in deanon_map.items():
                text = text.replace(placeholder, original)
            return text

        changed_titles = []
        changes_to_save = []

        for i, ch in enumerate(targeted_chapters):
            pct = 25 + int(60 * (i / total))
            _update("generating", pct, f"Modification du chapitre {i+1}/{total}: {ch['title'][:40]}...")

            modify_user = f"""Chapitre: {ch['numbering']} {ch['title']}

Contenu actuel:
{ch['content']}

--- INSTRUCTION ---
{anon_message}

Applique l'instruction et retourne le contenu COMPLET modifie."""

            modified_content = await ai_service.generate_streaming(
                modify_system, modify_user, temperature=0.3, timeout=600,
            )

            # Basic sanity check: AI should return substantial content
            if modified_content and len(modified_content.strip()) > 20:
                changes_to_save.append({
                    "chapter_id": ch["id"],
                    "title": ch["title"],
                    "new_content": _deanon(modified_content.strip()),
                })
                changed_titles.append(ch["title"])

        # Log AI usage for preview chat - pass 2 (modify chapters)
        async with TaskSession() as usage_db:
            await log_ai_usage_from_service(usage_db, project_id, "preview_chat_modify", ai_service)

        if changes_to_save:
            _update("saving", 90, f"Enregistrement de {len(changes_to_save)} chapitre(s)...")

            async with TaskSession() as db:
                for change in changes_to_save:
                    try:
                        ch_result = await db.execute(
                            select(Chapter).where(Chapter.id == uuid.UUID(change["chapter_id"]))
                        )
                        chapter = ch_result.scalar_one_or_none()
                        if chapter:
                            chapter.content = change["new_content"]
                    except Exception as e:
                        logger.warning("Could not update chapter %s: %s", change["chapter_id"], e)
                await db.commit()

        set_progress(_NS_PREVIEW_CHAT, pid, {
            "status": "completed", "step": "done", "progress": 100,
            "message": summary_intro or f"{len(changed_titles)} chapitre(s) modifie(s).",
            "changed_chapters": changed_titles,
        })

    except Exception as e:
        logger.exception("Preview chat failed for project %s", project_id)
        set_progress(_NS_PREVIEW_CHAT, pid, {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        })
    finally:
        await task_engine.dispose()


# ── Document Q&A ──


CATEGORY_LABELS = {
    "old_rfp": "Ancien AO",
    "old_response": "Ancienne Reponse",
    "new_rfp": "Nouvel AO",
    "new_response": "Notre Reponse",
    "inspiration": "Inspiration",
}


@router.post("/{project_id}/document-qa")
async def document_qa(
    project_id: uuid.UUID,
    request: DocumentQARequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer a question about the project documents using RAG (vector search + LLM)."""
    from ..services.moderation_service import moderate_prompt_llm
    from ..services.vector_service import VectorService
    from ..services.ai_service import create_ai_service
    from ..security import decrypt_api_key

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouve")

    config_result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
    )
    config = config_result.scalar_one_or_none()
    if not config or not config.mistral_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Configuration IA non definie")

    # Moderate the user question (regex + LLM) before any heavy processing
    scw_key = decrypt_api_key(config.scaleway_api_key_encrypted or "") if config.scaleway_api_key_encrypted else ""
    moderation = await moderate_prompt_llm(
        request.question,
        field_name="document_qa",
        api_key=scw_key,
        scaleway_project_id=config.scaleway_project_id or "",
    )
    if not moderation:
        return {
            "answer": moderation.message,
            "sources": [],
        }

    ai_service = create_ai_service(config)

    # Semantic search — optionally restricted to selected documents/categories
    # If categories are selected, search within each category and merge results
    if request.categories and not request.document_ids:
        all_search_results = []
        for cat in request.categories:
            cat_results = VectorService.search(
                str(project_id),
                request.question,
                top_k=15,
                category_filter=cat,
            )
            all_search_results.extend(cat_results)
        # Sort by score descending and take top 25
        all_search_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        search_results = all_search_results[:25]
    else:
        search_results = VectorService.search(
            str(project_id),
            request.question,
            top_k=25,
            document_ids=request.document_ids,
        )

    # Filter out low-relevance results (cosine similarity < 0.3)
    search_results = [r for r in search_results if r.get("score", 0) >= 0.3]

    # Load generated content if requested
    generated_context = ""
    if request.include_generated_content:
        from ..models.chapter import Chapter
        from ..services.anonymization_service import AnonymizationService
        ch_result = await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .where(Chapter.content != "")
            .order_by(Chapter.order)
        )
        chapters = ch_result.scalars().all()
        if chapters:
            ch_parts = []
            for ch in chapters:
                ch_parts.append(f"## {ch.title}\n{ch.content[:3000]}")
            generated_context = "\n\n".join(ch_parts)

    if not search_results and not generated_context:
        has_filters = request.document_ids or request.categories
        if has_filters:
            return {
                "answer": "Je n'ai trouve aucune information pertinente dans les sources selectionnees pour repondre a cette question. Essayez de reformuler votre question ou de selectionner d'autres sources.",
                "sources": [],
            }
        return {
            "answer": "Je n'ai trouve aucun document pertinent pour repondre a cette question. Verifiez que des documents ont bien ete charges et traites dans le projet.",
            "sources": [],
        }

    # Build context from search results — group by document for coherence
    from collections import defaultdict
    doc_groups = defaultdict(list)
    for r in search_results:
        doc_key = r.get("document_name", "Document inconnu")
        doc_groups[doc_key].append(r)

    context_parts = []
    sources = []
    seen_sources = set()
    chunk_count = 0
    max_chunks = 20  # Limit context window to avoid dilution

    for doc_name, doc_results in doc_groups.items():
        # Sort by page number then chunk index for coherent reading order
        doc_results.sort(key=lambda x: (x.get("page_number", 0), x.get("chunk_index", 0)))
        for r in doc_results:
            if chunk_count >= max_chunks:
                break
            content = r["content"]
            # Remove the "passage: " prefix added during indexing
            if content.startswith("passage: "):
                content = content[9:]
            category = r.get("category", "")
            page = r.get("page_number", 0)
            section = r.get("section_title", "")
            cat_label = CATEGORY_LABELS.get(category, category)
            score = r.get("score", 0)

            header = f"[Source: {doc_name} | {cat_label} | page {page}"
            if section:
                header += f" | section: {section}"
            header += f" | pertinence: {score:.0%}]"

            context_parts.append(f"{header}\n{content}")
            chunk_count += 1

            source_key = f"{doc_name}|{page}"
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                sources.append({
                    "document_name": doc_name,
                    "category": category,
                    "category_label": cat_label,
                    "page_number": page,
                    "score": score,
                    "excerpt": content[:200],
                })

    # Append generated content if requested
    if generated_context:
        context_parts.append(
            f"[Source: Contenu genere | Chapitres rediges | Reponse en cours]\n{generated_context}"
        )
        sources.append({
            "document_name": "Contenu genere (chapitres)",
            "category": "generated",
            "category_label": "Contenu genere",
            "page_number": 0,
            "score": 1.0,
            "excerpt": generated_context[:200],
        })

    context_text = "\n\n---\n\n".join(context_parts)

    # Build document scope description for the prompt
    doc_scope = ""
    if request.document_ids or request.categories:
        scope_parts = []
        if request.categories:
            scope_parts.append(f"categories: {', '.join(request.categories)}")
        if request.document_ids:
            doc_names_in_scope = list(doc_groups.keys())
            scope_parts.append(f"documents: {', '.join(doc_names_in_scope)}")
        if request.include_generated_content:
            scope_parts.append("contenu genere (chapitres rediges)")
        doc_scope = f"\n\nIMPORTANT: L'utilisateur a restreint la recherche aux sources suivantes : {'; '.join(scope_parts)}. Concentre ta reponse sur ces sources uniquement."
    elif request.include_generated_content:
        doc_scope = "\n\nIMPORTANT: L'utilisateur a demande d'inclure le contenu genere (chapitres rediges) dans la recherche. Utilise aussi ces informations pour repondre."

    system_prompt = f"""Tu es un assistant expert en analyse de documents pour les appels d'offres.
L'utilisateur te pose des questions sur les documents charges dans le projet.
Tu dois repondre en te basant UNIQUEMENT sur les extraits de documents fournis ci-dessous.

Regles STRICTES:
- Base ta reponse EXCLUSIVEMENT sur les extraits fournis. Ne complete JAMAIS avec des connaissances generales.
- Reponds de maniere precise, structuree et detaillee.
- Cite TOUJOURS tes sources avec le format exact : **(Source: nom_du_fichier.pdf, Categorie, page X)**
- Pour chaque affirmation factuelle, indique la source correspondante.
- Si tu ne trouves PAS l'information dans les extraits fournis, dis-le CLAIREMENT : "Cette information n'apparait pas dans les extraits disponibles."
- Ne fais JAMAIS de supposition ou d'extrapolation au-dela de ce qui est ecrit dans les documents.
- Si l'information est partielle, indique-le et cite ce qui est disponible.

Vocabulaire de categorie:
- "Ancien AO" = documents de categorie "Ancien AO" (ancien appel d'offres)
- "Ancienne Reponse" = documents de categorie "Ancienne Reponse"
- "Nouvel AO" / "cahier des charges" = documents de categorie "Nouvel AO"
- "Notre Reponse" = documents de categorie "Notre Reponse"
- "Inspiration" = documents d'inspiration / references
- "Contenu genere" = chapitres rediges par l'IA dans le cadre de la reponse en cours

Mise en forme:
- Utilise le markdown : titres (##), listes, **gras** pour les points cles.
- Si la question porte sur une comparaison, structure ta reponse en colonnes ou sections claires.
- Termine par une synthese courte si la reponse est longue.{doc_scope}"""

    user_prompt = f"""Voici les extraits pertinents des documents du projet (classes par document et page) :

{context_text}

---

Question de l'utilisateur : {request.question}

Reponds de maniere precise et structuree en citant systematiquement tes sources."""

    try:
        answer = await ai_service.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, timeout=120,
        )
    except Exception as e:
        logger.error("Document QA failed for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Erreur IA: {str(e)[:200]}")

    # Log AI usage for document QA
    from ..services.ai_service import log_ai_usage_from_service
    await log_ai_usage_from_service(db, project_id, "document_qa", ai_service)

    return {
        "answer": answer,
        "sources": sources[:10],
    }


# ── Soutenance (PowerPoint + Script) ──


class SoutenanceRequest(BaseModel):
    slide_count: int = Field(default=35, ge=15, le=60)


@router.post("/{project_id}/soutenance")
async def export_soutenance(
    project_id: uuid.UUID,
    body: SoutenanceRequest = SoutenanceRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch soutenance generation (PowerPoint + script) as a background task."""
    pid = str(project_id)

    existing = get_or_idle(_NS_SOUTENANCE, pid)
    if existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Generation de soutenance deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouve")

    config_result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
    )
    config = config_result.scalar_one_or_none()
    if not config or not config.mistral_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Configuration IA non definie")

    # Clear ALL previous soutenance data (Redis + filesystem) to allow clean regeneration
    delete_progress(_NS_SOUTENANCE, pid)
    delete_export_result("soutenance_pptx", pid)
    delete_export_result("soutenance_script", pid)

    # Clear old filesystem files
    import os, shutil
    sout_dir = os.path.join(settings.export_dir, "soutenance", pid)
    if os.path.isdir(sout_dir):
        shutil.rmtree(sout_dir, ignore_errors=True)

    # Set initial progress AFTER clearing everything
    set_progress(_NS_SOUTENANCE, pid, {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de la preparation de soutenance...",
    })

    from ..tasks.export_tasks import export_soutenance_task
    export_soutenance_task.apply_async(
        args=(pid, str(project.workspace_id), body.slide_count), priority=7,
    )

    return {"success": True, "message": "Preparation de soutenance lancee en arriere-plan"}


@router.get("/{project_id}/soutenance-exists")
async def check_soutenance_exists(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Check if a previously generated soutenance exists (Redis or filesystem)."""
    import os
    pid = str(project_id)

    # Check Redis first
    if get_export_result("soutenance_script", pid):
        return {"exists": True}

    # Check filesystem
    script_path = os.path.join(settings.export_dir, "soutenance", pid, "script.json")
    if os.path.exists(script_path):
        return {"exists": True}

    return {"exists": False}


@router.get("/{project_id}/soutenance-status")
async def get_soutenance_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of soutenance generation."""
    return get_or_idle(_NS_SOUTENANCE, str(project_id))


@router.get("/{project_id}/soutenance-download-pptx")
async def download_soutenance_pptx(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Download the generated soutenance PowerPoint."""
    import io, os
    pid = str(project_id)
    result = get_export_result("soutenance_pptx", pid)

    if result:
        file_buffer = io.BytesIO(result["bytes"])
        file_buffer.seek(0)
        filename = result["filename"]
    else:
        # Fall back to filesystem
        sout_dir = os.path.join(settings.export_dir, "soutenance", pid)
        fname_path = os.path.join(sout_dir, ".pptx_filename")
        if not os.path.exists(fname_path):
            raise HTTPException(status_code=404, detail="Aucune presentation disponible. Lancez d'abord la generation.")
        with open(fname_path, "r") as f:
            filename = f.read().strip()
        pptx_path = os.path.join(sout_dir, filename)
        if not os.path.exists(pptx_path):
            raise HTTPException(status_code=404, detail="Fichier PowerPoint introuvable.")
        with open(pptx_path, "rb") as f:
            file_buffer = io.BytesIO(f.read())
        file_buffer.seek(0)

    return StreamingResponse(
        file_buffer,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{project_id}/soutenance-download-script")
async def download_soutenance_script(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Download the generated soutenance script as JSON."""
    import json as _json
    import os

    pid = str(project_id)
    result = get_export_result("soutenance_script", pid)

    if result:
        script_data = _json.loads(result["bytes"].decode("utf-8"))
        return script_data

    # Fall back to filesystem
    script_path = os.path.join(settings.export_dir, "soutenance", pid, "script.json")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Aucun script disponible. Lancez d'abord la generation.")

    with open(script_path, "r", encoding="utf-8") as f:
        return _json.load(f)


@router.post("/{project_id}/soutenance-cancel")
async def cancel_soutenance(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Cancel a running soutenance generation."""
    pid = str(project_id)
    try:
        from ..celery_app import celery as celery_app
        celery_app.control.revoke(
            f"soutenance-{pid}", terminate=True, signal="SIGTERM",
        )
    except Exception as e:
        logger.warning("Could not revoke soutenance task %s: %s", pid, e)

    delete_progress(_NS_SOUTENANCE, pid)
    delete_export_result("soutenance_pptx", pid)
    delete_export_result("soutenance_script", pid)
    return {"cancelled": True}


@router.delete("/{project_id}/soutenance-progress")
async def clear_soutenance_progress(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Clear soutenance progress state."""
    pid = str(project_id)
    delete_progress(_NS_SOUTENANCE, pid)
    delete_export_result("soutenance_pptx", pid)
    delete_export_result("soutenance_script", pid)
    return {"cleared": True}


async def _run_soutenance_export(project_id: uuid.UUID, workspace_id: uuid.UUID, slide_count: int = 35):
    """Background task for soutenance generation (called by Celery worker)."""
    from ..database import create_task_engine
    from ..services.ai_service import create_ai_service
    import json as _json

    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        set_progress(_NS_SOUTENANCE, pid, {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        })

    task_engine, TaskSession = create_task_engine()

    try:
        _update("loading", 5, "Chargement du projet et des chapitres...")

        async with TaskSession() as db:
            config_result = await db.execute(
                select(AIConfig).where(AIConfig.workspace_id == workspace_id)
            )
            config = config_result.scalar_one()
            ai_service = create_ai_service(config)

            project_result = await db.execute(
                select(RFPProject).where(RFPProject.id == project_id)
            )
            project = project_result.scalar_one()

            chapters_result = await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.order)
            )
            all_chapters = chapters_result.scalars().all()

            deanon_map = await AnonymizationService.get_mappings_by_placeholder(db, project_id)

            def _deanon(text: str) -> str:
                if not text or not deanon_map:
                    return text
                for placeholder, original in deanon_map.items():
                    text = text.replace(placeholder, original)
                return text

            # Build chapter tree
            children_map = {}
            root_chapters = []
            for c in all_chapters:
                if c.parent_id:
                    children_map.setdefault(c.parent_id, []).append(c)
                else:
                    root_chapters.append(c)

            def build_chapter_data(chapter) -> dict:
                children = children_map.get(chapter.id, [])
                return {
                    "title": chapter.title,
                    "content": _deanon(chapter.content or ""),
                    "chapter_type": chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
                    "numbering": chapter.numbering or "",
                    "children": [
                        build_chapter_data(child)
                        for child in sorted(children, key=lambda x: x.order)
                    ],
                }

            chapters_data = [build_chapter_data(c) for c in root_chapters]

            proj_name = project.name
            proj_client = project.client_name or ""
            proj_company = getattr(project, 'company_name', '') or ''
            proj_ref = project.rfp_reference or ""
            proj_ai_context = project.ai_context or ""

        _update("generating", 15, "Generation du contenu de soutenance par l'IA...")

        # Build and send prompt
        system_prompt, user_prompt = build_soutenance_prompt(
            project_name=proj_name,
            client_name=proj_client,
            company_name=proj_company,
            rfp_reference=proj_ref,
            chapters_data=chapters_data,
            ai_context=proj_ai_context,
            slide_count=slide_count,
        )

        # Progress callback for streaming: update between 15% and 55%
        # based on tokens received vs expected max
        expected_max_tokens = 16000

        async def _on_stream_progress(token_count: int, char_count: int):
            # Map token progress from 15% to 55%
            ratio = min(token_count / expected_max_tokens, 1.0)
            pct = 15 + int(ratio * 40)  # 15% → 55%
            # Provide detailed messages at key milestones
            if pct < 25:
                msg = f"L'IA redige le contenu... ({token_count} tokens generes)"
            elif pct < 35:
                msg = f"Structuration des sections... ({token_count} tokens)"
            elif pct < 45:
                msg = f"Redaction des slides et notes... ({token_count} tokens)"
            else:
                msg = f"Finalisation du contenu... ({token_count} tokens)"
            _update("generating", pct, msg)

        raw_response = await ai_service.generate_streaming(
            system_prompt, user_prompt,
            temperature=0.3,
            max_tokens=expected_max_tokens,
            timeout=900,
            on_progress=_on_stream_progress,
        )

        # Log AI usage for soutenance generation
        from ..services.ai_service import log_ai_usage_from_service
        async with TaskSession() as usage_db:
            await log_ai_usage_from_service(usage_db, project_id, "soutenance_generation", ai_service)

        _update("parsing", 60, "Analyse de la reponse de l'IA...")

        soutenance_data = parse_soutenance_json(raw_response)

        total_slides = sum(len(s.get("slides", [])) for s in soutenance_data.get("sections", []))
        _update("building_pptx", 65, f"Construction du PowerPoint ({total_slides} slides)...")

        def _generate_pptx():
            return RFPPptxService.generate_presentation(
                project_name=proj_name,
                client_name=proj_client,
                company_name=proj_company,
                rfp_reference=proj_ref,
                soutenance_data=soutenance_data,
            )

        pptx_stream = await asyncio.to_thread(_generate_pptx)

        _update("building_pptx", 80, "PowerPoint genere, preparation des fichiers...")
        _update("saving", 85, "Sauvegarde du PowerPoint et du script...")

        # Store PPTX
        pptx_bytes = pptx_stream.getvalue()
        pptx_filename = f"soutenance_{proj_ref or proj_name}.pptx".replace(" ", "_").replace("/", "_")
        store_export_result("soutenance_pptx", pid, pptx_bytes, pptx_filename)

        # Store script data (as JSON in Redis)
        # The AI response has top-level sections/strengths/key_figures AND a nested
        # "script" block.  The script block may be truncated when the LLM hits
        # max_tokens because it comes last in the JSON.  We ensure the dashboard
        # is always populated by merging top-level data into the script.
        script_data = soutenance_data.get("script", {})
        script_data["project_name"] = proj_name
        script_data["client_name"] = proj_client
        script_data["company_name"] = proj_company
        script_data["rfp_reference"] = proj_ref

        top_sections = soutenance_data.get("sections", [])
        script_data["sections_overview"] = [
            {"title": s.get("title", ""), "duration": s.get("duration", "")}
            for s in top_sections
        ]
        script_data["key_figures"] = soutenance_data.get("key_figures", [])
        script_data["strengths"] = soutenance_data.get("strengths", [])

        # If script.sections is empty/missing, rebuild from top-level sections
        if not script_data.get("sections"):
            script_data["sections"] = [
                {
                    "title": s.get("title", ""),
                    "duration": s.get("duration", ""),
                    "presenter_guide": "\n".join(
                        sl.get("speaker_notes", "")
                        for sl in s.get("slides", [])
                        if sl.get("speaker_notes")
                    ),
                    "key_messages": [
                        sl.get("title", "")
                        for sl in s.get("slides", [])
                        if sl.get("title")
                    ],
                    "anticipated_questions": [],
                    "suggested_answers": [],
                }
                for s in top_sections
            ]

        # If total_duration missing, compute from sections
        if not script_data.get("total_duration"):
            durations = [s.get("duration", "") for s in top_sections]
            total_min = 0
            for d in durations:
                import re
                m = re.search(r'(\d+)', d)
                if m:
                    total_min += int(m.group(1))
            script_data["total_duration"] = f"{total_min} minutes" if total_min else "45 minutes"

        # Ensure qa_preparation exists
        if not script_data.get("qa_preparation"):
            script_data["qa_preparation"] = {
                "expected_questions": [],
                "difficult_topics": [],
            }

        # Ensure introduction/closing exist
        if not script_data.get("introduction"):
            script_data["introduction"] = f"Presentation de la soutenance pour le projet {proj_name} aupres de {proj_client}."
        if not script_data.get("closing"):
            script_data["closing"] = "Merci pour votre attention. Nous restons a votre disposition pour toute question."
        if not script_data.get("general_tips"):
            script_data["general_tips"] = []

        # Store script as JSON bytes with a special marker
        script_json = _json.dumps(script_data, ensure_ascii=False, indent=2)
        store_export_result("soutenance_script", pid, script_json.encode("utf-8"), "script.json")

        # Persist to filesystem for durability (survives Redis TTL expiry)
        import os
        sout_dir = os.path.join(settings.export_dir, "soutenance", pid)
        os.makedirs(sout_dir, exist_ok=True)
        with open(os.path.join(sout_dir, pptx_filename), "wb") as f:
            f.write(pptx_bytes)
        with open(os.path.join(sout_dir, "script.json"), "w", encoding="utf-8") as f:
            f.write(script_json)
        # Store the pptx filename for later retrieval
        with open(os.path.join(sout_dir, ".pptx_filename"), "w") as f:
            f.write(pptx_filename)

        # Count slides for the message
        total_slides = 2  # cover + agenda
        for section in soutenance_data.get("sections", []):
            total_slides += 1  # divider
            total_slides += len(section.get("slides", []))
        if soutenance_data.get("key_figures"):
            total_slides += 1
        if soutenance_data.get("strengths"):
            total_slides += 1
        total_slides += 1  # closing

        set_progress(_NS_SOUTENANCE, pid, {
            "status": "completed", "step": "done", "progress": 100,
            "message": f"Soutenance generee : {total_slides} slides + script complet ({len(pptx_bytes) // 1024} KB)",
        })

    except Exception as e:
        logger.exception("Soutenance export failed for project %s", project_id)
        set_progress(_NS_SOUTENANCE, pid, {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        })
    finally:
        await task_engine.dispose()

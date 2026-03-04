"""Export/Import API routes."""
import asyncio
import uuid
import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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


class PreviewChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class DocumentQARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


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
                    company_name=getattr(project, 'company_name', '') or '',
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
        "company_name": getattr(project, 'company_name', '') or '',
        "rfp_reference": project.rfp_reference,
        "chapters": [
            build_preview(c, 1, str(i+1))
            for i, c in enumerate(root_chapters)
        ],
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
    preview_chat_task.delay(pid, str(project.workspace_id), request.message)

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
    from ..services.vector_service import VectorService
    from ..services.ai_service import create_ai_service

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

    ai_service = create_ai_service(config)

    # Semantic search across all documents
    search_results = VectorService.search(
        str(project_id), request.question, top_k=15,
    )

    if not search_results:
        return {
            "answer": "Je n'ai trouve aucun document pertinent pour repondre a cette question. Verifiez que des documents ont bien ete charges et traites dans le projet.",
            "sources": [],
        }

    # Build context from search results
    context_parts = []
    sources = []
    seen_sources = set()
    for r in search_results:
        content = r["content"]
        # Remove the "passage: " prefix added during indexing
        if content.startswith("passage: "):
            content = content[9:]
        doc_name = r.get("document_name", "Document inconnu")
        category = r.get("category", "")
        page = r.get("page_number", 0)
        cat_label = CATEGORY_LABELS.get(category, category)

        context_parts.append(
            f"[Source: {doc_name} ({cat_label}), page {page}]\n{content}"
        )

        source_key = f"{doc_name}|{page}"
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            sources.append({
                "document_name": doc_name,
                "category": category,
                "category_label": cat_label,
                "page_number": page,
                "score": r.get("score", 0),
                "excerpt": content[:200],
            })

    context_text = "\n\n---\n\n".join(context_parts)

    system_prompt = """Tu es un assistant expert en analyse de documents pour les appels d'offres.
L'utilisateur te pose des questions sur les documents charges dans le projet.
Tu dois repondre en te basant UNIQUEMENT sur les extraits de documents fournis ci-dessous.

Regles:
- Reponds de maniere precise et detaillee en te basant sur les documents.
- Cite TOUJOURS tes sources : indique le nom du document, la categorie et le numero de page entre parentheses. Exemple: (Source: cahier_des_charges.pdf, Nouvel AO, page 12)
- Si tu ne trouves pas l'information dans les extraits fournis, dis-le clairement.
- Quand l'utilisateur parle d'"ancien AO" ou "ancien appel d'offres", il fait reference aux documents de categorie "Ancien AO".
- Quand il parle d'"ancienne reponse", il fait reference aux documents de categorie "Ancienne Reponse".
- Quand il parle de "nouvel AO" ou "nouveau cahier des charges", il fait reference aux documents de categorie "Nouvel AO".
- Quand il parle de "notre reponse", il fait reference aux documents de categorie "Notre Reponse".
- Utilise le markdown pour structurer ta reponse (titres, listes, gras).
- Si la question porte sur une comparaison entre ancien et nouvel AO, compare les informations des documents des deux categories."""

    user_prompt = f"""Voici les extraits pertinents des documents du projet :

{context_text}

---

Question de l'utilisateur : {request.question}

Reponds en citant tes sources."""

    try:
        answer = await ai_service.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, timeout=120,
        )
    except Exception as e:
        logger.error("Document QA failed for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Erreur IA: {str(e)[:200]}")

    return {
        "answer": answer,
        "sources": sources[:10],
    }

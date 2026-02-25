"""Chapter API routes for content editing and AI generation."""
import asyncio
import uuid
import logging
from typing import Dict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.chapter import Chapter, ChapterType, ChapterStatus
from ..schemas.chapter import (
    ChapterCreate, ChapterUpdate, ChapterOut,
    ChapterContentRequest, AddNoteRequest, ReorderChaptersRequest,
    BulkDeleteChaptersRequest,
)
from ..services.ai_service import MistralAIService
from ..services.vector_service import VectorService
from ..services.anonymization_service import AnonymizationService
from .deps import get_current_user

router = APIRouter(prefix="/chapters", tags=["Chapters"])
logger = logging.getLogger(__name__)

# In-memory progress tracking for chapter generation
_chapter_gen_progress: Dict[str, dict] = {}

# Semaphore to limit concurrent chapter generations (avoids DB pool exhaustion)
_gen_semaphore = asyncio.Semaphore(3)


def _chapter_to_out(chapter: Chapter, children: list = None) -> ChapterOut:
    """Convert Chapter model to ChapterOut schema."""
    return ChapterOut(
        id=str(chapter.id),
        project_id=str(chapter.project_id),
        parent_id=str(chapter.parent_id) if chapter.parent_id else None,
        response_document_id=str(chapter.response_document_id) if chapter.response_document_id else None,
        title=chapter.title,
        description=chapter.description,
        order=chapter.order,
        chapter_type=chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
        content=chapter.content,
        status=chapter.status.value if hasattr(chapter.status, 'value') else str(chapter.status),
        notes=chapter.notes or [],
        improvement_axes=chapter.improvement_axes or [],
        source_references=chapter.source_references or [],
        image_references=chapter.image_references or [],
        rfp_requirement=chapter.rfp_requirement,
        is_prefilled=chapter.is_prefilled,
        numbering=chapter.numbering,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
        children=children or [],
    )


@router.get("/project/{project_id}", response_model=list[ChapterOut])
async def list_chapters(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all chapters in a project as a tree structure."""
    result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order)
    )
    all_chapters = result.scalars().all()

    # Build tree
    chapter_map = {c.id: c for c in all_chapters}
    children_map = {}
    root_chapters = []

    for c in all_chapters:
        if c.parent_id:
            children_map.setdefault(c.parent_id, []).append(c)
        else:
            root_chapters.append(c)

    def build_tree(chapter: Chapter) -> ChapterOut:
        children = children_map.get(chapter.id, [])
        child_outs = [build_tree(child) for child in sorted(children, key=lambda x: x.order)]
        return _chapter_to_out(chapter, child_outs)

    return [build_tree(c) for c in root_chapters]


@router.post("/project/{project_id}", response_model=ChapterOut, status_code=201)
async def create_chapter(
    project_id: uuid.UUID,
    request: ChapterCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chapter."""
    valid_types = {t.value for t in ChapterType}
    ch_type = request.chapter_type if request.chapter_type in valid_types else "chapter"
    chapter = Chapter(
        project_id=project_id,
        parent_id=uuid.UUID(request.parent_id) if request.parent_id else None,
        title=request.title,
        description=request.description,
        order=request.order,
        chapter_type=ch_type,
        rfp_requirement=request.rfp_requirement,
    )
    db.add(chapter)
    await db.commit()
    await db.refresh(chapter)

    return _chapter_to_out(chapter)


@router.get("/{chapter_id}", response_model=ChapterOut)
async def get_chapter(
    chapter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single chapter with its children."""
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    # Get children
    children_result = await db.execute(
        select(Chapter)
        .where(Chapter.parent_id == chapter_id)
        .order_by(Chapter.order)
    )
    children = children_result.scalars().all()

    return _chapter_to_out(chapter, [_chapter_to_out(c) for c in children])


@router.put("/{chapter_id}", response_model=ChapterOut)
async def update_chapter(
    chapter_id: uuid.UUID,
    request: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a chapter."""
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    if request.title is not None:
        chapter.title = request.title
    if request.description is not None:
        chapter.description = request.description
    if request.content is not None:
        chapter.content = request.content
    if request.status is not None:
        chapter.status = request.status
    if request.order is not None:
        chapter.order = request.order
    if request.notes is not None:
        chapter.notes = request.notes
    if request.improvement_axes is not None:
        chapter.improvement_axes = request.improvement_axes
    if request.rfp_requirement is not None:
        chapter.rfp_requirement = request.rfp_requirement

    await db.commit()
    await db.refresh(chapter)

    return _chapter_to_out(chapter)


@router.delete("/{chapter_id}", status_code=204)
async def delete_chapter(
    chapter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chapter and its children."""
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    await db.delete(chapter)
    await db.commit()


@router.post("/bulk-delete")
async def bulk_delete_chapters(
    request: BulkDeleteChaptersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple chapters and their children.

    Accepts a list of chapter IDs. Children are cascade-deleted automatically
    by the DB foreign key constraint, so only root-level IDs need to be passed.
    """
    uuids = [uuid.UUID(cid) for cid in request.chapter_ids]
    result = await db.execute(
        select(Chapter).where(Chapter.id.in_(uuids))
    )
    chapters = result.scalars().all()
    deleted = len(chapters)
    for ch in chapters:
        await db.delete(ch)
    await db.commit()
    return {"deleted": deleted}


@router.post("/{chapter_id}/note")
async def add_note(
    chapter_id: uuid.UUID,
    request: AddNoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a note to a chapter."""
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    notes = chapter.notes or []
    notes.append({
        "id": str(uuid.uuid4()),
        "content": request.content,
        "author": request.author or current_user.username,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    chapter.notes = notes

    await db.commit()
    return {"success": True, "notes": notes}


@router.post("/{chapter_id}/generate-content")
async def generate_chapter_content(
    chapter_id: uuid.UUID,
    request: ChapterContentRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch chapter content generation as a background task (returns immediately)."""
    cid = str(chapter_id)

    existing = _chapter_gen_progress.get(cid)
    if existing and existing.get("status") in ("running", "queued"):
        raise HTTPException(status_code=409, detail="Generation deja en cours pour ce chapitre")

    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    project_result = await db.execute(select(RFPProject).where(RFPProject.id == chapter.project_id))
    project = project_result.scalar_one()

    config_result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
    )
    config = config_result.scalar_one_or_none()
    if not config or not config.mistral_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Configuration IA non définie")

    _chapter_gen_progress[cid] = {
        "status": "queued", "step": "queued", "progress": 0,
        "message": "En file d'attente...",
    }

    background_tasks.add_task(
        _run_chapter_generation, chapter_id, chapter.project_id,
        project.workspace_id, request.action, request.custom_prompt or "",
        request.use_old_response, request.include_improvement_axes,
    )

    return {"success": True, "message": "Generation lancee en arriere-plan"}


@router.get("/{chapter_id}/generate-status")
async def get_chapter_gen_status(
    chapter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of chapter content generation."""
    cid = str(chapter_id)
    return _chapter_gen_progress.get(cid, {
        "status": "idle", "step": "idle", "progress": 0, "message": "",
    })


async def _run_chapter_generation(
    chapter_id: uuid.UUID, project_id: uuid.UUID, workspace_id: uuid.UUID,
    action: str, custom_prompt: str, use_old_response: bool, include_improvement_axes: bool,
):
    """Background task for chapter content generation.

    Uses a semaphore to limit concurrent generations and avoid DB pool exhaustion.
    DB connections are acquired only for short reads/writes and released during
    slow AI calls to minimize pool pressure.
    """
    from ..database import async_session
    cid = str(chapter_id)

    def _update(step: str, progress: int, message: str):
        _chapter_gen_progress[cid] = {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        }

    try:
        # Wait for a slot in the concurrency pool
        async with _gen_semaphore:
            _update("starting", 0, "Demarrage de la generation...")

            # ── Phase 1: Read data + anonymize (short DB session) ──
            async with async_session() as db:
                config_result = await db.execute(
                    select(AIConfig).where(AIConfig.workspace_id == workspace_id)
                )
                config = config_result.scalar_one_or_none()
                ai_service = MistralAIService.from_config(config, config.mistral_api_key_encrypted)

                result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
                chapter = result.scalar_one()
                project_result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
                project = project_result.scalar_one()

                # Capture plain data we need for AI calls
                ch_title = chapter.title
                ch_description = chapter.description
                ch_rfp_requirement = chapter.rfp_requirement
                ch_content = chapter.content or ""
                ch_notes = chapter.notes or []
                proj_improvement = project.improvement_axes if include_improvement_axes else ""
                proj_ai_context = project.ai_context or ""

                if action == "custom" and custom_prompt:
                    _update("anonymizing", 15, "Anonymisation du contenu...")
                    anon_content = await AnonymizationService.anonymize_text(ch_content, project_id, db)
                    anon_prompt = await AnonymizationService.anonymize_text(custom_prompt, project_id, db)
                    ai_params = {"mode": "custom", "anon_content": anon_content, "anon_prompt": anon_prompt}

                elif action == "enrich" and ch_content:
                    _update("anonymizing", 15, "Anonymisation du contenu...")
                    anon_content = await AnonymizationService.anonymize_text(ch_content, project_id, db)
                    ai_params = {"mode": "enrich", "anon_content": anon_content}

                else:
                    _update("searching", 10, "Recherche de contenu pertinent...")
                    old_response_content = ""
                    search_results = []
                    if use_old_response:
                        search_results = VectorService.search(
                            str(project_id),
                            f"{ch_title} {ch_description}",
                            top_k=5, category_filter="old_response",
                        )
                    context_results = VectorService.search(
                        str(project_id),
                        f"{ch_title} {ch_rfp_requirement}",
                        top_k=3,
                    )
                    context_chunks_text = "\n\n".join([r["content"] for r in context_results]) if context_results else ""

                    _update("anonymizing", 25, "Anonymisation...")
                    if search_results:
                        raw_old = "\n\n".join([r["content"] for r in search_results])
                        old_response_content = await AnonymizationService.anonymize_text(raw_old, project_id, db)

                    notes_text = "\n".join([n.get("content", "") for n in ch_notes])
                    ai_params = {
                        "mode": "generate",
                        "old_response_content": old_response_content,
                        "context_chunks_text": context_chunks_text,
                        "notes_text": notes_text,
                    }
            # DB connection released here

            # ── Phase 2: AI generation (NO DB connection held) ──
            mode = ai_params["mode"]
            if mode == "custom":
                _update("generating", 35, "Generation IA en cours...")
                result_text = await ai_service.execute_custom_prompt(
                    ai_params["anon_content"], ai_params["anon_prompt"], ch_title,
                    ai_context=proj_ai_context,
                )
            elif mode == "enrich":
                _update("generating", 35, "Enrichissement IA en cours...")
                result_text = await ai_service.enrich_content(
                    ai_params["anon_content"], ch_title, ch_rfp_requirement, proj_improvement,
                    ai_context=proj_ai_context,
                )
            else:
                _update("generating", 40, "Generation IA du contenu...")
                result_text = await ai_service.generate_chapter_content(
                    chapter_title=ch_title,
                    chapter_description=ch_description,
                    rfp_requirement=ch_rfp_requirement,
                    old_response_content=ai_params["old_response_content"],
                    context_chunks=ai_params["context_chunks_text"],
                    improvement_axes=proj_improvement,
                    notes=ai_params["notes_text"],
                    ai_context=proj_ai_context,
                )

            # ── Phase 3: Deanonymize + save (short DB session) ──
            _update("deanonymizing", 80, "Deanonymisation...")
            async with async_session() as db:
                final_content = await AnonymizationService.deanonymize_text(result_text, project_id, db)

                _update("saving", 90, "Enregistrement...")
                chap_result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
                chap = chap_result.scalar_one()
                chap.content = final_content
                chap.status = ChapterStatus.IN_PROGRESS
                await db.commit()

        _chapter_gen_progress[cid] = {
            "status": "completed", "step": "done", "progress": 100,
            "message": "Contenu genere avec succes",
        }

    except Exception as e:
        logger.exception("Chapter generation failed for chapter %s", chapter_id)
        _chapter_gen_progress[cid] = {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


@router.post("/reorder")
async def reorder_chapters(
    request: ReorderChaptersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder chapters."""
    for item in request.chapter_orders:
        chapter_id = uuid.UUID(item["id"])
        new_order = item["order"]
        result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
        chapter = result.scalar_one_or_none()
        if chapter:
            chapter.order = new_order

    await db.commit()
    return {"success": True}

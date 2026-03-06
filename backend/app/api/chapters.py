"""Chapter API routes for content editing and AI generation."""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.chapter import Chapter, ChapterType, ChapterStatus
from ..schemas.chapter import (
    ChapterCreate, ChapterUpdate, ChapterOut,
    ChapterContentRequest, AddNoteRequest, ReorderChaptersRequest,
    BulkDeleteChaptersRequest,
)
from ..services.progress_service import get_or_idle, set_progress
from ..services.moderation_service import moderate_prompt, moderate_prompt_llm
from .deps import get_current_user

router = APIRouter(prefix="/chapters", tags=["Chapters"])
logger = logging.getLogger(__name__)

# Redis namespace for chapter generation progress
_NS = "chapter_gen"


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
    """Delete multiple chapters and their children."""
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
    moderation = moderate_prompt(request.content, "note")
    if not moderation:
        raise HTTPException(status_code=422, detail=moderation.message)

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch chapter content generation as a Celery background task."""
    cid = str(chapter_id)

    existing = get_or_idle(_NS, cid)
    if existing.get("status") in ("running", "queued"):
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

    # Moderate the custom prompt (regex + LLM) before dispatching
    if request.custom_prompt:
        from ..security import decrypt_api_key
        scw_key = decrypt_api_key(config.scaleway_api_key_encrypted or "") if config.scaleway_api_key_encrypted else ""
        moderation = await moderate_prompt_llm(
            request.custom_prompt,
            field_name="custom_prompt",
            api_key=scw_key,
            scaleway_project_id=config.scaleway_project_id or "",
        )
        if not moderation:
            raise HTTPException(status_code=422, detail=moderation.message)

    set_progress(_NS, cid, {
        "status": "queued", "step": "queued", "progress": 0,
        "message": "En file d'attente...",
    })

    # Dispatch to Celery worker
    from ..tasks.chapter_tasks import generate_chapter_content_task
    generate_chapter_content_task.delay(
        cid, str(chapter.project_id), str(project.workspace_id),
        request.action, request.custom_prompt or "",
        request.use_old_response, request.include_improvement_axes,
    )

    return {"success": True, "message": "Generation lancee en arriere-plan"}


@router.get("/{chapter_id}/generate-status")
async def get_chapter_gen_status(
    chapter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of chapter content generation."""
    return get_or_idle(_NS, str(chapter_id))


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

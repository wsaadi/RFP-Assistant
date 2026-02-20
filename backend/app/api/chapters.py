"""Chapter API routes for content editing and AI generation."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.chapter import Chapter, ChapterStatus
from ..schemas.chapter import (
    ChapterCreate, ChapterUpdate, ChapterOut,
    ChapterContentRequest, AddNoteRequest, ReorderChaptersRequest,
)
from ..services.ai_service import MistralAIService
from ..services.vector_service import VectorService
from ..services.anonymization_service import AnonymizationService
from .deps import get_current_user

router = APIRouter(prefix="/chapters", tags=["Chapters"])


def _chapter_to_out(chapter: Chapter, children: list = None) -> ChapterOut:
    """Convert Chapter model to ChapterOut schema."""
    return ChapterOut(
        id=str(chapter.id),
        project_id=str(chapter.project_id),
        parent_id=str(chapter.parent_id) if chapter.parent_id else None,
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
    chapter = Chapter(
        project_id=project_id,
        parent_id=uuid.UUID(request.parent_id) if request.parent_id else None,
        title=request.title,
        description=request.description,
        order=request.order,
        chapter_type=request.chapter_type,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate or enrich content for a chapter using AI."""
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    # Get project and AI config
    project_result = await db.execute(select(RFPProject).where(RFPProject.id == chapter.project_id))
    project = project_result.scalar_one()

    config_result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
    )
    config = config_result.scalar_one_or_none()
    if not config or not config.mistral_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Configuration IA non définie")

    ai_service = MistralAIService.from_config(config, config.mistral_api_key_encrypted)

    if request.action == "custom" and request.custom_prompt:
        # Custom prompt
        anon_content = await AnonymizationService.anonymize_text(
            chapter.content, chapter.project_id, db
        )
        anon_prompt = await AnonymizationService.anonymize_text(
            request.custom_prompt, chapter.project_id, db
        )
        result_text = await ai_service.execute_custom_prompt(
            anon_content, anon_prompt, chapter.title
        )
        chapter.content = await AnonymizationService.deanonymize_text(
            result_text, chapter.project_id, db
        )

    elif request.action == "enrich" and chapter.content:
        # Enrich existing content
        anon_content = await AnonymizationService.anonymize_text(
            chapter.content, chapter.project_id, db
        )
        improvement = project.improvement_axes if request.include_improvement_axes else ""
        result_text = await ai_service.enrich_content(
            anon_content, chapter.title, chapter.rfp_requirement, improvement
        )
        chapter.content = await AnonymizationService.deanonymize_text(
            result_text, chapter.project_id, db
        )

    else:
        # Generate new content
        old_response_content = ""
        context_chunks_text = ""

        if request.use_old_response:
            search_results = VectorService.search(
                str(chapter.project_id),
                f"{chapter.title} {chapter.description}",
                top_k=5,
                category_filter="old_response",
            )
            if search_results:
                old_response_content = "\n\n".join([r["content"] for r in search_results])
                old_response_content = await AnonymizationService.anonymize_text(
                    old_response_content, chapter.project_id, db
                )

        # Get context from all documents
        context_results = VectorService.search(
            str(chapter.project_id),
            f"{chapter.title} {chapter.rfp_requirement}",
            top_k=3,
        )
        if context_results:
            context_chunks_text = "\n\n".join([r["content"] for r in context_results])

        notes_text = "\n".join([n.get("content", "") for n in (chapter.notes or [])])
        improvement = project.improvement_axes if request.include_improvement_axes else ""

        result_text = await ai_service.generate_chapter_content(
            chapter_title=chapter.title,
            chapter_description=chapter.description,
            rfp_requirement=chapter.rfp_requirement,
            old_response_content=old_response_content,
            context_chunks=context_chunks_text,
            improvement_axes=improvement,
            notes=notes_text,
        )

        chapter.content = await AnonymizationService.deanonymize_text(
            result_text, chapter.project_id, db
        )

    chapter.status = ChapterStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(chapter)

    return {"success": True, "content": chapter.content}


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

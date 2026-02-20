"""RFP Project API routes."""
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..models.user import User
from ..models.workspace import WorkspaceMember
from ..models.project import RFPProject, AIConfig, AnonymizationMapping, ProjectStatus
from ..models.document import Document, DocumentChunk
from ..models.chapter import Chapter, ChapterType, ChapterStatus
from ..schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut,
    ImprovementAxisRequest, GapAnalysisRequest,
    GenerateStructureRequest, PrefillRequest, ComplianceAnalysisRequest,
)
from ..schemas.document import StatisticsOut, AnonymizationMappingOut
from ..services.ai_service import MistralAIService
from ..services.vector_service import VectorService
from ..services.anonymization_service import AnonymizationService
from .deps import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])


async def _get_ai_service(workspace_id: uuid.UUID, db: AsyncSession) -> MistralAIService:
    """Helper to get AI service from workspace config."""
    result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == workspace_id)
    )
    config = result.scalar_one_or_none()
    if not config or not config.mistral_api_key_encrypted:
        raise HTTPException(
            status_code=400,
            detail="Configuration IA non définie. Configurez la clé API Mistral dans l'administration.",
        )
    return MistralAIService.from_config(config, config.mistral_api_key_encrypted)


@router.get("/workspace/{workspace_id}", response_model=list[ProjectOut])
async def list_projects(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects in a workspace."""
    result = await db.execute(
        select(RFPProject)
        .where(RFPProject.workspace_id == workspace_id)
        .order_by(RFPProject.updated_at.desc())
    )
    projects = result.scalars().all()

    project_list = []
    for p in projects:
        doc_count = (await db.execute(
            select(func.count()).where(Document.project_id == p.id)
        )).scalar() or 0
        ch_count = (await db.execute(
            select(func.count()).where(Chapter.project_id == p.id)
        )).scalar() or 0

        project_list.append(ProjectOut(
            id=str(p.id),
            workspace_id=str(p.workspace_id),
            name=p.name,
            description=p.description,
            client_name=p.client_name,
            rfp_reference=p.rfp_reference,
            deadline=p.deadline,
            status=p.status.value,
            improvement_axes=p.improvement_axes,
            created_by=str(p.created_by),
            created_at=p.created_at,
            updated_at=p.updated_at,
            document_count=doc_count,
            chapter_count=ch_count,
        ))
    return project_list


@router.post("/workspace/{workspace_id}", response_model=ProjectOut, status_code=201)
async def create_project(
    workspace_id: uuid.UUID,
    request: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new RFP project."""
    project = RFPProject(
        workspace_id=workspace_id,
        name=request.name,
        description=request.description,
        client_name=request.client_name,
        rfp_reference=request.rfp_reference,
        deadline=request.deadline,
        created_by=current_user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectOut(
        id=str(project.id),
        workspace_id=str(project.workspace_id),
        name=project.name,
        description=project.description,
        client_name=project.client_name,
        rfp_reference=project.rfp_reference,
        deadline=project.deadline,
        status=project.status.value,
        improvement_axes=project.improvement_axes,
        created_by=str(project.created_by),
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=0,
        chapter_count=0,
    )


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    doc_count = (await db.execute(
        select(func.count()).where(Document.project_id == project_id)
    )).scalar() or 0
    ch_count = (await db.execute(
        select(func.count()).where(Chapter.project_id == project_id)
    )).scalar() or 0

    return ProjectOut(
        id=str(project.id),
        workspace_id=str(project.workspace_id),
        name=project.name,
        description=project.description,
        client_name=project.client_name,
        rfp_reference=project.rfp_reference,
        deadline=project.deadline,
        status=project.status.value,
        improvement_axes=project.improvement_axes,
        created_by=str(project.created_by),
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=doc_count,
        chapter_count=ch_count,
    )


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    request: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update project details."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    for field in ["name", "description", "client_name", "rfp_reference", "deadline", "improvement_axes"]:
        value = getattr(request, field, None)
        if value is not None:
            setattr(project, field, value)
    if request.status is not None:
        project.status = request.status

    await db.commit()
    await db.refresh(project)

    return await get_project(project_id, current_user, db)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and all its data."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    VectorService.delete_project_data(str(project_id))
    await db.delete(project)
    await db.commit()


# ── AI-powered features ──

@router.post("/{project_id}/gap-analysis")
async def analyze_gap(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze gaps between old and new RFP."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    ai_service = await _get_ai_service(project.workspace_id, db)

    # Get old RFP chunks
    old_rfp_chunks = VectorService.search(str(project_id), "exigences appel d'offres", top_k=20, category_filter="old_rfp")
    old_rfp_content = "\n\n".join([c["content"] for c in old_rfp_chunks])

    # Get new RFP chunks
    new_rfp_chunks = VectorService.search(str(project_id), "exigences appel d'offres", top_k=20, category_filter="new_rfp")
    new_rfp_content = "\n\n".join([c["content"] for c in new_rfp_chunks])

    if not old_rfp_content or not new_rfp_content:
        raise HTTPException(
            status_code=400,
            detail="Documents d'ancien et/ou de nouvel appel d'offres manquants ou non indexés",
        )

    # Anonymize before sending to AI
    anon_old = await AnonymizationService.anonymize_text(old_rfp_content, project_id, db)
    anon_new = await AnonymizationService.anonymize_text(new_rfp_content, project_id, db)

    analysis = await ai_service.analyze_gap(anon_old, anon_new)

    # Deanonymize the response
    for key in ["summary"]:
        if key in analysis and isinstance(analysis[key], str):
            analysis[key] = await AnonymizationService.deanonymize_text(analysis[key], project_id, db)

    return {"success": True, "analysis": analysis}


@router.post("/{project_id}/generate-structure")
async def generate_structure(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate the complete response structure from the new RFP."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    ai_service = await _get_ai_service(project.workspace_id, db)

    # Get new RFP content
    new_rfp_chunks = VectorService.search(str(project_id), "structure exigences chapitres", top_k=30, category_filter="new_rfp")
    rfp_content = "\n\n".join([c["content"] for c in new_rfp_chunks])

    if not rfp_content:
        raise HTTPException(status_code=400, detail="Aucun document de nouvel appel d'offres indexé")

    # Get old response structure if available
    old_chapters = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .where(Chapter.parent_id.is_(None))
        .order_by(Chapter.order)
    )
    existing = old_chapters.scalars().all()
    old_structure = "\n".join([f"- {c.title}: {c.description}" for c in existing]) if existing else ""

    # Anonymize
    anon_rfp = await AnonymizationService.anonymize_text(rfp_content, project_id, db)

    structure = await ai_service.generate_response_structure(anon_rfp, old_structure)

    # Create chapters from structure
    order = 0
    created_chapters = []

    async def create_chapters_recursive(items, parent_id=None):
        nonlocal order
        for item in items:
            order += 1
            chapter = Chapter(
                project_id=project_id,
                parent_id=parent_id,
                title=item.get("title", ""),
                description=item.get("description", ""),
                order=order,
                chapter_type=item.get("chapter_type", "chapter"),
                rfp_requirement=item.get("rfp_requirement", ""),
            )
            db.add(chapter)
            await db.flush()
            created_chapters.append(chapter)

            children = item.get("children", [])
            if children:
                await create_chapters_recursive(children, parent_id=chapter.id)

    await create_chapters_recursive(structure)
    await db.commit()

    return {
        "success": True,
        "chapters_created": len(created_chapters),
        "message": f"{len(created_chapters)} chapitres créés",
    }


@router.post("/{project_id}/prefill")
async def prefill_chapters(
    project_id: uuid.UUID,
    request: PrefillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pre-fill chapters with content from old response where relevant."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    ai_service = await _get_ai_service(project.workspace_id, db)

    # Get chapters to prefill
    query = select(Chapter).where(Chapter.project_id == project_id)
    if request.chapter_ids:
        chapter_uuids = [uuid.UUID(cid) for cid in request.chapter_ids]
        query = query.where(Chapter.id.in_(chapter_uuids))
    result = await db.execute(query.order_by(Chapter.order))
    chapters = result.scalars().all()

    prefilled = 0
    tasks = []

    for chapter in chapters:
        if chapter.content:
            continue

        # Search old response for relevant content
        search_query = f"{chapter.title} {chapter.description}"
        old_response_chunks = VectorService.search(
            str(project_id), search_query, top_k=5, category_filter="old_response"
        )

        if old_response_chunks:
            old_content = "\n\n".join([c["content"] for c in old_response_chunks])
            anon_content = await AnonymizationService.anonymize_text(old_content, project_id, db)

            content = await ai_service.generate_chapter_content(
                chapter_title=chapter.title,
                chapter_description=chapter.description,
                rfp_requirement=chapter.rfp_requirement,
                old_response_content=anon_content,
            )

            # Deanonymize
            chapter.content = await AnonymizationService.deanonymize_text(content, project_id, db)
            chapter.is_prefilled = True
            chapter.status = ChapterStatus.IN_PROGRESS
            chapter.source_references = [
                {"document": c["document_name"], "page": c["page_number"], "score": c["score"]}
                for c in old_response_chunks[:3]
            ]
            prefilled += 1

    await db.commit()

    return {
        "success": True,
        "prefilled_count": prefilled,
        "message": f"{prefilled} chapitres pré-remplis",
    }


@router.post("/{project_id}/compliance-analysis")
async def analyze_compliance(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze exhaustiveness and compliance of the current response."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    ai_service = await _get_ai_service(project.workspace_id, db)

    # Get all chapter content
    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order)
    )
    chapters = chapters_result.scalars().all()
    response_content = "\n\n".join([
        f"## {c.title}\n{c.content}" for c in chapters if c.content
    ])

    # Get new RFP requirements
    new_rfp_chunks = VectorService.search(str(project_id), "exigences critères évaluation", top_k=25, category_filter="new_rfp")
    rfp_requirements = "\n\n".join([c["content"] for c in new_rfp_chunks])

    if not rfp_requirements:
        raise HTTPException(status_code=400, detail="Aucun document d'appel d'offres indexé")

    # Anonymize
    anon_response = await AnonymizationService.anonymize_text(response_content, project_id, db)
    anon_rfp = await AnonymizationService.anonymize_text(rfp_requirements, project_id, db)

    analysis = await ai_service.analyze_compliance(anon_response, anon_rfp)

    return {"success": True, "analysis": analysis}


@router.post("/{project_id}/improvement-axes")
async def add_improvement_axis(
    project_id: uuid.UUID,
    request: ImprovementAxisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add improvement axes from client feedback."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    existing = project.improvement_axes or ""
    source_info = f" (Source: {request.source})" if request.source else ""
    project.improvement_axes = existing + f"\n- {request.content}{source_info}" if existing else f"- {request.content}{source_info}"

    await db.commit()
    return {"success": True, "message": "Axe d'amélioration ajouté"}


@router.get("/{project_id}/statistics", response_model=StatisticsOut)
async def get_statistics(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project statistics."""
    # Count chapters by status
    chapters_result = await db.execute(
        select(Chapter).where(Chapter.project_id == project_id)
    )
    chapters = chapters_result.scalars().all()

    total_content = " ".join([c.content for c in chapters if c.content])
    total_words = len(total_content.split()) if total_content else 0
    total_chars = len(total_content) if total_content else 0
    total_pages = max(1, total_words // 300)  # ~300 words per page estimate

    completed = sum(1 for c in chapters if c.status == ChapterStatus.COMPLETED)
    in_progress = sum(1 for c in chapters if c.status == ChapterStatus.IN_PROGRESS)

    # Count documents
    doc_count = (await db.execute(
        select(func.count()).where(Document.project_id == project_id)
    )).scalar() or 0

    # Count anonymized entities
    anon_count = (await db.execute(
        select(func.count()).where(AnonymizationMapping.project_id == project_id)
    )).scalar() or 0

    # Count images
    from ..models.document import DocumentImage
    img_count_result = await db.execute(
        select(func.count())
        .select_from(DocumentImage)
        .join(Document, Document.id == DocumentImage.document_id)
        .where(Document.project_id == project_id)
    )
    img_count = img_count_result.scalar() or 0

    completion = (completed / len(chapters) * 100) if chapters else 0

    return StatisticsOut(
        total_pages=total_pages,
        total_words=total_words,
        total_characters=total_chars,
        anonymized_entities=anon_count,
        chapters_completed=completed,
        chapters_total=len(chapters),
        chapters_in_progress=in_progress,
        documents_count=doc_count,
        images_count=img_count,
        completion_percentage=round(completion, 1),
    )


@router.get("/{project_id}/anonymization-mappings", response_model=list[AnonymizationMappingOut])
async def get_anonymization_mappings(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all anonymization mappings for a project."""
    result = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.project_id == project_id)
        .order_by(AnonymizationMapping.entity_type)
    )
    mappings = result.scalars().all()

    return [
        AnonymizationMappingOut(
            id=str(m.id),
            entity_type=m.entity_type.value,
            original_value=m.original_value,
            anonymized_value=m.anonymized_value,
            is_active=m.is_active,
        )
        for m in mappings
    ]

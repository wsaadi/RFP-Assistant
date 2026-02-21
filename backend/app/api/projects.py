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
from ..schemas.document import StatisticsOut, AnonymizationMappingOut, AnonymizationReportOut, AnonymizationEntityGroup
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
    """Generate the complete response structure by deeply analyzing the new RFP,
    comparing with old RFP, and leveraging the old response."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    ai_service = await _get_ai_service(project.workspace_id, db)
    pid = str(project_id)

    # ── 1. Gather NEW RFP content (multiple queries for full coverage) ──
    new_rfp_queries = [
        "sommaire structure plan chapitres organisation document",
        "exigences techniques spécifications prestations attendues",
        "critères évaluation notation jugement offres",
        "annexes documents à fournir pièces administratives",
        "lots allotissement périmètre objet du marché",
        "conditions exécution délais planning livrables",
    ]
    new_rfp_all_chunks = {}
    for query in new_rfp_queries:
        chunks = VectorService.search(pid, query, top_k=15, category_filter="new_rfp")
        for c in chunks:
            new_rfp_all_chunks[c["chunk_id"]] = c

    # Sort by page number for logical order
    new_rfp_sorted = sorted(new_rfp_all_chunks.values(), key=lambda c: (c.get("page_number", 0)))
    new_rfp_content = "\n\n".join([c["content"] for c in new_rfp_sorted])

    if not new_rfp_content:
        raise HTTPException(status_code=400, detail="Aucun document de nouvel appel d'offres indexé")

    # ── 2. Gather OLD RFP content ──
    old_rfp_chunks = {}
    for query in ["exigences techniques spécifications", "structure chapitres sommaire", "critères évaluation lots"]:
        chunks = VectorService.search(pid, query, top_k=15, category_filter="old_rfp")
        for c in chunks:
            old_rfp_chunks[c["chunk_id"]] = c
    old_rfp_sorted = sorted(old_rfp_chunks.values(), key=lambda c: (c.get("page_number", 0)))
    old_rfp_content = "\n\n".join([c["content"] for c in old_rfp_sorted])

    # ── 3. Gather OLD RESPONSE content (actual text, not just titles) ──
    old_response_chunks = {}
    for query in ["présentation méthodologie organisation", "compétences références expérience", "solution technique offre proposition"]:
        chunks = VectorService.search(pid, query, top_k=15, category_filter="old_response")
        for c in chunks:
            old_response_chunks[c["chunk_id"]] = c
    old_response_sorted = sorted(old_response_chunks.values(), key=lambda c: (c.get("page_number", 0)))
    old_response_content = "\n\n".join([c["content"] for c in old_response_sorted])

    # ── 4. Run gap analysis if both old and new RFP available ──
    gap_analysis = None
    if old_rfp_content and new_rfp_content:
        anon_old_rfp = await AnonymizationService.anonymize_text(old_rfp_content, project_id, db)
        anon_new_rfp_gap = await AnonymizationService.anonymize_text(new_rfp_content, project_id, db)
        gap_analysis = await ai_service.analyze_gap(anon_old_rfp, anon_new_rfp_gap)

    # ── 5. Anonymize all content before sending to AI ──
    anon_new_rfp = await AnonymizationService.anonymize_text(new_rfp_content, project_id, db)
    anon_old_rfp = await AnonymizationService.anonymize_text(old_rfp_content, project_id, db) if old_rfp_content else ""
    anon_old_response = await AnonymizationService.anonymize_text(old_response_content, project_id, db) if old_response_content else ""

    # ── 6. Generate structure with full context ──
    structure = await ai_service.generate_response_structure(
        new_rfp_content=anon_new_rfp,
        old_rfp_content=anon_old_rfp,
        old_response_content=anon_old_response,
        gap_analysis=gap_analysis,
    )

    # ── 7. Create chapters from structure ──
    order = 0
    created_chapters = []
    delta_stats = {"new": 0, "modified": 0, "unchanged": 0}

    async def create_chapters_recursive(items, parent_id=None):
        nonlocal order
        for item in items:
            order += 1
            delta = item.get("delta", "unchanged")
            if delta in delta_stats:
                delta_stats[delta] += 1

            # Store delta info in notes for UI display
            notes = []
            if delta and delta != "unchanged":
                notes.append({"type": "delta", "value": delta})

            chapter = Chapter(
                project_id=project_id,
                parent_id=parent_id,
                title=item.get("title", ""),
                description=item.get("description", ""),
                order=order,
                chapter_type=item.get("chapter_type", "chapter"),
                rfp_requirement=item.get("rfp_requirement", ""),
                notes=notes,
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
        "delta_stats": delta_stats,
        "has_gap_analysis": gap_analysis is not None,
        "message": f"{len(created_chapters)} chapitres créés ({delta_stats['new']} nouveaux, {delta_stats['modified']} modifiés, {delta_stats['unchanged']} inchangés)",
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


@router.get("/{project_id}/anonymization-report", response_model=AnonymizationReportOut)
async def get_anonymization_report(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a structured anonymization report with statistics and samples."""
    from ..models.project import EntityType
    from collections import defaultdict

    result = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.project_id == project_id)
        .order_by(AnonymizationMapping.entity_type, AnonymizationMapping.created_at)
    )
    all_mappings = result.scalars().all()

    # Group by entity type
    groups_dict = defaultdict(list)
    for m in all_mappings:
        groups_dict[m.entity_type].append(m)

    # Human-readable labels
    type_labels = {
        EntityType.COMPANY: "Entreprises / Organisations",
        EntityType.PERSON: "Personnes",
        EntityType.EMAIL: "Adresses email",
        EntityType.PHONE: "Numéros de téléphone",
        EntityType.ADDRESS: "Adresses postales",
        EntityType.PROJECT_CODE: "Codes projet",
        EntityType.RFP_CODE: "Codes AO",
        EntityType.SOLUTION_NAME: "Noms de solutions",
        EntityType.DATE: "Dates",
        EntityType.AMOUNT: "Montants",
        EntityType.OTHER: "Autres entités",
    }

    entity_groups = []
    for entity_type in EntityType:
        mappings_for_type = groups_dict.get(entity_type, [])
        if not mappings_for_type:
            continue
        entity_groups.append(AnonymizationEntityGroup(
            entity_type=entity_type.value,
            label=type_labels.get(entity_type, entity_type.value),
            count=len(mappings_for_type),
            mappings=[
                AnonymizationMappingOut(
                    id=str(m.id),
                    entity_type=m.entity_type.value,
                    original_value=m.original_value,
                    anonymized_value=m.anonymized_value,
                    is_active=m.is_active,
                )
                for m in mappings_for_type
            ],
        ))

    # Generate a sample before/after from a real document chunk
    sample_before = ""
    sample_after = ""
    chunk_result = await db.execute(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.project_id == project_id)
        .where(DocumentChunk.anonymized_content != "")
        .where(DocumentChunk.anonymized_content != DocumentChunk.content)
        .limit(1)
    )
    sample_chunk = chunk_result.scalar_one_or_none()
    if sample_chunk:
        sample_before = sample_chunk.content[:500]
        sample_after = sample_chunk.anonymized_content[:500]

    active_count = sum(1 for m in all_mappings if m.is_active)

    return AnonymizationReportOut(
        total_entities=len(all_mappings),
        active_entities=active_count,
        entity_groups=entity_groups,
        sample_before=sample_before,
        sample_after=sample_after,
    )

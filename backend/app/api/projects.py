"""RFP Project API routes."""
import uuid
import asyncio
import logging
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..models.user import User
from ..models.workspace import WorkspaceMember
from ..models.project import RFPProject, AIConfig, AnonymizationMapping, ProjectStatus
from ..models.document import Document, DocumentChunk, DocumentCategory
from ..models.chapter import Chapter, ChapterType, ChapterStatus
from ..models.response_document import ResponseDocument, DocumentFormat, ContentType
from ..schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut,
    ImprovementAxisRequest, GapAnalysisRequest,
    GenerateStructureRequest, PrefillRequest, ComplianceAnalysisRequest,
)
from ..schemas.document import StatisticsOut, AnonymizationMappingOut, AnonymizationReportOut, AnonymizationEntityGroup
from ..schemas.response_document import ResponseDocumentOut, ResponseDocumentUpdate, BulkUpdateSelectionRequest
from ..services.ai_service import MistralAIService
from ..services.vector_service import VectorService
from ..services.anonymization_service import AnonymizationService
from .deps import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])
logger = logging.getLogger(__name__)

# In-memory progress tracking for long-running generation tasks
_generation_progress: Dict[str, dict] = {}
_prefill_progress: Dict[str, dict] = {}


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


async def _get_all_chunks_by_category(
    db: AsyncSession, project_id: uuid.UUID, category: DocumentCategory
) -> str:
    """Get ALL document chunks for a category, ordered sequentially.
    Returns the full concatenated text."""
    result = await db.execute(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.project_id == project_id)
        .where(Document.category == category)
        .order_by(Document.original_filename, DocumentChunk.page_number, DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    return "\n\n".join([c.content for c in chunks if c.content.strip()])


async def _get_all_chunks_anonymized_by_category(
    db: AsyncSession, project_id: uuid.UUID, category: DocumentCategory
) -> str:
    """Get ALL pre-anonymized document chunks for a category.
    Uses anonymized_content already computed at upload time, avoiding
    redundant GLiNER inference."""
    result = await db.execute(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.project_id == project_id)
        .where(Document.category == category)
        .order_by(Document.original_filename, DocumentChunk.page_number, DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    return "\n\n".join([
        (c.anonymized_content or c.content) for c in chunks if (c.anonymized_content or c.content).strip()
    ])


@router.post("/{project_id}/generate-structure")
async def generate_structure(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch structure generation as a background task (returns immediately)."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # Quick check: has new RFP docs?
    doc_count = (await db.execute(
        select(func.count()).select_from(Document)
        .where(Document.project_id == project_id)
        .where(Document.category == DocumentCategory.NEW_RFP)
    )).scalar() or 0
    if doc_count == 0:
        raise HTTPException(status_code=400, detail="Aucun document de nouvel appel d'offres indexe")

    pid = str(project_id)

    # Check if already running
    existing = _generation_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Generation deja en cours")

    workspace_id = project.workspace_id
    _generation_progress[pid] = {
        "status": "running",
        "step": "starting",
        "progress": 0,
        "message": "Demarrage de la generation...",
    }

    background_tasks.add_task(_run_structure_generation, project_id, workspace_id)

    return {"success": True, "message": "Generation lancee en arriere-plan"}


@router.get("/{project_id}/generation-status")
async def get_generation_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of the structure generation task."""
    pid = str(project_id)
    return _generation_progress.get(pid, {
        "status": "idle",
        "step": "idle",
        "progress": 0,
        "message": "",
    })


def _make_stream_progress_callback(pid: str, step: str, start_pct: int, end_pct: int, label: str, max_tokens: int):
    """Create a streaming progress callback for use with generate_streaming().

    Returns an async callback(token_count, char_count) that updates
    _generation_progress based on *real* tokens received from Mistral.
    """
    import time
    t0 = time.monotonic()

    async def _on_progress(token_count: int, char_count: int):
        elapsed = int(time.monotonic() - t0)
        # Real progress based on actual tokens received vs expected max
        ratio = min(token_count / max_tokens, 0.95)
        pct = start_pct + int((end_pct - start_pct) * ratio)
        _generation_progress[pid] = {
            "status": "running",
            "step": step,
            "progress": pct,
            "message": f"{label} — {token_count} tokens recus ({char_count:,} car.) — {elapsed}s",
        }

    return _on_progress


async def _run_structure_generation(project_id: uuid.UUID, workspace_id: uuid.UUID):
    """Background task for the full structure generation pipeline."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _generation_progress[pid] = {
            "status": "running",
            "step": step,
            "progress": progress,
            "message": message,
        }

    try:
        # ── Phase 1: Load data from DB (short-lived session) ──
        async with async_session() as db:
            ai_service = await _get_ai_service(workspace_id, db)

            _update("loading", 5, "Chargement des documents du nouvel AO...")
            anon_new_rfp = await _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.NEW_RFP)
            if not anon_new_rfp:
                _generation_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "Aucun document de nouvel appel d'offres indexe",
                }
                return

            _update("loading", 10, "Chargement de l'ancien AO et ancienne reponse...")
            anon_old_rfp = await _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RFP)
            anon_old_response = await _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RESPONSE)

        # DB session released — all data is now in memory

        new_rfp_k = len(anon_new_rfp) // 1000
        old_rfp_k = len(anon_old_rfp) // 1000
        old_resp_k = len(anon_old_response) // 1000
        _update("loading", 15,
                f"Documents charges: nouvel AO ({new_rfp_k}K car.), "
                f"ancien AO ({old_rfp_k}K car.), "
                f"ancienne reponse ({old_resp_k}K car.)")

        # ── Phase 2: Gap analysis (streamed, real token progress) ──
        gap_analysis = None
        if anon_old_rfp:
            _update("gap_analysis", 15, "Analyse des ecarts ancien/nouveau AO...")
            gap_cb = _make_stream_progress_callback(
                pid, "gap_analysis", 15, 40, "Analyse des ecarts", max_tokens=12000,
            )
            gap_analysis = await ai_service.analyze_gap(
                anon_old_rfp, anon_new_rfp, on_progress=gap_cb,
            )
            gap_new = len(gap_analysis.get("new_requirements", []))
            gap_mod = len(gap_analysis.get("modified_requirements", []))
            gap_del = len(gap_analysis.get("removed_requirements", []))
            _update("gap_analysis", 40,
                    f"Ecarts identifies: {gap_new} nouvelles, {gap_mod} modifiees, {gap_del} supprimees")

        # ── Phase 3: Check for response documents ──
        # Only generate chapters for "redaction" type documents (text to write)
        # "completion" type documents (Excel/PDF to fill in) are handled separately
        resp_docs = []
        async with async_session() as db:
            result = await db.execute(
                select(ResponseDocument)
                .where(ResponseDocument.project_id == project_id)
                .where(ResponseDocument.is_selected == True)
                .order_by(ResponseDocument.order)
            )
            all_docs = result.scalars().all()
            resp_docs = [
                (str(rd.id), rd.title, rd.description)
                for rd in all_docs
                if rd.content_type == ContentType.REDACTION or rd.content_type == "redaction"
            ]
            completion_docs_count = sum(
                1 for rd in all_docs
                if rd.content_type == ContentType.COMPLETION or rd.content_type == "completion"
            )

        # ── Phase 3: Generate structure ──
        order = 0
        created_count = 0
        delta_stats = {"new": 0, "modified": 0, "unchanged": 0}

        if resp_docs:
            # ── Per-document generation ──
            total_docs = len(resp_docs)
            all_doc_structures: list[tuple[str, list]] = []  # (doc_id, chapters)

            for doc_idx, (doc_id, doc_title, doc_desc) in enumerate(resp_docs):
                doc_num = doc_idx + 1
                start_pct = 40 + int(45 * doc_idx / total_docs)
                end_pct = 40 + int(45 * doc_num / total_docs)

                _update("generating", start_pct,
                        f"Document {doc_num}/{total_docs}: {doc_title}...")

                import time
                t0_doc = time.monotonic()

                async def _doc_progress(token_count: int, char_count: int, _start=start_pct, _end=end_pct, _t0=t0_doc):
                    elapsed = int(time.monotonic() - _t0)
                    ratio = min(token_count / 8000, 0.95)
                    pct = _start + int((_end - _start) * ratio)
                    _generation_progress[pid] = {
                        "status": "running", "step": "generating", "progress": pct,
                        "message": f"Document {doc_num}/{total_docs}: {doc_title} — {token_count} tokens — {elapsed}s",
                    }

                structure = await ai_service.generate_response_structure_for_document(
                    document_title=doc_title,
                    document_description=doc_desc,
                    new_rfp_content=anon_new_rfp,
                    old_rfp_content=anon_old_rfp,
                    old_response_content=anon_old_response,
                    on_progress=_doc_progress,
                )
                if structure:
                    all_doc_structures.append((doc_id, structure))

            if not all_doc_structures:
                _generation_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "L'IA n'a genere aucune structure pour les documents selectionnes.",
                }
                return

            _update("saving", 88, "Enregistrement des chapitres en base...")

            async with async_session() as db:
                for doc_id, structure in all_doc_structures:
                    doc_uuid = uuid.UUID(doc_id)

                    async def create_chapters_recursive(items, parent_id=None, resp_doc_id=None):
                        nonlocal order, created_count
                        for item in items:
                            order += 1
                            created_count += 1
                            raw_type = item.get("chapter_type", "chapter")
                            valid_types = {t.value for t in ChapterType}
                            ch_type = raw_type if raw_type in valid_types else ("sub_chapter" if parent_id else "chapter")
                            chapter = Chapter(
                                project_id=project_id,
                                parent_id=parent_id,
                                response_document_id=resp_doc_id,
                                title=item.get("title", ""),
                                description=item.get("description", ""),
                                order=order,
                                chapter_type=ch_type,
                                rfp_requirement=item.get("rfp_requirement", ""),
                            )
                            db.add(chapter)
                            await db.flush()

                            children = item.get("children", [])
                            if children:
                                await create_chapters_recursive(children, parent_id=chapter.id, resp_doc_id=resp_doc_id)

                    await create_chapters_recursive(structure, resp_doc_id=doc_uuid)

                await db.commit()

        else:
            # ── Legacy: single-document generation ──
            _update("generating", 40, "Generation IA de la structure en cours...")
            gen_cb = _make_stream_progress_callback(
                pid, "generating", 40, 85, "Generation structure", max_tokens=12000,
            )
            structure = await ai_service.generate_response_structure(
                new_rfp_content=anon_new_rfp,
                old_rfp_content=anon_old_rfp,
                old_response_content=anon_old_response,
                gap_analysis=gap_analysis,
                on_progress=gen_cb,
            )

            if not structure:
                _generation_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "L'IA n'a pas retourne de JSON valide apres 2 tentatives. "
                               "Verifiez les logs serveur pour le diagnostic. Reessayez.",
                }
                return

            _update("saving", 88, "Enregistrement des chapitres en base...")

            async with async_session() as db:
                async def create_chapters_recursive(items, parent_id=None):
                    nonlocal order, created_count
                    for item in items:
                        order += 1
                        created_count += 1
                        delta = item.get("delta", "unchanged")
                        if delta in delta_stats:
                            delta_stats[delta] += 1

                        notes = []
                        if delta and delta != "unchanged":
                            notes.append({"type": "delta", "value": delta})

                        raw_type = item.get("chapter_type", "chapter")
                        valid_types = {t.value for t in ChapterType}
                        ch_type = raw_type if raw_type in valid_types else ("sub_chapter" if parent_id else "chapter")

                        chapter = Chapter(
                            project_id=project_id,
                            parent_id=parent_id,
                            title=item.get("title", ""),
                            description=item.get("description", ""),
                            order=order,
                            chapter_type=ch_type,
                            rfp_requirement=item.get("rfp_requirement", ""),
                            notes=notes,
                        )
                        db.add(chapter)
                        await db.flush()

                        children = item.get("children", [])
                        if children:
                            await create_chapters_recursive(children, parent_id=chapter.id)

                await create_chapters_recursive(structure)
                await db.commit()

        _update("generating", 85,
                f"Structure generee: {created_count} chapitres")

        completion_msg = ""
        if completion_docs_count > 0:
            completion_msg = f" — {completion_docs_count} document(s) a completer (Excel/PDF) a traiter dans l'onglet Livrables"

        _generation_progress[pid] = {
            "status": "completed",
            "step": "done",
            "progress": 100,
            "chapters_created": created_count,
            "delta_stats": delta_stats,
            "has_gap_analysis": gap_analysis is not None,
            "completion_docs_count": completion_docs_count,
            "message": f"{created_count} chapitres crees"
                       + (f" pour {len(resp_docs)} document(s) redactionnels" if resp_docs else
                          f" ({delta_stats['new']} nouveaux, {delta_stats['modified']} modifies, {delta_stats['unchanged']} inchanges)")
                       + completion_msg,
        }

    except Exception as e:
        logger.exception("Structure generation failed for project %s", project_id)
        _generation_progress[pid] = {
            "status": "error",
            "step": "error",
            "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


@router.post("/{project_id}/prefill")
async def prefill_chapters(
    project_id: uuid.UUID,
    request: PrefillRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch chapter pre-filling as a background task (returns immediately)."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    pid = str(project_id)

    # Check if already running
    existing = _prefill_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Pre-remplissage deja en cours")

    # Verify old response documents exist
    old_resp_count = (await db.execute(
        select(func.count()).select_from(Document)
        .where(Document.project_id == project_id)
        .where(Document.category == DocumentCategory.OLD_RESPONSE)
    )).scalar() or 0
    if old_resp_count == 0:
        raise HTTPException(status_code=400, detail="Aucun document d'ancienne reponse indexe")

    workspace_id = project.workspace_id
    chapter_ids = request.chapter_ids or []

    _prefill_progress[pid] = {
        "status": "running",
        "step": "starting",
        "progress": 0,
        "message": "Demarrage du pre-remplissage...",
    }

    background_tasks.add_task(_run_prefill, project_id, workspace_id, chapter_ids)

    return {"success": True, "message": "Pre-remplissage lance en arriere-plan"}


@router.get("/{project_id}/prefill-status")
async def get_prefill_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of the chapter pre-filling task."""
    pid = str(project_id)
    return _prefill_progress.get(pid, {
        "status": "idle",
        "step": "idle",
        "progress": 0,
        "message": "",
    })


async def _run_prefill(project_id: uuid.UUID, workspace_id: uuid.UUID, chapter_ids: list[str]):
    """Background task for pre-filling chapters from old response."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _prefill_progress[pid] = {
            "status": "running",
            "step": step,
            "progress": progress,
            "message": message,
        }

    try:
        async with async_session() as db:
            ai_service = await _get_ai_service(workspace_id, db)

            _update("loading", 5, "Chargement des chapitres...")

            # Get chapters to prefill
            query = select(Chapter).where(Chapter.project_id == project_id)
            if chapter_ids:
                chapter_uuids = [uuid.UUID(cid) for cid in chapter_ids]
                query = query.where(Chapter.id.in_(chapter_uuids))
            result = await db.execute(query.order_by(Chapter.order))
            chapters = result.scalars().all()

            # Filter to chapters without content
            to_prefill = [ch for ch in chapters if not ch.content]
            total = len(to_prefill)

            if total == 0:
                _prefill_progress[pid] = {
                    "status": "completed",
                    "step": "done",
                    "progress": 100,
                    "prefilled_count": 0,
                    "message": "Aucun chapitre vide a pre-remplir",
                }
                return

            _update("loading", 10,
                    f"{total} chapitre(s) vide(s) a pre-remplir sur {len(chapters)} total")

            prefilled = 0
            skipped = 0

            for idx, chapter in enumerate(to_prefill):
                chapter_num = idx + 1
                pct = 10 + int(85 * idx / total)
                _update("prefilling", pct,
                        f"Chapitre {chapter_num}/{total}: {chapter.title[:60]}...")

                # Search old response for relevant content
                search_query = f"{chapter.title} {chapter.description}"
                old_response_chunks = VectorService.search(
                    str(project_id), search_query, top_k=5, category_filter="old_response"
                )

                if not old_response_chunks:
                    skipped += 1
                    continue

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

                _update("prefilling", 10 + int(85 * chapter_num / total),
                        f"Chapitre {chapter_num}/{total} termine — {prefilled} pre-rempli(s)")

            _update("saving", 95, "Enregistrement en base...")
            await db.commit()

        _prefill_progress[pid] = {
            "status": "completed",
            "step": "done",
            "progress": 100,
            "prefilled_count": prefilled,
            "message": f"{prefilled} chapitre(s) pre-rempli(s)"
                       + (f" ({skipped} sans contenu pertinent)" if skipped else ""),
        }

    except Exception as e:
        logger.exception("Prefill failed for project %s", project_id)
        _prefill_progress[pid] = {
            "status": "error",
            "step": "error",
            "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


# ── Response Documents (Deliverables) ──

_detect_progress: Dict[str, dict] = {}


@router.post("/{project_id}/detect-deliverables")
async def detect_deliverables(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect expected deliverables from the RFP (background task)."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    doc_count = (await db.execute(
        select(func.count()).select_from(Document)
        .where(Document.project_id == project_id)
        .where(Document.category == DocumentCategory.NEW_RFP)
    )).scalar() or 0
    if doc_count == 0:
        raise HTTPException(status_code=400, detail="Aucun document de nouvel AO indexe")

    pid = str(project_id)
    existing = _detect_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Detection deja en cours")

    _detect_progress[pid] = {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de la detection des livrables...",
    }

    background_tasks.add_task(_run_detect_deliverables, project_id, project.workspace_id)
    return {"success": True, "message": "Detection lancee en arriere-plan"}


@router.get("/{project_id}/detect-deliverables-status")
async def get_detect_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of deliverable detection."""
    pid = str(project_id)
    return _detect_progress.get(pid, {
        "status": "idle", "step": "idle", "progress": 0, "message": "",
    })


async def _run_detect_deliverables(project_id: uuid.UUID, workspace_id: uuid.UUID):
    """Background task: analyze RFP to detect expected deliverables."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _detect_progress[pid] = {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        }

    try:
        async with async_session() as db:
            ai_service = await _get_ai_service(workspace_id, db)

            _update("loading", 10, "Chargement du contenu de l'AO...")
            anon_new_rfp = await _get_all_chunks_anonymized_by_category(
                db, project_id, DocumentCategory.NEW_RFP
            )
            if not anon_new_rfp:
                _detect_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "Aucun document de nouvel AO indexe",
                }
                return

            anon_old_response = await _get_all_chunks_anonymized_by_category(
                db, project_id, DocumentCategory.OLD_RESPONSE
            )

            _update("analyzing", 20, "Analyse IA des livrables attendus...")
            detect_cb = _make_stream_progress_callback(
                pid, "analyzing", 20, 80, "Detection des livrables", max_tokens=8000,
            )
            # Reuse the same progress dict (not _generation_progress) — update reference
            # We need the callback to update _detect_progress, not _generation_progress
            import time
            t0 = time.monotonic()

            async def _on_detect_progress(token_count: int, char_count: int):
                elapsed = int(time.monotonic() - t0)
                ratio = min(token_count / 8000, 0.95)
                pct = 20 + int(60 * ratio)
                _detect_progress[pid] = {
                    "status": "running", "step": "analyzing", "progress": pct,
                    "message": f"Analyse IA — {token_count} tokens ({char_count:,} car.) — {elapsed}s",
                }

            deliverables = await ai_service.detect_deliverables(
                new_rfp_content=anon_new_rfp,
                old_response_content=anon_old_response,
                on_progress=_on_detect_progress,
            )

            if not deliverables:
                _detect_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "L'IA n'a pas detecte de livrables. Reessayez.",
                }
                return

            _update("saving", 85, f"{len(deliverables)} livrable(s) detecte(s), enregistrement...")

            # Remove old response documents (re-detection replaces previous)
            old_docs = await db.execute(
                select(ResponseDocument).where(ResponseDocument.project_id == project_id)
            )
            for old_doc in old_docs.scalars().all():
                await db.delete(old_doc)

            # Create new response documents
            for idx, d in enumerate(deliverables):
                fmt = d.get("expected_format", "docx")
                try:
                    doc_format = DocumentFormat(fmt)
                except ValueError:
                    doc_format = DocumentFormat.OTHER

                # Determine content_type from AI response or infer from format
                raw_content_type = d.get("content_type", "")
                if raw_content_type == "completion":
                    ct = ContentType.COMPLETION
                elif raw_content_type == "redaction":
                    ct = ContentType.REDACTION
                else:
                    # Infer: xlsx is almost always completion, pdf forms too
                    if doc_format == DocumentFormat.XLSX:
                        ct = ContentType.COMPLETION
                    elif doc_format == DocumentFormat.PDF:
                        # PDF could be either; default to completion for forms
                        title_lower = d.get("title", "").lower()
                        form_keywords = ["dc1", "dc2", "dc3", "dc4", "attri", "noti",
                                         "acte d'engagement", "formulaire", "cerfa",
                                         "a completer", "à compléter", "a remplir", "à remplir"]
                        if any(kw in title_lower for kw in form_keywords):
                            ct = ContentType.COMPLETION
                        else:
                            ct = ContentType.REDACTION
                    else:
                        ct = ContentType.REDACTION

                rd = ResponseDocument(
                    project_id=project_id,
                    title=d.get("title", f"Document {idx + 1}"),
                    description=d.get("description", ""),
                    expected_format=doc_format,
                    content_type=ct,
                    is_selected=d.get("suggested", True),
                    order=idx + 1,
                    rfp_source=d.get("rfp_source", ""),
                )
                db.add(rd)

            await db.commit()

        _detect_progress[pid] = {
            "status": "completed", "step": "done", "progress": 100,
            "deliverables_count": len(deliverables),
            "message": f"{len(deliverables)} livrable(s) detecte(s) dans l'AO",
        }

    except Exception as e:
        logger.exception("Deliverable detection failed for project %s", project_id)
        _detect_progress[pid] = {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


@router.get("/{project_id}/response-documents", response_model=list[ResponseDocumentOut])
async def list_response_documents(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all detected response documents for a project."""
    result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.project_id == project_id)
        .order_by(ResponseDocument.order)
    )
    docs = result.scalars().all()

    out = []
    for d in docs:
        ch_count = (await db.execute(
            select(func.count()).select_from(Chapter)
            .where(Chapter.response_document_id == d.id)
        )).scalar() or 0
        out.append(ResponseDocumentOut(
            id=str(d.id),
            project_id=str(d.project_id),
            title=d.title,
            description=d.description,
            expected_format=d.expected_format.value,
            content_type=d.content_type.value if hasattr(d.content_type, 'value') else (d.content_type or "redaction"),
            is_selected=d.is_selected,
            order=d.order,
            rfp_source=d.rfp_source,
            fill_content=d.fill_content or "",
            fill_status=d.fill_status or "pending",
            created_at=d.created_at,
            updated_at=d.updated_at,
            chapter_count=ch_count,
        ))
    return out


@router.put("/{project_id}/response-documents/{doc_id}", response_model=ResponseDocumentOut)
async def update_response_document(
    project_id: uuid.UUID,
    doc_id: uuid.UUID,
    request: ResponseDocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a response document (toggle selection, rename, etc.)."""
    result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.id == doc_id, ResponseDocument.project_id == project_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    for field in ["title", "description", "expected_format", "content_type", "is_selected", "order"]:
        value = getattr(request, field, None)
        if value is not None:
            setattr(doc, field, value)

    await db.commit()
    await db.refresh(doc)

    ch_count = (await db.execute(
        select(func.count()).select_from(Chapter)
        .where(Chapter.response_document_id == doc.id)
    )).scalar() or 0

    return ResponseDocumentOut(
        id=str(doc.id), project_id=str(doc.project_id),
        title=doc.title, description=doc.description,
        expected_format=doc.expected_format.value,
        content_type=doc.content_type.value if hasattr(doc.content_type, 'value') else (doc.content_type or "redaction"),
        is_selected=doc.is_selected, order=doc.order,
        rfp_source=doc.rfp_source,
        fill_content=doc.fill_content or "",
        fill_status=doc.fill_status or "pending",
        created_at=doc.created_at, updated_at=doc.updated_at,
        chapter_count=ch_count,
    )


@router.post("/{project_id}/response-documents/confirm-selection")
async def confirm_document_selection(
    project_id: uuid.UUID,
    request: BulkUpdateSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-update which response documents are selected."""
    for item in request.selections:
        doc_id = uuid.UUID(item["id"])
        result = await db.execute(
            select(ResponseDocument)
            .where(ResponseDocument.id == doc_id, ResponseDocument.project_id == project_id)
        )
        doc = result.scalar_one_or_none()
        if doc:
            doc.is_selected = item.get("is_selected", True)

    await db.commit()
    selected_count = (await db.execute(
        select(func.count()).select_from(ResponseDocument)
        .where(ResponseDocument.project_id == project_id)
        .where(ResponseDocument.is_selected == True)
    )).scalar() or 0

    return {"success": True, "selected_count": selected_count}


# ── Auto-fill completion documents (Excel/PDF) ──

_fill_progress: Dict[str, dict] = {}


@router.post("/{project_id}/fill-deliverables")
async def fill_deliverables(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch auto-fill for completion-type deliverables (background task)."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # Check for completion-type documents
    comp_result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.project_id == project_id)
        .where(ResponseDocument.is_selected == True)
        .where(ResponseDocument.content_type == ContentType.COMPLETION)
    )
    comp_docs = comp_result.scalars().all()
    if not comp_docs:
        raise HTTPException(status_code=400, detail="Aucun document à compléter détecté")

    pid = str(project_id)
    existing = _fill_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Auto-remplissage déjà en cours")

    _fill_progress[pid] = {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Démarrage de l'auto-remplissage...",
    }

    background_tasks.add_task(_run_fill_deliverables, project_id, project.workspace_id)
    return {"success": True, "message": "Auto-remplissage lancé en arrière-plan"}


@router.get("/{project_id}/fill-deliverables-status")
async def get_fill_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of auto-fill for completion documents."""
    pid = str(project_id)
    return _fill_progress.get(pid, {
        "status": "idle", "step": "idle", "progress": 0, "message": "",
    })


async def _run_fill_deliverables(project_id: uuid.UUID, workspace_id: uuid.UUID):
    """Background task: auto-fill completion-type documents (BPU, DQE, forms, etc.)."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _fill_progress[pid] = {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        }

    try:
        async with async_session() as db:
            ai_service = await _get_ai_service(workspace_id, db)

            _update("loading", 5, "Chargement des documents à compléter...")

            # Get completion-type documents
            result = await db.execute(
                select(ResponseDocument)
                .where(ResponseDocument.project_id == project_id)
                .where(ResponseDocument.is_selected == True)
                .where(ResponseDocument.content_type == ContentType.COMPLETION)
                .order_by(ResponseDocument.order)
            )
            comp_docs = result.scalars().all()
            total = len(comp_docs)

            if total == 0:
                _fill_progress[pid] = {
                    "status": "completed", "step": "done", "progress": 100,
                    "filled_count": 0,
                    "message": "Aucun document à compléter",
                }
                return

            _update("loading", 10, f"{total} document(s) à compléter...")

            # Load RFP and old response content
            anon_new_rfp = await _get_all_chunks_anonymized_by_category(
                db, project_id, DocumentCategory.NEW_RFP
            )
            anon_old_response = await _get_all_chunks_anonymized_by_category(
                db, project_id, DocumentCategory.OLD_RESPONSE
            )

            # Also gather any already-generated chapter content for context
            chapters_result = await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .where(Chapter.content != "")
                .order_by(Chapter.order)
            )
            existing_chapters = chapters_result.scalars().all()
            chapter_context = "\n\n".join([
                f"## {ch.title}\n{ch.content[:2000]}"
                for ch in existing_chapters[:10]
            ])

            filled_count = 0

            for idx, doc in enumerate(comp_docs):
                doc_num = idx + 1
                start_pct = 10 + int(85 * idx / total)
                end_pct = 10 + int(85 * doc_num / total)

                _update("filling", start_pct,
                        f"Document {doc_num}/{total}: {doc.title}...")

                doc.fill_status = "generating"

                import time
                t0_doc = time.monotonic()

                async def _on_fill_progress(token_count: int, char_count: int,
                                            _start=start_pct, _end=end_pct,
                                            _t0=t0_doc, _doc_num=doc_num, _title=doc.title):
                    elapsed = int(time.monotonic() - _t0)
                    ratio = min(token_count / 8000, 0.95)
                    pct = _start + int((_end - _start) * ratio)
                    _fill_progress[pid] = {
                        "status": "running", "step": "filling", "progress": pct,
                        "message": f"Document {_doc_num}/{total}: {_title} — {token_count} tokens — {elapsed}s",
                    }

                # Combine old response + chapter context for fuller context
                combined_context = anon_old_response
                if chapter_context:
                    combined_context += "\n\n--- CONTENU DÉJÀ RÉDIGÉ ---\n\n" + chapter_context

                fill_content = await ai_service.generate_fill_content(
                    document_title=doc.title,
                    document_description=doc.description,
                    expected_format=doc.expected_format.value,
                    new_rfp_content=anon_new_rfp,
                    old_response_content=combined_context,
                    on_progress=_on_fill_progress,
                )

                # Deanonymize the fill content
                doc.fill_content = await AnonymizationService.deanonymize_text(
                    fill_content, project_id, db
                )
                doc.fill_status = "completed"
                filled_count += 1

                _update("filling", end_pct,
                        f"Document {doc_num}/{total} terminé — {filled_count} complété(s)")

            _update("saving", 96, "Enregistrement...")
            await db.commit()

        _fill_progress[pid] = {
            "status": "completed", "step": "done", "progress": 100,
            "filled_count": filled_count,
            "message": f"{filled_count} document(s) à compléter traité(s)",
        }

    except Exception as e:
        logger.exception("Fill deliverables failed for project %s", project_id)
        _fill_progress[pid] = {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
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

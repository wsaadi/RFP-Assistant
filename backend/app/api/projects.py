"""RFP Project API routes."""
import io
import os
import uuid
import asyncio
import logging
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..models.user import User
from ..models.workspace import WorkspaceMember
from ..models.project import RFPProject, AIConfig, AnonymizationMapping, ProjectStatus, EntityType, ComplianceResult, GapAnalysisResult
from ..models.document import Document, DocumentChunk, DocumentCategory
from ..models.chapter import Chapter, ChapterType, ChapterStatus
from ..models.response_document import ResponseDocument, DocumentFormat, ContentType
from ..schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut,
    ImprovementAxisRequest, GapAnalysisRequest,
    GenerateStructureRequest, PrefillRequest, ComplianceAnalysisRequest,
)
from ..schemas.document import (
    StatisticsOut, AnonymizationMappingOut, AnonymizationReportOut, AnonymizationEntityGroup,
    AnonymizationMappingCreate, AnonymizationMappingUpdate,
)
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
_gap_analysis_progress: Dict[str, dict] = {}
_compliance_progress: Dict[str, dict] = {}


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

@router.get("/{project_id}/gap-analysis")
async def get_gap_analysis(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest persisted gap analysis for a project."""
    result = await db.execute(
        select(GapAnalysisResult)
        .where(GapAnalysisResult.project_id == project_id)
        .order_by(GapAnalysisResult.created_at.desc())
        .limit(1)
    )
    gr = result.scalar_one_or_none()
    if not gr:
        return {"analysis": None}

    return {
        "analysis": {
            "id": str(gr.id),
            "summary": gr.summary,
            "new_requirements": gr.new_requirements or [],
            "removed_requirements": gr.removed_requirements or [],
            "modified_requirements": gr.modified_requirements or [],
            "unchanged_requirements": gr.unchanged_requirements or [],
            "created_at": gr.created_at.isoformat() if gr.created_at else None,
        }
    }


@router.post("/{project_id}/gap-analysis")
async def analyze_gap(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch gap analysis as a background task (returns immediately)."""
    pid = str(project_id)

    existing = _gap_analysis_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Analyse des ecarts deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    _gap_analysis_progress[pid] = {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de l'analyse des ecarts...",
    }

    background_tasks.add_task(_run_gap_analysis, project_id, project.workspace_id)

    return {"success": True, "message": "Analyse des ecarts lancee en arriere-plan"}


@router.get("/{project_id}/gap-analysis-status")
async def get_gap_analysis_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of gap analysis."""
    pid = str(project_id)
    return _gap_analysis_progress.get(pid, {
        "status": "idle", "step": "idle", "progress": 0, "message": "",
    })


async def _run_gap_analysis(project_id: uuid.UUID, workspace_id: uuid.UUID):
    """Background task for gap analysis."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _gap_analysis_progress[pid] = {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        }

    try:
        async with async_session() as db:
            ai_service = await _get_ai_service(workspace_id, db)

            _update("searching", 10, "Recherche des documents d'appel d'offres...")

            old_rfp_chunks = VectorService.search(str(project_id), "exigences appel d'offres", top_k=20, category_filter="old_rfp")
            new_rfp_chunks = VectorService.search(str(project_id), "exigences appel d'offres", top_k=20, category_filter="new_rfp")

            old_rfp_content = "\n\n".join([c["content"] for c in old_rfp_chunks])
            new_rfp_content = "\n\n".join([c["content"] for c in new_rfp_chunks])

            if not old_rfp_content or not new_rfp_content:
                _gap_analysis_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "Documents d'ancien et/ou de nouvel appel d'offres manquants",
                }
                return

            _update("anonymizing", 20, "Anonymisation des documents...")
            anon_old = await AnonymizationService.anonymize_text(old_rfp_content, project_id, db)
            anon_new = await AnonymizationService.anonymize_text(new_rfp_content, project_id, db)

            _update("analyzing", 40, "Analyse IA des ecarts en cours...")
            analysis = await ai_service.analyze_gap(anon_old, anon_new)

            _update("deanonymizing", 75, "Deanonymisation des resultats...")
            for key in ["summary"]:
                if key in analysis and isinstance(analysis[key], str):
                    analysis[key] = await AnonymizationService.deanonymize_text(analysis[key], project_id, db)
            for req_list_key in ["new_requirements", "removed_requirements", "modified_requirements", "unchanged_requirements"]:
                for req in analysis.get(req_list_key, []):
                    for field in ["title", "description", "old_description", "new_description", "impact"]:
                        if field in req and req[field]:
                            req[field] = await AnonymizationService.deanonymize_text(req[field], project_id, db)

            _update("saving", 90, "Enregistrement des resultats...")
            gr = GapAnalysisResult(
                project_id=project_id,
                summary=analysis.get("summary", ""),
                new_requirements=analysis.get("new_requirements", []),
                removed_requirements=analysis.get("removed_requirements", []),
                modified_requirements=analysis.get("modified_requirements", []),
                unchanged_requirements=analysis.get("unchanged_requirements", []),
            )
            db.add(gr)
            await db.commit()

        _gap_analysis_progress[pid] = {
            "status": "completed", "step": "done", "progress": 100,
            "message": "Analyse des ecarts terminee",
        }

    except Exception as e:
        logger.exception("Gap analysis failed for project %s", project_id)
        _gap_analysis_progress[pid] = {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


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

            _update("loading", 5, "Chargement des documents (AO, ancien AO, ancienne reponse)...")
            # Load all 3 categories in parallel for speed
            anon_new_rfp, anon_old_rfp, anon_old_response = await asyncio.gather(
                _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.NEW_RFP),
                _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RFP),
                _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RESPONSE),
            )
            if not anon_new_rfp:
                _generation_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "Aucun document de nouvel appel d'offres indexe",
                }
                return

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

            # Safety net: skip docs that are clearly completion-type even if
            # content_type was set to REDACTION (e.g. xlsx BPU misclassified)
            _completion_kw = [
                "bpu", "bordereau", "dqe", "dpgf",
                "dc1", "dc2", "dc3", "dc4",
                "attri", "noti", "acte d'engagement",
                "formulaire", "cerfa",
                "a completer", "à compléter",
                "a remplir", "à remplir",
                "grille", "questionnaire",
                "annexe conformit", "annexe rgpd",
            ]

            def _is_truly_redaction(rd) -> bool:
                """Return True only if the document really needs chapter generation."""
                title_lower = (rd.title or "").lower()
                if rd.expected_format == DocumentFormat.XLSX:
                    return False
                if any(kw in title_lower for kw in _completion_kw):
                    return False
                return (
                    rd.content_type == ContentType.REDACTION
                    or rd.content_type in ("redaction", "REDACTION")
                )

            resp_docs = [
                (str(rd.id), rd.title, rd.description)
                for rd in all_docs
                if _is_truly_redaction(rd)
            ]
            completion_docs_count = sum(
                1 for rd in all_docs
                if not _is_truly_redaction(rd)
            )

        # ── Phase 3: Generate structure ──
        order = 0
        created_count = 0
        delta_stats = {"new": 0, "modified": 0, "unchanged": 0}

        # If deliverables were detected but all are completion-type, no chapters to generate
        has_deliverables = (len(resp_docs) + completion_docs_count) > 0
        if has_deliverables and not resp_docs:
            _generation_progress[pid] = {
                "status": "completed",
                "step": "done",
                "progress": 100,
                "chapters_created": 0,
                "delta_stats": delta_stats,
                "has_gap_analysis": gap_analysis is not None,
                "completion_docs_count": completion_docs_count,
                "message": f"Aucun document a rediger detecte — {completion_docs_count} document(s) "
                           f"a completer (Excel/PDF) a traiter dans l'onglet Livrables",
            }
            return

        if resp_docs:
            import time

            # ── Phase 3a: Summarize RFP once (saves re-sending 60K per doc) ──
            total_docs = len(resp_docs)
            rfp_summary = ""
            if total_docs > 1:
                _update("summarizing", 40, "Resume de l'AO pour generation parallele...")
                sum_cb = _make_stream_progress_callback(
                    pid, "summarizing", 40, 50, "Resume AO", max_tokens=6000,
                )
                rfp_summary = await ai_service.summarize_rfp_for_structure(
                    anon_new_rfp, on_progress=sum_cb,
                )
                logger.info("RFP summary: %d chars (vs %d full)", len(rfp_summary), len(anon_new_rfp))

            # ── Phase 3b: Generate structure for all docs IN PARALLEL ──
            all_doc_structures: list[tuple[str, list]] = []
            _doc_done_count = 0

            sem = asyncio.Semaphore(3)  # Limit concurrent Mistral calls

            async def _gen_one_doc(doc_idx, doc_id, doc_title, doc_desc):
                nonlocal _doc_done_count
                t0_doc = time.monotonic()

                async def _doc_progress(token_count: int, char_count: int,
                                        _idx=doc_idx, _title=doc_title, _t0=t0_doc):
                    elapsed = int(time.monotonic() - _t0)
                    ratio = min(token_count / 8000, 0.95)
                    # Progress between 50-88% for parallel generation
                    base = 50 if rfp_summary else 40
                    pct = base + int(38 * (_doc_done_count + ratio) / total_docs)
                    _generation_progress[pid] = {
                        "status": "running", "step": "generating", "progress": pct,
                        "message": f"Documents en parallele ({_doc_done_count + 1}/{total_docs}): "
                                   f"{_title} — {token_count} tokens — {elapsed}s",
                    }

                async with sem:
                    structure = await ai_service.generate_response_structure_for_document(
                        document_title=doc_title,
                        document_description=doc_desc,
                        new_rfp_content=anon_new_rfp,
                        old_rfp_content=anon_old_rfp,
                        old_response_content=anon_old_response,
                        rfp_summary=rfp_summary,
                        on_progress=_doc_progress,
                    )
                    _doc_done_count += 1
                    return (doc_id, structure)

            _update("generating", 50 if rfp_summary else 40,
                    f"Generation parallele de {total_docs} document(s)...")

            results = await asyncio.gather(*[
                _gen_one_doc(idx, doc_id, doc_title, doc_desc)
                for idx, (doc_id, doc_title, doc_desc) in enumerate(resp_docs)
            ])

            all_doc_structures = [(did, struct) for did, struct in results if struct]

            if not all_doc_structures:
                _generation_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "L'IA n'a genere aucune structure pour les documents selectionnes.",
                }
                return

            # ── Phase 3c: Batch insert chapters (single commit) ──
            _update("saving", 88, "Enregistrement des chapitres en base...")

            async with async_session() as db:
                valid_types = {t.value for t in ChapterType}

                def _build_chapters_flat(items, parent_id, resp_doc_id):
                    """Build Chapter objects with pre-assigned UUIDs (no flush needed)."""
                    nonlocal order, created_count
                    chapters = []
                    for item in items:
                        order += 1
                        created_count += 1
                        ch_id = uuid.uuid4()
                        raw_type = item.get("chapter_type", "chapter")
                        ch_type = raw_type if raw_type in valid_types else ("sub_chapter" if parent_id else "chapter")
                        chapters.append(Chapter(
                            id=ch_id,
                            project_id=project_id,
                            parent_id=parent_id,
                            response_document_id=resp_doc_id,
                            title=item.get("title", ""),
                            description=item.get("description", ""),
                            order=order,
                            chapter_type=ch_type,
                            rfp_requirement=item.get("rfp_requirement", ""),
                        ))
                        children = item.get("children", [])
                        if children:
                            chapters.extend(_build_chapters_flat(children, ch_id, resp_doc_id))
                    return chapters

                all_chapters = []
                for doc_id, structure in all_doc_structures:
                    all_chapters.extend(_build_chapters_flat(structure, None, uuid.UUID(doc_id)))

                db.add_all(all_chapters)
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
                valid_types = {t.value for t in ChapterType}

                def _build_legacy_chapters(items, parent_id=None):
                    """Build Chapter objects with pre-assigned UUIDs (batch insert)."""
                    nonlocal order, created_count
                    chapters = []
                    for item in items:
                        order += 1
                        created_count += 1
                        ch_id = uuid.uuid4()
                        delta = item.get("delta", "unchanged")
                        if delta in delta_stats:
                            delta_stats[delta] += 1
                        notes = []
                        if delta and delta != "unchanged":
                            notes.append({"type": "delta", "value": delta})
                        raw_type = item.get("chapter_type", "chapter")
                        ch_type = raw_type if raw_type in valid_types else ("sub_chapter" if parent_id else "chapter")
                        chapters.append(Chapter(
                            id=ch_id,
                            project_id=project_id,
                            parent_id=parent_id,
                            title=item.get("title", ""),
                            description=item.get("description", ""),
                            order=order,
                            chapter_type=ch_type,
                            rfp_requirement=item.get("rfp_requirement", ""),
                            notes=notes,
                        ))
                        children = item.get("children", [])
                        if children:
                            chapters.extend(_build_legacy_chapters(children, parent_id=ch_id))
                    return chapters

                all_chapters = _build_legacy_chapters(structure)
                db.add_all(all_chapters)
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
    """Background task for pre-filling chapters from old response.

    Processes chapters sequentially and saves each one immediately
    so partial results are preserved if something fails.
    """
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str, prefilled_count: int = 0):
        _prefill_progress[pid] = {
            "status": "running",
            "step": step,
            "progress": progress,
            "message": message,
            "prefilled_count": prefilled_count,
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

            # Process chapters sequentially to avoid DB session concurrency issues
            # and save each chapter immediately for incremental persistence
            for idx, chapter in enumerate(to_prefill):
                try:
                    progress = 10 + int(85 * (idx + 1) / total)
                    _update("prefilling", progress,
                            f"Chapitre {idx + 1}/{total}: {chapter.title[:60]}...",
                            prefilled_count=prefilled)

                    # Search old response for relevant content (sync, fast)
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

                    deanon = await AnonymizationService.deanonymize_text(content, project_id, db)
                    refs = [
                        {"document": c["document_name"], "page": c["page_number"], "score": c["score"]}
                        for c in old_response_chunks[:3]
                    ]

                    # Save immediately after each chapter
                    chapter.content = deanon
                    chapter.is_prefilled = True
                    chapter.status = ChapterStatus.IN_PROGRESS
                    chapter.source_references = refs
                    await db.commit()
                    prefilled += 1

                except Exception as ch_err:
                    logger.warning("Prefill failed for chapter %s: %s", chapter.title, str(ch_err)[:200])
                    skipped += 1
                    # Continue with next chapter instead of failing completely
                    continue

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
                title_lower = d.get("title", "").lower()

                # Keywords that ALWAYS indicate a completion document,
                # regardless of what the AI classified
                completion_keywords = [
                    "bpu", "bordereau", "dqe", "dpgf",
                    "dc1", "dc2", "dc3", "dc4",
                    "attri", "noti", "acte d'engagement",
                    "formulaire", "cerfa",
                    "a completer", "à compléter",
                    "a remplir", "à remplir",
                    "cadre de réponse", "cadre de reponse",
                    "grille", "questionnaire",
                    "annexe conformit", "annexe rgpd",
                ]
                is_clearly_completion = (
                    doc_format == DocumentFormat.XLSX
                    or any(kw in title_lower for kw in completion_keywords)
                )

                if is_clearly_completion:
                    # Force COMPLETION for xlsx or docs with completion keywords,
                    # even if AI said "redaction" (common misclassification)
                    ct = ContentType.COMPLETION
                    if raw_content_type == "redaction":
                        logger.warning(
                            "AI classified '%s' (format=%s) as redaction but "
                            "heuristic overrides to COMPLETION",
                            d.get("title"), doc_format,
                        )
                elif raw_content_type == "completion":
                    ct = ContentType.COMPLETION
                elif raw_content_type == "redaction":
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
            content_type=d.content_type.value if hasattr(d.content_type, 'value') else (d.content_type or "REDACTION").lower(),
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
            # Convert string values to proper enums for SQLAlchemy
            if field == "content_type" and isinstance(value, str):
                try:
                    value = ContentType(value)
                except ValueError:
                    value = ContentType.REDACTION
            elif field == "expected_format" and isinstance(value, str):
                try:
                    value = DocumentFormat(value)
                except ValueError:
                    value = DocumentFormat.OTHER
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
        content_type=doc.content_type.value if hasattr(doc.content_type, 'value') else (doc.content_type or "REDACTION").lower(),
        is_selected=doc.is_selected, order=doc.order,
        rfp_source=doc.rfp_source,
        fill_content=doc.fill_content or "",
        fill_status=doc.fill_status or "pending",
        created_at=doc.created_at, updated_at=doc.updated_at,
        chapter_count=ch_count,
    )


@router.post("/{project_id}/response-documents/{doc_id}/reset-fill")
async def reset_fill_content(
    project_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset fill_content and fill_status for a response document so it can be regenerated."""
    result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.id == doc_id, ResponseDocument.project_id == project_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    doc.fill_content = ""
    doc.fill_status = "pending"
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
        content_type=doc.content_type.value if hasattr(doc.content_type, 'value') else (doc.content_type or "REDACTION").lower(),
        is_selected=doc.is_selected, order=doc.order,
        rfp_source=doc.rfp_source,
        fill_content="",
        fill_status="pending",
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

            # Load RFP and old response content in parallel
            anon_new_rfp, anon_old_response = await asyncio.gather(
                _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.NEW_RFP),
                _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RESPONSE),
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

            import time
            filled_count = 0

            # Pre-compute shared context once (instead of per-doc)
            combined_context = anon_old_response
            if chapter_context:
                combined_context += "\n\n--- CONTENU DÉJÀ RÉDIGÉ ---\n\n" + chapter_context

            sem = asyncio.Semaphore(3)
            _fill_done = 0

            async def _fill_one_doc(idx, doc):
                nonlocal _fill_done
                t0_doc = time.monotonic()

                async def _on_fill_progress(token_count: int, char_count: int,
                                            _t0=t0_doc, _title=doc.title):
                    elapsed = int(time.monotonic() - _t0)
                    ratio = min(token_count / 8000, 0.95)
                    pct = 10 + int(85 * (_fill_done + ratio) / total)
                    _fill_progress[pid] = {
                        "status": "running", "step": "filling", "progress": pct,
                        "message": f"Documents en parallele ({_fill_done + 1}/{total}): "
                                   f"{_title} — {token_count} tokens — {elapsed}s",
                    }

                async with sem:
                    fill_content = await ai_service.generate_fill_content(
                        document_title=doc.title,
                        document_description=doc.description,
                        expected_format=doc.expected_format.value,
                        new_rfp_content=anon_new_rfp,
                        old_response_content=combined_context,
                        on_progress=_on_fill_progress,
                    )
                    deanon = await AnonymizationService.deanonymize_text(
                        fill_content, project_id, db
                    )
                    _fill_done += 1
                    return (doc, deanon)

            _update("filling", 10, f"Remplissage parallele de {total} document(s)...")

            results = await asyncio.gather(*[
                _fill_one_doc(idx, doc) for idx, doc in enumerate(comp_docs)
            ])

            for doc, content in results:
                doc.fill_content = content
                doc.fill_status = "completed"
                filled_count += 1

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


@router.get("/{project_id}/compliance-analysis")
async def get_compliance_analysis(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest persisted compliance analysis for a project."""
    result = await db.execute(
        select(ComplianceResult)
        .where(ComplianceResult.project_id == project_id)
        .order_by(ComplianceResult.created_at.desc())
        .limit(1)
    )
    cr = result.scalar_one_or_none()
    if not cr:
        return {"analysis": None}

    return {
        "analysis": {
            "id": str(cr.id),
            "score": cr.score,
            "summary": cr.summary,
            "covered_requirements": cr.covered_requirements or [],
            "missing_elements": cr.missing_elements or [],
            "recommendations": cr.recommendations or [],
            "created_at": cr.created_at.isoformat() if cr.created_at else None,
        }
    }


@router.post("/{project_id}/compliance-analysis")
async def analyze_compliance(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch compliance analysis as a background task (returns immediately)."""
    pid = str(project_id)

    existing = _compliance_progress.get(pid)
    if existing and existing.get("status") == "running":
        raise HTTPException(status_code=409, detail="Analyse de conformite deja en cours")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # Quick pre-checks before launching background task
    chapters_result = await db.execute(
        select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.order)
    )
    chapters = chapters_result.scalars().all()
    response_content = "\n\n".join([
        f"## {c.title}\n{c.content}" for c in chapters if c.content
    ])
    if not response_content.strip():
        raise HTTPException(status_code=400, detail="Aucun contenu de chapitre à analyser. Rédigez d'abord les chapitres.")

    _compliance_progress[pid] = {
        "status": "running", "step": "starting", "progress": 0,
        "message": "Demarrage de l'analyse de conformite...",
    }

    background_tasks.add_task(_run_compliance_analysis, project_id, project.workspace_id)

    return {"success": True, "message": "Analyse de conformite lancee en arriere-plan"}


@router.get("/{project_id}/compliance-analysis-status")
async def get_compliance_analysis_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Poll the progress of compliance analysis."""
    pid = str(project_id)
    return _compliance_progress.get(pid, {
        "status": "idle", "step": "idle", "progress": 0, "message": "",
    })


async def _run_compliance_analysis(project_id: uuid.UUID, workspace_id: uuid.UUID):
    """Background task for compliance analysis."""
    from ..database import async_session
    pid = str(project_id)

    def _update(step: str, progress: int, message: str):
        _compliance_progress[pid] = {
            "status": "running", "step": step,
            "progress": progress, "message": message,
        }

    try:
        async with async_session() as db:
            ai_service = await _get_ai_service(workspace_id, db)

            _update("loading", 10, "Chargement des chapitres...")
            chapters_result = await db.execute(
                select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.order)
            )
            chapters = chapters_result.scalars().all()
            response_content = "\n\n".join([
                f"## {c.title}\n{c.content}" for c in chapters if c.content
            ])

            _update("searching", 15, "Recherche des exigences du cahier des charges...")
            new_rfp_chunks = VectorService.search(str(project_id), "exigences critères évaluation", top_k=25, category_filter="new_rfp")
            rfp_requirements = "\n\n".join([c["content"] for c in new_rfp_chunks])

            if not rfp_requirements:
                _compliance_progress[pid] = {
                    "status": "error", "step": "error", "progress": 0,
                    "message": "Aucun document d'appel d'offres indexe",
                }
                return

            _update("anonymizing", 25, "Anonymisation des contenus...")
            anon_response = await AnonymizationService.anonymize_text(response_content, project_id, db)
            anon_rfp = await AnonymizationService.anonymize_text(rfp_requirements, project_id, db)

            _update("analyzing", 40, "Analyse IA de la conformite en cours...")
            analysis = await ai_service.analyze_compliance(anon_response, anon_rfp)

            _update("deanonymizing", 75, "Deanonymisation des resultats...")
            for req in analysis.get("covered_requirements", []):
                for key in ("requirement", "comment"):
                    if key in req and req[key]:
                        req[key] = await AnonymizationService.deanonymize_text(req[key], project_id, db)
            for elem in analysis.get("missing_elements", []):
                for key in ("requirement", "description"):
                    if key in elem and elem[key]:
                        elem[key] = await AnonymizationService.deanonymize_text(elem[key], project_id, db)
            for i, rec in enumerate(analysis.get("recommendations", [])):
                if rec:
                    analysis["recommendations"][i] = await AnonymizationService.deanonymize_text(rec, project_id, db)
            if analysis.get("summary"):
                analysis["summary"] = await AnonymizationService.deanonymize_text(analysis["summary"], project_id, db)

            _update("saving", 90, "Enregistrement des resultats...")
            cr = ComplianceResult(
                project_id=project_id,
                score=analysis.get("score", 0),
                summary=analysis.get("summary", ""),
                covered_requirements=analysis.get("covered_requirements", []),
                missing_elements=analysis.get("missing_elements", []),
                recommendations=analysis.get("recommendations", []),
            )
            db.add(cr)
            await db.commit()

        _compliance_progress[pid] = {
            "status": "completed", "step": "done", "progress": 100,
            "message": "Analyse de conformite terminee",
        }

    except Exception as e:
        logger.exception("Compliance analysis failed for project %s", project_id)
        _compliance_progress[pid] = {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        }


@router.post("/{project_id}/compliance-analysis/generate-recommendation")
async def generate_recommendation_content(
    project_id: uuid.UUID,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate chapter content addressing a specific compliance recommendation.

    Body: {"recommendation": "the recommendation text", "chapter_id": "optional target chapter id"}
    """
    recommendation = request.get("recommendation", "").strip()
    chapter_id = request.get("chapter_id")

    if not recommendation:
        raise HTTPException(status_code=400, detail="Recommendation manquante")

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    ai_service = await _get_ai_service(project.workspace_id, db)

    # Get RFP context
    rfp_chunks = VectorService.search(
        str(project_id), recommendation, top_k=5, category_filter="new_rfp"
    )
    rfp_context = "\n\n".join([c["content"] for c in rfp_chunks]) if rfp_chunks else ""

    # Anonymize
    anon_rec = await AnonymizationService.anonymize_text(recommendation, project_id, db)
    anon_rfp = await AnonymizationService.anonymize_text(rfp_context, project_id, db) if rfp_context else ""

    system_prompt = """Tu es un expert en réponse aux appels d'offres.
À partir d'une recommandation issue d'une analyse de conformité, génère un contenu structuré
qui répond à cette recommandation et comble la lacune identifiée.

Rédige en français, de manière professionnelle et argumentée. Utilise du markdown
(titres, listes, tableaux si pertinent). Le contenu doit être directement intégrable
dans un mémoire de réponse."""

    user_prompt = f"""RECOMMANDATION À TRAITER:
{anon_rec}

CONTEXTE DU CAHIER DES CHARGES:
{anon_rfp[:5000] if anon_rfp else "(non disponible)"}

Génère un contenu structuré (1-2 pages) qui répond à cette recommandation."""

    try:
        content = await ai_service.generate(system_prompt, user_prompt, max_tokens=4096)
        content = await AnonymizationService.deanonymize_text(content, project_id, db)
    except Exception as e:
        logger.exception("Recommendation content generation failed")
        raise HTTPException(status_code=500, detail=f"Erreur de génération: {str(e)}")

    # If a target chapter is specified, append the content
    if chapter_id:
        ch_result = await db.execute(
            select(Chapter).where(Chapter.id == uuid.UUID(chapter_id)).where(Chapter.project_id == project_id)
        )
        chapter = ch_result.scalar_one_or_none()
        if chapter:
            separator = "\n\n---\n\n" if chapter.content else ""
            chapter.content = (chapter.content or "") + separator + content
            await db.commit()

    return {"content": content}


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

    # Build chapters_by_status breakdown
    by_status: Dict[str, int] = {}
    for c in chapters:
        s = c.status.value if hasattr(c.status, 'value') else str(c.status)
        by_status[s] = by_status.get(s, 0) + 1

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
        chapters_by_status=by_status,
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


# ── Anonymization Mapping CRUD ──────────────────────────────────────

@router.post("/{project_id}/anonymization-mappings", response_model=AnonymizationMappingOut, status_code=201)
async def create_anonymization_mapping(
    project_id: uuid.UUID,
    request: AnonymizationMappingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new anonymization mapping manually."""
    from ..services.anonymization_service import ENTITY_PREFIXES
    from collections import defaultdict

    # Validate entity type
    try:
        entity_type = EntityType(request.entity_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Type d'entité invalide: {request.entity_type}")

    # Check for duplicate original_value
    existing = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.project_id == project_id)
        .where(AnonymizationMapping.original_value == request.original_value)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Cette valeur originale existe déjà dans les mappings")

    # Auto-generate placeholder if not provided
    anonymized_value = request.anonymized_value
    if not anonymized_value:
        # Count existing mappings of this type to generate next placeholder
        count_result = await db.execute(
            select(func.count())
            .where(AnonymizationMapping.project_id == project_id)
            .where(AnonymizationMapping.entity_type == entity_type)
        )
        count = count_result.scalar() or 0
        prefix = ENTITY_PREFIXES.get(entity_type, "ENTITE")
        anonymized_value = f"[{prefix}_{count + 1}]"

    mapping = AnonymizationMapping(
        project_id=project_id,
        entity_type=entity_type,
        original_value=request.original_value,
        anonymized_value=anonymized_value,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    return AnonymizationMappingOut(
        id=str(mapping.id),
        entity_type=mapping.entity_type.value,
        original_value=mapping.original_value,
        anonymized_value=mapping.anonymized_value,
        is_active=mapping.is_active,
    )


@router.put("/{project_id}/anonymization-mappings/{mapping_id}", response_model=AnonymizationMappingOut)
async def update_anonymization_mapping(
    project_id: uuid.UUID,
    mapping_id: uuid.UUID,
    request: AnonymizationMappingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing anonymization mapping."""
    result = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.id == mapping_id)
        .where(AnonymizationMapping.project_id == project_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping non trouvé")

    if request.original_value is not None:
        mapping.original_value = request.original_value
    if request.anonymized_value is not None:
        mapping.anonymized_value = request.anonymized_value
    if request.entity_type is not None:
        try:
            mapping.entity_type = EntityType(request.entity_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Type d'entité invalide: {request.entity_type}")
    if request.is_active is not None:
        mapping.is_active = request.is_active

    await db.commit()
    await db.refresh(mapping)

    return AnonymizationMappingOut(
        id=str(mapping.id),
        entity_type=mapping.entity_type.value,
        original_value=mapping.original_value,
        anonymized_value=mapping.anonymized_value,
        is_active=mapping.is_active,
    )


@router.delete("/{project_id}/anonymization-mappings/{mapping_id}", status_code=204)
async def delete_anonymization_mapping(
    project_id: uuid.UUID,
    mapping_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an anonymization mapping."""
    result = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.id == mapping_id)
        .where(AnonymizationMapping.project_id == project_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping non trouvé")

    await db.delete(mapping)
    await db.commit()


@router.post("/{project_id}/re-anonymize")
async def re_anonymize_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-anonymize all document chunks and chapter content using current active mappings.

    Applies all active mappings (including manually added ones) to existing content.
    """
    # Get all active mappings sorted by length (longest first to avoid partial replacements)
    result = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.project_id == project_id)
        .where(AnonymizationMapping.is_active == True)
    )
    mappings = result.scalars().all()
    mappings_sorted = sorted(mappings, key=lambda m: len(m.original_value), reverse=True)

    if not mappings_sorted:
        return {"updated_chunks": 0, "updated_chapters": 0}

    def apply_mappings(text: str) -> str:
        """Apply all mappings to a text, longest match first."""
        result_text = text
        for m in mappings_sorted:
            result_text = result_text.replace(m.original_value, m.anonymized_value)
        return result_text

    # Re-anonymize document chunks
    chunks_result = await db.execute(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.project_id == project_id)
    )
    chunks = chunks_result.scalars().all()
    updated_chunks = 0
    for chunk in chunks:
        if chunk.content:
            new_anon = apply_mappings(chunk.content)
            if new_anon != chunk.anonymized_content:
                chunk.anonymized_content = new_anon
                updated_chunks += 1

    # Re-anonymize chapter content (store anonymized version)
    chapters_result = await db.execute(
        select(Chapter).where(Chapter.project_id == project_id)
    )
    chapters = chapters_result.scalars().all()
    updated_chapters = 0
    for ch in chapters:
        if ch.content:
            new_anon = apply_mappings(ch.content)
            if new_anon != ch.anonymized_content:
                ch.anonymized_content = new_anon
                updated_chapters += 1

    await db.commit()

    return {"updated_chunks": updated_chunks, "updated_chapters": updated_chapters}


@router.get("/{project_id}/chapters/{chapter_id}/anonymized-content")
async def get_chapter_anonymized_content(
    project_id: uuid.UUID,
    chapter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the anonymized version of a chapter's content (what the AI sees)."""
    result = await db.execute(
        select(Chapter)
        .where(Chapter.id == chapter_id)
        .where(Chapter.project_id == project_id)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapitre non trouvé")

    if not chapter.content:
        return {"anonymized_content": ""}

    # Apply all active mappings to get the anonymized version
    mappings_result = await db.execute(
        select(AnonymizationMapping)
        .where(AnonymizationMapping.project_id == project_id)
        .where(AnonymizationMapping.is_active == True)
    )
    mappings = mappings_result.scalars().all()
    mappings_sorted = sorted(mappings, key=lambda m: len(m.original_value), reverse=True)

    anonymized = chapter.content
    for m in mappings_sorted:
        anonymized = anonymized.replace(m.original_value, m.anonymized_value)

    return {"anonymized_content": anonymized}


# ── Fill Excel endpoint ─────────────────────────────────────────────

def _read_excel_structure(file_path: str) -> str:
    """Read an Excel file and return a textual representation of its structure with cell references.
    Skips fully empty rows and only marks empty cells adjacent to filled cells to reduce noise."""
    from openpyxl import load_workbook
    wb = load_workbook(file_path, data_only=True)
    parts = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        parts.append(f"\n=== Onglet: {sheet_name} ===")
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
            row_cells = []
            has_value = False
            for cell in row:
                coord = cell.coordinate
                val = cell.value
                if val is not None:
                    has_value = True
                    row_cells.append(f"{coord}={val}")
                else:
                    row_cells.append(f"{coord}=(vide)")
            # Only include rows that have at least one non-empty cell
            if has_value:
                parts.append(" | ".join(row_cells))
    wb.close()
    return "\n".join(parts)


def _fill_excel_with_data(file_path: str, fill_data: list) -> bytes:
    """Open an Excel file, fill cells from AI-generated data, return modified bytes."""
    from openpyxl import load_workbook
    import re as _re
    wb = load_workbook(file_path)

    for entry in fill_data:
        sheet_name = entry.get("sheet", "")
        cell_ref = entry.get("cell", "")
        value = entry.get("value")

        if not sheet_name or not cell_ref or value is None:
            continue
        if isinstance(value, str) and value.strip() == "[A COMPLÉTER]":
            continue  # skip placeholder values

        # Find the sheet (try exact match, then case-insensitive)
        ws = None
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            for sn in wb.sheetnames:
                if sn.lower() == sheet_name.lower():
                    ws = wb[sn]
                    break
        if ws is None:
            continue

        # Validate cell reference format
        if not _re.match(r'^[A-Z]{1,3}[0-9]+$', cell_ref.upper()):
            continue

        try:
            ws[cell_ref.upper()] = value
        except Exception:
            continue

    output = io.BytesIO()
    wb.save(output)
    wb.close()
    output.seek(0)
    return output.read()


@router.post("/{project_id}/fill-excel/{doc_id}")
async def fill_excel_document(
    project_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a filled Excel file for a completion-type document (BPU, DQE, conformité, etc.)
    by using data from the old response and the original Excel template from the DCE."""

    # 1. Get the response document
    result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.id == doc_id, ResponseDocument.project_id == project_id)
    )
    resp_doc = result.scalar_one_or_none()
    if not resp_doc:
        raise HTTPException(status_code=404, detail="Document livrable non trouvé")

    # 2. Find the source Excel file in uploaded DCE documents
    # Try matching by rfp_source (filename reference) or by title keywords
    doc_title_lower = (resp_doc.title or "").lower()
    rfp_source_lower = (resp_doc.rfp_source or "").lower()

    # Search for Excel files in the project's new_rfp documents
    docs_result = await db.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .where(Document.category == DocumentCategory.NEW_RFP)
    )
    all_dce_docs = docs_result.scalars().all()

    # Find the best matching Excel file
    excel_doc = None
    for doc in all_dce_docs:
        if doc.file_type.value not in ("xlsx", "xls"):
            continue
        fname_lower = (doc.original_filename or "").lower()
        # Match by rfp_source reference or title similarity
        if rfp_source_lower and rfp_source_lower in fname_lower:
            excel_doc = doc
            break
        if fname_lower and fname_lower in rfp_source_lower:
            excel_doc = doc
            break
        # Fuzzy: check for keywords in both title and filename
        match_keywords = [
            "bpu", "bordereau", "dqe", "dpgf", "prix",
            "rgpd", "conformit", "gdpr", "grille", "questionnaire",
            "annexe", "engagement", "qualit", "sécurit", "securit",
            "environnement", "rse", "social", "audit",
        ]
        for kw in match_keywords:
            if kw in doc_title_lower and kw in fname_lower:
                excel_doc = doc
                break
        if excel_doc:
            break

    # Fallback 1: match by title words (at least 2 words matching)
    if not excel_doc:
        title_words = [w for w in doc_title_lower.split() if len(w) > 3]
        best_match = None
        best_score = 0
        for doc in all_dce_docs:
            if doc.file_type.value not in ("xlsx", "xls"):
                continue
            fname_lower = (doc.original_filename or "").lower()
            score = sum(1 for w in title_words if w in fname_lower)
            if score >= 2 and score > best_score:
                best_match = doc
                best_score = score
        if best_match:
            excel_doc = best_match

    # Fallback 2: just pick the first Excel file
    if not excel_doc:
        for doc in all_dce_docs:
            if doc.file_type.value in ("xlsx", "xls"):
                excel_doc = doc
                break

    if not excel_doc or not os.path.isfile(excel_doc.file_path):
        raise HTTPException(
            status_code=404,
            detail="Aucun fichier Excel source trouvé dans le DCE. "
                   "Assurez-vous d'avoir uploadé le BPU Excel dans les documents du nouvel AO.",
        )

    # 3. Read Excel structure
    excel_structure = _read_excel_structure(excel_doc.file_path)

    # 4. Get project for workspace_id
    proj_result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # 5. Load context: new RFP + old response (with pricing)
    anon_new_rfp, anon_old_response = await asyncio.gather(
        _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.NEW_RFP),
        _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RESPONSE),
    )

    # Targeted vector search - adapt query based on document type
    doc_title_for_search = resp_doc.title or ""
    title_lower_for_search = doc_title_for_search.lower()
    conformity_keywords = ["rgpd", "conformit", "gdpr", "protection des données",
                           "questionnaire", "grille", "annexe", "déclaration",
                           "engagement", "certification", "audit", "sécurité",
                           "environnement", "rse", "social", "qualité"]
    is_conformity_doc = any(kw in title_lower_for_search for kw in conformity_keywords)

    if is_conformity_doc:
        search_query = (
            f"{doc_title_for_search} conformité RGPD protection données personnelles "
            "politique sécurité mesures techniques organisationnelles DPO registre "
            "sous-traitant transfert consentement droits personnes concernées"
        )
    else:
        search_query = (
            f"prix unitaire tarif {doc_title_for_search} BPU bordereau montant "
            "coût forfait taux journalier"
        )

    relevant_chunks = VectorService.search(
        str(project_id),
        search_query,
        top_k=20,
        category_filter="old_response",
    )
    relevant_context = "\n\n".join([
        f"[{c['document_name']} p.{c['page_number']}] {c['content']}"
        for c in relevant_chunks
    ])

    old_response_with_context = anon_old_response
    if relevant_context:
        label = "EXTRAITS PERTINENTS" if is_conformity_doc else "EXTRAITS PERTINENTS SUR LES PRIX"
        old_response_with_context = (
            f"=== {label} ===\n{relevant_context}\n\n"
            f"=== CONTENU COMPLET ANCIENNE RÉPONSE ===\n{anon_old_response}"
        )

    # 6. Call AI to generate structured fill data
    logger.info(
        "fill-excel %s: excel_structure=%d chars, old_response=%d chars, relevant_chunks=%d, new_rfp=%d chars",
        resp_doc.title, len(excel_structure), len(old_response_with_context),
        len(relevant_chunks), len(anon_new_rfp),
    )
    ai_service = await _get_ai_service(project.workspace_id, db)
    fill_data = await ai_service.generate_excel_fill_data(
        document_title=resp_doc.title,
        excel_structure=excel_structure,
        new_rfp_content=anon_new_rfp,
        old_response_content=old_response_with_context,
    )
    logger.info("fill-excel %s: AI returned %d cell entries", resp_doc.title, len(fill_data))

    # 7. Fill the Excel and return as download
    filled_bytes = _fill_excel_with_data(excel_doc.file_path, fill_data)

    # Generate output filename
    base_name = os.path.splitext(excel_doc.original_filename)[0]
    output_filename = f"{base_name}_rempli.xlsx"

    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{output_filename}"'},
    )


# ── Fill PDF endpoint ──────────────────────────────────────────────

def _extract_pdf_zones(file_path: str) -> dict:
    """Extract PDF layout and identify fillable zones with real coordinates.

    Returns a dict with:
      - "has_form_fields": bool
      - "form_fields": list of form field dicts (for form PDFs)
      - "zones": list of fillable zone dicts (for non-form PDFs)
      - "text_for_ai": formatted text describing zones for AI consumption
    """
    import fitz
    import re
    doc = fitz.open(file_path)
    result = {"has_form_fields": False, "form_fields": [], "zones": [], "text_for_ai": ""}

    # ── 1. Check for interactive form fields ──
    for page_num in range(len(doc)):
        page = doc[page_num]
        for w in page.widgets() or []:
            result["has_form_fields"] = True
            result["form_fields"].append({
                "page": page_num + 1,
                "field_name": w.field_name or "",
                "field_type": w.field_type_string or "",
                "field_value": w.field_value or "",
            })

    if result["has_form_fields"]:
        # For form PDFs, we just list the fields for the AI
        parts = ["=== CHAMPS DE FORMULAIRE PDF ==="]
        for f in result["form_fields"]:
            parts.append(
                f"  Page {f['page']}: Champ '{f['field_name']}' "
                f"(type={f['field_type']}, valeur actuelle='{f['field_value']}')"
            )
        # Also add text context per page
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                parts.append(f"\n=== TEXTE PAGE {page_num + 1} ===")
                parts.append(text[:5000])
        result["text_for_ai"] = "\n".join(parts)
        doc.close()
        return result

    # ── 2. For non-form PDFs: extract layout with zone detection ──
    # Pattern matching for filler characters (dots, underscores, etc.)
    _FILLER_RE = re.compile(r'[.…_]{3,}|(\.\s){3,}')

    zones = []
    ai_parts = []
    zone_id = 0

    # Track page-level right margin (the farthest content boundary)
    page_margins = {}

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        text_dict = page.get_text("dict")
        page_zones = []

        # First pass: compute the effective right margin for the page
        max_right = 0
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if txt and not _FILLER_RE.fullmatch(txt):
                        max_right = max(max_right, span["bbox"][2])
        # Use page width minus a small margin as fallback
        effective_right = min(page_width - 20, max(max_right + 30, page_width * 0.85))
        page_margins[page_num] = effective_right

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # text blocks only
                continue

            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue

                line_text = "".join(s["text"] for s in spans).strip()
                if not line_text:
                    continue

                line_bbox = line["bbox"]  # [x0, y0, x1, y1]
                first_span = spans[0]
                last_span = spans[-1]
                last_span_bbox = last_span["bbox"]
                first_span_bbox = first_span["bbox"]
                font_size = last_span.get("size", 10)

                # Compute the line height (distance from top to bottom of the line)
                line_height = line_bbox[3] - line_bbox[1]

                # ── Zone type B: line with dots/underscores (fill-in line) ──
                # Check this FIRST because these lines might also end with ":"
                has_filler = bool(_FILLER_RE.search(line_text))

                if has_filler:
                    # Find where the filler starts to position text AFTER the label part
                    # Walk through spans to find the first span containing filler chars
                    label_end_x = first_span_bbox[0]
                    fill_start_x = first_span_bbox[0]
                    filler_found = False
                    label_text = ""

                    for s in spans:
                        s_text = s.get("text", "")
                        if _FILLER_RE.search(s_text) and not filler_found:
                            filler_found = True
                            # Check if span has label text before the filler
                            match = _FILLER_RE.search(s_text)
                            if match and match.start() > 0:
                                # There's label text before the filler in this span
                                label_prefix = s_text[:match.start()].rstrip()
                                if label_prefix:
                                    label_text += label_prefix
                                    # Estimate X position where filler starts
                                    span_width = s["bbox"][2] - s["bbox"][0]
                                    char_width = span_width / max(len(s_text), 1)
                                    fill_start_x = s["bbox"][0] + len(label_prefix) * char_width
                                else:
                                    fill_start_x = s["bbox"][0]
                            else:
                                fill_start_x = s["bbox"][0]
                        elif not filler_found:
                            label_text += s_text
                            label_end_x = s["bbox"][2]

                    # If no label found before filler, use the line start
                    if not label_text.strip():
                        fill_start_x = first_span_bbox[0]
                    else:
                        # Position fill right after the label text
                        fill_start_x = max(fill_start_x, label_end_x + 2)

                    fill_end_x = last_span_bbox[2]

                    # Build a clean label for the AI (strip filler chars)
                    clean_label = _FILLER_RE.sub("", line_text).strip()
                    if clean_label.endswith(":"):
                        clean_label = clean_label[:-1].strip()

                    z = {
                        "id": f"z{zone_id}",
                        "page": page_num + 1,
                        "type": "fill_line",
                        "label": clean_label[:100] if clean_label else line_text[:100],
                        "x": fill_start_x,
                        "y": line_bbox[1],  # top of line (we'll compute baseline at fill time)
                        "y_bottom": line_bbox[3],
                        "max_width": fill_end_x - fill_start_x,
                        "line_height": line_height,
                        "font_size": min(font_size, 9),
                        # Store the full line bbox for clearing
                        "clear_rect": [fill_start_x - 1, line_bbox[1], fill_end_x + 1, line_bbox[3]],
                    }
                    zones.append(z)
                    page_zones.append(z)
                    zone_id += 1

                # ── Zone type A: label ending with ":" with space after ──
                elif line_text.rstrip().endswith(":"):
                    space_after = effective_right - last_span_bbox[2]
                    if space_after > 40:  # enough room to fill after the colon
                        z = {
                            "id": f"z{zone_id}",
                            "page": page_num + 1,
                            "type": "after_label",
                            "label": line_text.rstrip(": ").strip(),
                            "x": last_span_bbox[2] + 4,
                            "y": line_bbox[1],
                            "y_bottom": line_bbox[3],
                            "max_width": space_after - 10,
                            "line_height": line_height,
                            "font_size": min(font_size, 9),
                            "clear_rect": None,  # nothing to clear for after-label
                        }
                        zones.append(z)
                        page_zones.append(z)
                        zone_id += 1

                # ── Zone type C: line ending with empty space (> 50% of page) ──
                elif last_span_bbox[2] < page_width * 0.5 and len(line_text) < 40:
                    # Short label with lots of space → likely a field
                    space_after = effective_right - last_span_bbox[2]
                    if space_after > 150:
                        z = {
                            "id": f"z{zone_id}",
                            "page": page_num + 1,
                            "type": "after_short_label",
                            "label": line_text,
                            "x": last_span_bbox[2] + 8,
                            "y": line_bbox[1],
                            "y_bottom": line_bbox[3],
                            "max_width": space_after - 15,
                            "line_height": line_height,
                            "font_size": min(font_size, 9),
                            "clear_rect": None,
                        }
                        zones.append(z)
                        page_zones.append(z)
                        zone_id += 1

        # Build AI-friendly text for this page
        if page_zones:
            ai_parts.append(f"\n=== PAGE {page_num + 1} — ZONES REMPLISSABLES ===")
            # Also include full page text for context
            page_text = page.get_text("text")
            if page_text.strip():
                ai_parts.append(f"[Contenu de la page pour contexte:]\n{page_text[:3000]}")
            ai_parts.append("")
            for z in page_zones:
                ai_parts.append(f'  {z["id"]}: ({z["type"]}) Label: "{z["label"]}"')
        else:
            # Include page text even without zones for context
            page_text = page.get_text("text")
            if page_text.strip():
                ai_parts.append(f"\n=== PAGE {page_num + 1} (pas de zones détectées) ===")
                ai_parts.append(page_text[:3000])

    result["zones"] = zones
    result["text_for_ai"] = "\n".join(ai_parts)
    doc.close()
    return result


def _fill_pdf_with_zones(file_path: str, fill_data: list, zone_map: dict) -> bytes:
    """Fill a PDF using pre-computed zone coordinates.

    fill_data: [{"zone_id": "z0", "value": "text"}, ...] or [{"field": ..., "value": ...}, ...]
    zone_map: dict mapping zone_id → zone dict with x, y, page, font_size, max_width, clear_rect
    """
    import fitz
    doc = fitz.open(file_path)

    # ── Handle form field fills ──
    field_fills = [e for e in fill_data if e.get("field")]
    if field_fills:
        for page_num in range(len(doc)):
            page = doc[page_num]
            for widget in page.widgets() or []:
                field_name = widget.field_name or ""
                for entry in field_fills:
                    if entry["field"].strip().lower() == field_name.strip().lower():
                        value = entry.get("value")
                        if value is not None and str(value).strip() != "[A COMPLÉTER]":
                            widget.field_value = str(value)
                            widget.update()
                        break

    # ── Handle zone-based fills ──
    zone_fills = [e for e in fill_data if e.get("zone_id")]

    # Step 1: Collect all clear_rect areas per page, then apply redactions to erase
    # dots/underscores before writing new text
    page_rects: Dict[int, list] = {}
    zone_fill_entries = []
    for entry in zone_fills:
        zone_id = entry.get("zone_id", "")
        value = str(entry.get("value", "")).strip()

        if not value or value == "[A COMPLÉTER]":
            continue
        if zone_id not in zone_map:
            logger.warning("fill-pdf: zone_id '%s' not found in zone_map, skipping", zone_id)
            continue

        zone = zone_map[zone_id]
        page_idx = int(zone["page"]) - 1
        if page_idx < 0 or page_idx >= len(doc):
            continue

        zone_fill_entries.append((zone_id, value, zone, page_idx))

        # Collect clear rectangles
        clear_rect = zone.get("clear_rect")
        if clear_rect:
            page_rects.setdefault(page_idx, []).append(clear_rect)

    # Apply redaction annotations to erase filler content (dots, underscores)
    for page_idx, rects in page_rects.items():
        page = doc[page_idx]
        for rect_coords in rects:
            rect = fitz.Rect(rect_coords)
            # Add a redaction annotation that will white-out the area
            page.add_redact_annot(rect, fill=(1, 1, 1))  # white fill
        page.apply_redactions()  # apply all redactions for this page at once

    # Step 2: Insert the fill text in the cleared areas
    filled_count = 0
    for zone_id, value, zone, page_idx in zone_fill_entries:
        page = doc[page_idx]
        x = float(zone["x"])
        y_top = float(zone["y"])
        y_bottom = float(zone.get("y_bottom", y_top + 12))
        font_size = float(zone.get("font_size", 9))
        max_width = float(zone.get("max_width", 300))
        line_height = float(zone.get("line_height", y_bottom - y_top))

        # Ensure font_size fits within the line height (leave 1pt padding)
        if font_size > line_height - 1:
            font_size = max(line_height - 1, 5)

        # Compute baseline: position text so it sits within the line box
        # PyMuPDF insert_text uses the baseline as the y coordinate.
        # baseline ≈ top of line + ascent ≈ top + font_size * 0.85
        baseline_y = y_top + font_size * 0.85
        # Make sure baseline doesn't go below the line bottom
        if baseline_y > y_bottom - 1:
            baseline_y = y_bottom - 1

        # Calculate how many characters fit on one line
        # Use a more accurate estimate: average char width ≈ font_size * 0.52
        char_width_est = font_size * 0.52
        max_chars = int(max_width / char_width_est) if char_width_est > 0 else 50

        # Truncate value to fit
        if len(value) > max_chars:
            value = value[:max(max_chars - 1, 1)] + "…"

        point = fitz.Point(x, baseline_y)
        try:
            page.insert_text(
                point,
                value,
                fontname="helv",  # Helvetica — clean sans-serif
                fontsize=font_size,
                color=(0.05, 0.05, 0.35),  # Dark blue to distinguish filled text
            )
            filled_count += 1
        except Exception as exc:
            logger.warning("fill-pdf: failed to insert text at zone '%s': %s", zone_id, exc)

    logger.info("fill-pdf: filled %d zones out of %d entries", filled_count, len(zone_fills))
    output = doc.tobytes()
    doc.close()
    return output


@router.post("/{project_id}/fill-pdf/{doc_id}")
async def fill_pdf_document(
    project_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a filled PDF file for a completion-type document
    by using data from the old response and the original PDF template from the DCE."""

    # 1. Get the response document
    result = await db.execute(
        select(ResponseDocument)
        .where(ResponseDocument.id == doc_id, ResponseDocument.project_id == project_id)
    )
    resp_doc = result.scalar_one_or_none()
    if not resp_doc:
        raise HTTPException(status_code=404, detail="Document livrable non trouvé")

    # 2. Find the source PDF file in uploaded DCE documents
    doc_title_lower = (resp_doc.title or "").lower()
    rfp_source_lower = (resp_doc.rfp_source or "").lower()

    docs_result = await db.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .where(Document.category == DocumentCategory.NEW_RFP)
    )
    all_dce_docs = docs_result.scalars().all()

    # Find the best matching PDF file
    all_pdfs = [doc for doc in all_dce_docs if doc.file_type.value == "pdf"]
    logger.info(
        "fill-pdf: looking for PDF source for '%s' (rfp_source='%s'), %d PDFs in DCE: %s",
        resp_doc.title, resp_doc.rfp_source, len(all_pdfs),
        [d.original_filename for d in all_pdfs],
    )

    pdf_doc = None
    # Strategy 1: Match by rfp_source reference
    for doc in all_pdfs:
        fname_lower = (doc.original_filename or "").lower()
        if rfp_source_lower and rfp_source_lower in fname_lower:
            pdf_doc = doc
            break
        if fname_lower and fname_lower in rfp_source_lower:
            pdf_doc = doc
            break

    # Strategy 2: Match by title keywords (at least 2 matching words)
    if not pdf_doc:
        title_words = [w for w in doc_title_lower.split() if len(w) > 3]
        best_score, best_doc = 0, None
        for doc in all_pdfs:
            fname_lower = (doc.original_filename or "").lower()
            matches = sum(1 for w in title_words if w in fname_lower)
            if matches > best_score:
                best_score = matches
                best_doc = doc
        if best_score >= 2:
            pdf_doc = best_doc

    # Strategy 3: Match by common admin/form keywords
    if not pdf_doc:
        for doc in all_pdfs:
            fname_lower = (doc.original_filename or "").lower()
            for kw in ["formulaire", "acte", "dc1", "dc2", "dc3", "dc4", "attrib", "engagement",
                        "candidature", "marche", "contrat", "annexe"]:
                if kw in doc_title_lower and kw in fname_lower:
                    pdf_doc = doc
                    break
            if pdf_doc:
                break

    # Strategy 4: Match any word from title in filename
    if not pdf_doc:
        for doc in all_pdfs:
            fname_lower = (doc.original_filename or "").lower()
            for w in doc_title_lower.split():
                if len(w) > 4 and w in fname_lower:
                    pdf_doc = doc
                    break
            if pdf_doc:
                break

    # Last fallback: pick the first available PDF
    if not pdf_doc and all_pdfs:
        pdf_doc = all_pdfs[0]
        logger.info("fill-pdf: no keyword match, falling back to first PDF: %s", pdf_doc.original_filename)

    if not pdf_doc or not os.path.isfile(pdf_doc.file_path):
        raise HTTPException(
            status_code=404,
            detail="Aucun fichier PDF source trouvé dans le DCE. "
                   "Assurez-vous d'avoir uploadé le PDF correspondant dans les documents du nouvel AO.",
        )
    logger.info("fill-pdf: matched PDF source '%s' for deliverable '%s'", pdf_doc.original_filename, resp_doc.title)

    # 3. Extract PDF zones (layout analysis with real coordinates)
    pdf_zones = _extract_pdf_zones(pdf_doc.file_path)
    logger.info(
        "fill-pdf '%s': has_form_fields=%s, detected %d zones, text_for_ai=%d chars",
        resp_doc.title, pdf_zones["has_form_fields"],
        len(pdf_zones["zones"]), len(pdf_zones["text_for_ai"]),
    )

    # 4. Get project for workspace_id
    proj_result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # 5. Load context: new RFP + old response
    anon_new_rfp, anon_old_response = await asyncio.gather(
        _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.NEW_RFP),
        _get_all_chunks_anonymized_by_category(db, project_id, DocumentCategory.OLD_RESPONSE),
    )

    # Targeted vector search for relevant content
    search_query = f"{resp_doc.title} formulaire informations candidat société entreprise"
    relevant_chunks = VectorService.search(
        str(project_id),
        search_query,
        top_k=15,
        category_filter="old_response",
    )
    relevant_context = "\n\n".join([
        f"[{c['document_name']} p.{c['page_number']}] {c['content']}"
        for c in relevant_chunks
    ])

    old_response_with_context = anon_old_response
    if relevant_context:
        old_response_with_context = (
            f"=== EXTRAITS PERTINENTS DE L'ANCIENNE RÉPONSE ===\n{relevant_context}\n\n"
            f"=== CONTENU COMPLET ANCIENNE RÉPONSE ===\n{anon_old_response}"
        )

    # 6. Call AI to generate structured fill data
    logger.info(
        "fill-pdf %s: old_response=%d chars, relevant_chunks=%d, new_rfp=%d chars",
        resp_doc.title, len(old_response_with_context),
        len(relevant_chunks), len(anon_new_rfp),
    )
    ai_service = await _get_ai_service(project.workspace_id, db)
    fill_data = await ai_service.generate_pdf_fill_data(
        document_title=resp_doc.title,
        pdf_structure=pdf_zones["text_for_ai"],
        new_rfp_content=anon_new_rfp,
        old_response_content=old_response_with_context,
        has_form_fields=pdf_zones["has_form_fields"],
    )
    logger.info("fill-pdf %s: AI returned %d fill entries", resp_doc.title, len(fill_data))

    # 7. Fill the PDF and return as download
    zone_map = {z["id"]: z for z in pdf_zones["zones"]}
    filled_bytes = _fill_pdf_with_zones(pdf_doc.file_path, fill_data, zone_map)

    base_name = os.path.splitext(pdf_doc.original_filename)[0]
    output_filename = f"{base_name}_rempli.pdf"

    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_filename}"'},
    )

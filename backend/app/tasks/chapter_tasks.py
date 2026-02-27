"""Celery tasks for chapter content generation."""
import asyncio
import logging
import uuid

from ..celery_app import celery
from ..services.progress_service import set_progress, get_progress

logger = logging.getLogger(__name__)

# Namespace for chapter generation progress in Redis
NS = "chapter_gen"


def _update_chapter(cid: str, status: str, step: str, progress: int, message: str, **extra):
    data = {"status": status, "step": step, "progress": progress, "message": message}
    data.update(extra)
    set_progress(NS, cid, data)


@celery.task(name="tasks.generate_chapter_content", bind=True, max_retries=1)
def generate_chapter_content_task(
    self,
    chapter_id: str,
    project_id: str,
    workspace_id: str,
    action: str,
    custom_prompt: str,
    use_old_response: bool,
    include_improvement_axes: bool,
):
    """Celery wrapper for chapter content generation."""
    asyncio.run(_run_chapter_generation(
        uuid.UUID(chapter_id),
        uuid.UUID(project_id),
        uuid.UUID(workspace_id),
        action,
        custom_prompt,
        use_old_response,
        include_improvement_axes,
    ))


async def _run_chapter_generation(
    chapter_id: uuid.UUID, project_id: uuid.UUID, workspace_id: uuid.UUID,
    action: str, custom_prompt: str, use_old_response: bool, include_improvement_axes: bool,
):
    """Background task for chapter content generation.

    Uses a task-scoped engine to avoid stale asyncpg connections across
    ``asyncio.run()`` invocations in Celery workers.
    """
    from sqlalchemy import select
    from ..database import create_task_engine
    from ..models.project import RFPProject, AIConfig
    from ..models.chapter import Chapter, ChapterStatus
    from ..models.document import Document, DocumentChunk, DocumentCategory, ProcessingStatus
    from ..services.ai_service import MistralAIService
    from ..services.vector_service import VectorService
    from ..services.anonymization_service import AnonymizationService

    cid = str(chapter_id)

    def _update(step: str, progress: int, message: str):
        _update_chapter(cid, "running", step, progress, message)

    task_engine, TaskSession = create_task_engine()

    try:
        _update("starting", 0, "Demarrage de la generation...")

        # ── Phase 1: Read data + anonymize (short DB session) ──
        async with TaskSession() as db:
            config_result = await db.execute(
                select(AIConfig).where(AIConfig.workspace_id == workspace_id)
            )
            config = config_result.scalar_one_or_none()
            ai_service = MistralAIService.from_config(config, config.mistral_api_key_encrypted)

            result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
            chapter = result.scalar_one()
            project_result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
            project = project_result.scalar_one()

            ch_title = chapter.title
            ch_description = chapter.description
            ch_rfp_requirement = chapter.rfp_requirement
            ch_content = chapter.content or ""
            ch_notes = chapter.notes or []
            proj_improvement = project.improvement_axes if include_improvement_axes else ""
            proj_ai_context = project.ai_context or ""
            proj_context_mode = project.context_mode or "rag"

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
                old_response_content = ""
                context_chunks_text = ""

                if proj_context_mode == "full":
                    _update("loading", 10, "Chargement du contexte complet...")
                    old_response_content = await _get_full_text_anon(db, project_id, DocumentCategory.OLD_RESPONSE) if use_old_response else ""
                    context_chunks_text = await _get_full_text_anon(db, project_id, DocumentCategory.NEW_RFP)
                else:
                    _update("searching", 10, "Recherche de contenu pertinent...")
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
                    if search_results:
                        raw_old = "\n\n".join([r["content"] for r in search_results])
                        old_response_content = await AnonymizationService.anonymize_text(raw_old, project_id, db)

                _update("anonymizing", 25, "Preparation...")
                notes_text = "\n".join([n.get("content", "") for n in ch_notes])
                ai_params = {
                    "mode": "generate",
                    "old_response_content": old_response_content,
                    "context_chunks_text": context_chunks_text,
                    "notes_text": notes_text,
                }

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

        # ── Phase 3: Deanonymize + save ──
        _update("deanonymizing", 80, "Deanonymisation...")
        async with TaskSession() as db:
            final_content = await AnonymizationService.deanonymize_text(result_text, project_id, db)

            _update("saving", 90, "Enregistrement...")
            chap_result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
            chap = chap_result.scalar_one()
            chap.content = final_content
            chap.status = ChapterStatus.IN_PROGRESS
            await db.commit()

        set_progress(NS, cid, {
            "status": "completed", "step": "done", "progress": 100,
            "message": "Contenu genere avec succes",
        })

    except Exception as e:
        logger.exception("Chapter generation failed for chapter %s", chapter_id)
        set_progress(NS, cid, {
            "status": "error", "step": "error", "progress": 0,
            "message": f"Erreur: {str(e)[:200]}",
        })
    finally:
        await task_engine.dispose()


async def _get_full_text_anon(db, project_id, category):
    """Get full anonymized text for all documents of a category."""
    from sqlalchemy import select
    from ..models.document import Document, DocumentChunk, ProcessingStatus

    result = await db.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .where(Document.category == category)
        .where(Document.processing_status == ProcessingStatus.COMPLETED)
        .order_by(Document.original_filename)
    )
    docs = result.scalars().all()
    parts = []
    fallback_doc_ids = []
    for doc in docs:
        anon = (doc.anonymized_full_text or "").strip()
        if anon:
            parts.append(f"\n\n=== DOCUMENT: {doc.original_filename} ===\n")
            parts.append(anon)
        else:
            fallback_doc_ids.append(doc.id)

    if fallback_doc_ids:
        chunk_result = await db.execute(
            select(DocumentChunk, Document.original_filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(fallback_doc_ids))
            .order_by(Document.original_filename, DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        current_doc = None
        for chunk, doc_name in chunk_result.all():
            text = (chunk.anonymized_content or chunk.content or "").strip()
            if not text:
                continue
            if doc_name != current_doc:
                current_doc = doc_name
                parts.append(f"\n\n=== DOCUMENT: {doc_name} ===\n")
            parts.append(text)

    return "\n\n".join(parts)

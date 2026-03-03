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
    from ..models.document import Document, DocumentChunk, DocumentImage, DocumentCategory, ProcessingStatus
    from ..services.ai_service import MistralAIService, create_ai_service
    from ..services.vector_service import VectorService
    from ..services.anonymization_service import AnonymizationService
    from ..services.image_providers import ner_config_from_ai_config

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
            ai_service = create_ai_service(config)

            # Configure NER provider from workspace settings
            if config:
                AnonymizationService.configure_ner(ner_config_from_ai_config(config))

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
            proj_company_name = getattr(project, 'company_name', '') or ''
            proj_client_name = project.client_name or ''

            # ── Anonymize ALL metadata fields before sending to Mistral ──
            # These fields (title, description, requirement, notes, improvement
            # axes, AI context) were previously sent in clear text, leaking
            # company names, client names, etc. to the external AI.
            _update("anonymizing", 10, "Anonymisation des metadonnees...")
            _anon = AnonymizationService.apply_existing_mappings
            anon_title = await _anon(ch_title, project_id, db)
            anon_description = await _anon(ch_description, project_id, db)
            anon_rfp_requirement = await _anon(ch_rfp_requirement, project_id, db)
            anon_improvement = await _anon(proj_improvement, project_id, db) if proj_improvement else ""
            anon_ai_context = await _anon(proj_ai_context, project_id, db) if proj_ai_context else ""

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
                inspiration_content = ""

                if proj_context_mode == "full":
                    _update("loading", 10, "Chargement du contexte complet...")
                    old_response_content = await _get_full_text_anon(db, project_id, DocumentCategory.OLD_RESPONSE) if use_old_response else ""
                    context_chunks_text = await _get_full_text_anon(db, project_id, DocumentCategory.NEW_RFP)
                    # Also load inspiration documents (always anonymized)
                    inspiration_content = await _get_full_text_anon(db, project_id, DocumentCategory.INSPIRATION)
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
                    # Search inspiration documents for relevant content
                    inspiration_results = VectorService.search(
                        str(project_id),
                        f"{ch_title} {ch_description}",
                        top_k=3, category_filter="inspiration",
                    )
                    # Anonymize context chunks too — Mistral must never see raw secrets
                    if context_results:
                        raw_context = "\n\n".join([r["content"] for r in context_results])
                        context_chunks_text = await AnonymizationService.anonymize_text(raw_context, project_id, db)
                    else:
                        context_chunks_text = ""
                    if search_results:
                        raw_old = "\n\n".join([r["content"] for r in search_results])
                        old_response_content = await AnonymizationService.anonymize_text(raw_old, project_id, db)
                    # Inspiration content is ALWAYS anonymized to prevent client name leaks
                    if inspiration_results:
                        raw_inspi = "\n\n".join([r["content"] for r in inspiration_results])
                        inspiration_content = await AnonymizationService.anonymize_text(raw_inspi, project_id, db)

                _update("anonymizing", 25, "Preparation...")
                notes_text = "\n".join([n.get("content", "") for n in ch_notes])
                anon_notes = await _anon(notes_text, project_id, db) if notes_text else ""
                ai_params = {
                    "mode": "generate",
                    "old_response_content": old_response_content,
                    "context_chunks_text": context_chunks_text,
                    "inspiration_content": inspiration_content,
                    "notes_text": anon_notes,
                }

            # ── Load analyzed images for this project ──
            # Only include informative images that were successfully analyzed.
            # Mistral receives anonymized metadata only — never the actual images.
            _update("loading_images", 28, "Chargement des images analysees...")
            available_images = await _load_project_images(
                db, project_id, ch_title, ch_description,
            )

        # ── Phase 2: AI generation (NO DB connection held) ──
        # All text fields sent to Mistral are now anonymized.
        # available_images contains only anonymized metadata — no raw image data.
        mode = ai_params["mode"]
        if mode == "custom":
            _update("generating", 35, "Generation IA en cours...")
            result_text = await ai_service.execute_custom_prompt(
                ai_params["anon_content"], ai_params["anon_prompt"], anon_title,
                ai_context=anon_ai_context,
                company_name=proj_company_name, client_name=proj_client_name,
            )
        elif mode == "enrich":
            _update("generating", 35, "Enrichissement IA en cours...")
            result_text = await ai_service.enrich_content(
                ai_params["anon_content"], anon_title, anon_rfp_requirement, anon_improvement,
                ai_context=anon_ai_context,
                company_name=proj_company_name, client_name=proj_client_name,
                available_images=available_images,
            )
        else:
            _update("generating", 40, "Generation IA du contenu...")
            result_text = await ai_service.generate_chapter_content(
                chapter_title=anon_title,
                chapter_description=anon_description,
                rfp_requirement=anon_rfp_requirement,
                old_response_content=ai_params["old_response_content"],
                context_chunks=ai_params["context_chunks_text"],
                improvement_axes=anon_improvement,
                notes=ai_params["notes_text"],
                ai_context=anon_ai_context,
                inspiration_content=ai_params.get("inspiration_content", ""),
                company_name=proj_company_name,
                client_name=proj_client_name,
                available_images=available_images,
            )

        # ── Phase 3: Deanonymize + save (with image references) ──
        _update("deanonymizing", 80, "Deanonymisation...")
        async with TaskSession() as db:
            final_content = await AnonymizationService.deanonymize_text(result_text, project_id, db)

            # Extract image references from the generated content
            import re
            image_refs = re.findall(r'\[INSERT_IMAGE:([^\]]+)\]', final_content)
            image_references = []
            if image_refs and available_images:
                img_lookup = {str(img["id"]): img for img in available_images}
                for ref_id in image_refs:
                    ref_id_clean = ref_id.strip()
                    if ref_id_clean in img_lookup:
                        img = img_lookup[ref_id_clean]
                        image_references.append({
                            "image_id": ref_id_clean,
                            "file_path": img.get("file_path", ""),
                            "description": img.get("description", ""),
                            "image_type": img.get("image_type", ""),
                        })

            _update("saving", 90, "Enregistrement...")
            chap_result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
            chap = chap_result.scalar_one()
            chap.content = final_content
            chap.status = ChapterStatus.IN_PROGRESS
            if image_references:
                chap.image_references = image_references
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


async def _load_project_images(db, project_id, chapter_title: str, chapter_description: str):
    """Load analyzed images from the project's documents for AI context.

    Returns a list of image metadata dicts containing ONLY anonymized information
    (no raw image data). Mistral uses these to decide where to insert images
    via [INSERT_IMAGE:id] markers.

    Images are filtered to:
    - Only include successfully analyzed images (analysis_status = 'completed')
    - Only include informative images (not decorative logos/separators)
    - Prefer images whose suggested_usage matches the chapter context
    """
    from sqlalchemy import select
    from ..models.document import Document, DocumentImage, ProcessingStatus

    try:
        result = await db.execute(
            select(DocumentImage, Document.original_filename)
            .join(Document, Document.id == DocumentImage.document_id)
            .where(Document.project_id == project_id)
            .where(Document.processing_status == ProcessingStatus.COMPLETED)
            .where(DocumentImage.analysis_status == "completed")
            .order_by(DocumentImage.page_number, DocumentImage.created_at)
        )
        rows = result.all()
    except Exception as e:
        logger.warning("Failed to load project images: %s", e)
        return []

    images = []
    for db_image, doc_name in rows:
        # Skip non-informative images (decorative, logos, etc.)
        img_type = db_image.image_type or ""
        if img_type in ("logo", "illustration") and not db_image.key_information:
            continue

        # Build the anonymized metadata that Mistral will see
        images.append({
            "id": str(db_image.id),
            "file_path": db_image.file_path,
            "image_type": img_type,
            "description": db_image.description or "",
            "anonymized_description": db_image.anonymized_description or "",
            "key_information": db_image.key_information or [],
            "suggested_usage": db_image.suggested_usage or "",
            "page_number": db_image.page_number,
            "document_name": doc_name,
            "width": db_image.width,
            "height": db_image.height,
        })

    # Limit to most relevant images (avoid flooding the prompt)
    # Prioritize images whose suggested_usage matches the chapter context
    if len(images) > 15:
        chapter_context = f"{chapter_title} {chapter_description}".lower()
        for img in images:
            usage = (img.get("suggested_usage") or "").lower()
            desc = (img.get("anonymized_description") or "").lower()
            # Simple relevance scoring
            score = 0
            for word in chapter_context.split():
                if len(word) > 3:
                    if word in usage:
                        score += 2
                    if word in desc:
                        score += 1
            img["_relevance"] = score

        images.sort(key=lambda x: x.get("_relevance", 0), reverse=True)
        images = images[:15]

        # Clean up internal scoring field
        for img in images:
            img.pop("_relevance", None)

    return images


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

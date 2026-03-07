"""Celery tasks for document processing (upload, extraction, indexing).

Reliability features:
- Per-phase error handling: each phase can fail independently
- Structured logging: every step logs document_id + phase for debugging
- Partial recovery: if anonymization fails, we still save raw chunks
- Graceful timeout: catches SoftTimeLimitExceeded to save progress
- Redis lock: prevents concurrent processing of the same content hash
"""
import asyncio
import logging
import time
import uuid

import redis as _redis_lib
from celery.exceptions import SoftTimeLimitExceeded

from ..celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="tasks.process_document",
    bind=True,
    max_retries=2,
    reject_on_worker_lost=True,
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=30,
    retry_backoff_max=120,
    retry_jitter=True,
)
def process_document_task(self, document_id: str, project_id: str):
    """Celery wrapper — runs the async processing pipeline in its own event loop.

    ``reject_on_worker_lost`` prevents infinite redelivery when the worker
    is killed (OOM, hard time-limit SIGKILL, etc.) while
    ``task_acks_late`` is enabled.

    ``autoretry_for`` handles transient I/O errors (Redis/DB connection drops)
    with exponential backoff.
    """
    delivery_info = self.request.delivery_info or {}
    redelivered = getattr(self.request, "redelivered", False)
    retries = self.request.retries or 0

    logger.info(
        "[doc:%s] Task started (attempt=%d, redelivered=%s)",
        document_id, retries + 1, redelivered,
    )

    if redelivered and retries >= self.max_retries:
        logger.error(
            "[doc:%s] Giving up: redelivered after %d retries",
            document_id, retries,
        )
        asyncio.run(_mark_document_failed(
            document_id, "Échec après plusieurs tentatives (worker crash)"
        ))
        return

    asyncio.run(_process_document_async(document_id, project_id))


async def _process_document_async(document_id: str, project_id: str):
    """Full document processing pipeline (async).

    Uses a **task-scoped** engine so that each ``asyncio.run()`` gets its own
    clean connection pool — the module-level engine retains asyncpg connections
    bound to previous (dead) event loops, causing "unexpected EOF" errors.

    The pipeline is split into isolated phases with independent error handling
    so that a failure in one phase (e.g., anonymization) doesn't lose the
    work done in previous phases (e.g., text extraction).
    """
    from sqlalchemy import select
    from ..database import create_task_engine
    from ..models.document import (
        Document, DocumentChunk, DocumentImage,
        FileType, ProcessingStatus,
    )
    from ..services.document_service import DocumentProcessor
    from ..services.vector_service import VectorService
    from ..services.anonymization_service import AnonymizationService
    from ..services.progress_service import ProgressTracker
    from ..models.project import AIConfig, RFPProject
    from ..services.llm_provider import ProviderConfig

    task_engine, TaskSession = create_task_engine()
    t_start = time.monotonic()
    _content_lock = None  # Redis lock for content dedup

    try:
        # ── Phase 1: Load document metadata + mark processing ──
        logger.info("[doc:%s] Phase 1: Loading metadata", document_id)
        async with TaskSession() as db:
            result = await db.execute(
                select(Document).where(Document.id == uuid.UUID(document_id))
            )
            document = result.scalar_one_or_none()
            if not document:
                logger.error("[doc:%s] Document not found in DB — aborting", document_id)
                return

            # ── Content-hash lock: prevent concurrent processing of identical files ──
            content_hash = getattr(document, "content_hash", "") or ""
            if content_hash:
                import os
                _redis_url = os.environ.get("REDIS_URL")
                if not _redis_url:
                    _rp = os.environ.get("REDIS_PASSWORD", "")
                    _redis_url = f"redis://:{_rp}@redis:6379/0" if _rp else "redis://redis:6379/0"
                _lock_redis = _redis_lib.from_url(_redis_url, decode_responses=True)
                lock_key = f"docproc:lock:{content_hash}"
                _content_lock = _lock_redis.lock(
                    lock_key, timeout=1200, blocking_timeout=5,
                )
                acquired = _content_lock.acquire(blocking=True)
                if not acquired:
                    logger.warning(
                        "[doc:%s] Another worker is processing identical content (hash=%s) — skipping",
                        document_id, content_hash[:12],
                    )
                    # Check if a sibling document with same hash is already completed
                    from sqlalchemy import and_
                    sibling = await db.execute(
                        select(Document).where(
                            and_(
                                Document.project_id == document.project_id,
                                Document.content_hash == content_hash,
                                Document.id != document.id,
                                Document.processing_status == ProcessingStatus.COMPLETED,
                            )
                        )
                    )
                    if sibling.scalar_one_or_none():
                        logger.info("[doc:%s] Sibling already completed — marking as duplicate", document_id)
                        document.processing_status = ProcessingStatus.FAILED
                        await db.commit()
                        ProgressTracker.fail(document_id, "Doublon déjà traité")
                    return

            ProgressTracker.start(document_id, document.original_filename)
            document.processing_status = ProcessingStatus.PROCESSING
            await db.commit()

            file_path = document.file_path
            file_type = document.file_type
            original_filename = document.original_filename
            category_value = document.category.value

        # ── Phase 2: File I/O + text extraction + chunking (CPU-bound) ──
        logger.info("[doc:%s] Phase 2: Extracting text from %s (%s)", document_id, original_filename, file_type.value)
        ProgressTracker.update(document_id, "extracting_text")

        def _extract_and_chunk():
            with open(file_path, "rb") as f:
                file_content = f.read()

            _text = ""
            _pages_data = None
            _images_data = []
            _page_count = None

            if file_type == FileType.PDF:
                _text, _page_count, _pages_data = DocumentProcessor.extract_text_from_pdf(file_content)
                ProgressTracker.update(document_id, "extracting_images")
                _images_data = DocumentProcessor.extract_images_from_pdf(file_content, document_id)

            elif file_type == FileType.DOC:
                try:
                    docx_content = DocumentProcessor.convert_doc_to_docx(file_content)
                    _text, _sections = DocumentProcessor.extract_text_from_docx(docx_content)
                    _page_count = max(1, len(_text.split()) // 300)
                    ProgressTracker.update(document_id, "extracting_images")
                    _images_data = DocumentProcessor.extract_images_from_docx(docx_content, document_id)
                except Exception as doc_err:
                    logger.warning("[doc:%s] LibreOffice conversion failed, trying fallback: %s", document_id, doc_err)
                    # Fallback: extract text directly with antiword/catdoc
                    _text = DocumentProcessor.extract_text_from_doc_fallback(file_content)
                    if _text.strip():
                        _page_count = max(1, len(_text.split()) // 300)
                        logger.info("[doc:%s] Fallback extraction succeeded (%d chars)", document_id, len(_text))
                    else:
                        logger.error("[doc:%s] All .doc extraction methods failed: %s", document_id, doc_err, exc_info=True)

            elif file_type == FileType.DOCX:
                try:
                    _text, _sections = DocumentProcessor.extract_text_from_docx(file_content)
                    _page_count = max(1, len(_text.split()) // 300)
                    ProgressTracker.update(document_id, "extracting_images")
                    _images_data = DocumentProcessor.extract_images_from_docx(file_content, document_id)
                except Exception as docx_err:
                    logger.error("[doc:%s] DOCX parsing failed: %s", document_id, docx_err, exc_info=True)
                    _text = ""

            elif file_type in (FileType.XLSX, FileType.XLS):
                _text, _pages_data = DocumentProcessor.extract_text_from_excel(file_content)
                _page_count = max(1, len(_pages_data))

            if not _text.strip():
                return None, None, None, None, None

            ProgressTracker.update(document_id, "chunking")
            _chunks = DocumentProcessor.create_chunks(
                text=_text,
                document_id=document_id,
                document_name=original_filename,
                category=category_value,
                pages_data=_pages_data,
            )
            return _text, _pages_data, _images_data, _page_count, _chunks

        text, pages_data, images_data, page_count, chunks = await asyncio.to_thread(
            _extract_and_chunk
        )

        if text is None:
            logger.warning("[doc:%s] No text extracted — marking FAILED", document_id)
            fail_msg = "Aucun texte extrait du document"
            if file_type == FileType.DOC:
                fail_msg = "Impossible d'extraire le texte du fichier .doc — le format est peut-être trop ancien ou le fichier corrompu"
            ProgressTracker.fail(document_id, fail_msg)
            async with TaskSession() as db:
                result = await db.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                doc = result.scalar_one()
                doc.processing_status = ProcessingStatus.FAILED
                await db.commit()
            return

        logger.info(
            "[doc:%s] Extraction done: %d chars, %d chunks, %d images",
            document_id, len(text), len(chunks), len(images_data),
        )

        # ── Load NER provider config from AIConfig ──
        try:
            async with TaskSession() as db:
                proj_result = await db.execute(
                    select(RFPProject).where(RFPProject.id == uuid.UUID(project_id))
                )
                project = proj_result.scalar_one_or_none()
                if project:
                    ai_cfg_result = await db.execute(
                        select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
                    )
                    ai_config = ai_cfg_result.scalar_one_or_none()
                    if ai_config:
                        from ..security import decrypt_api_key
                        _api_key = ""
                        if ai_config.ner_provider == "mistral":
                            _api_key = decrypt_api_key(ai_config.mistral_api_key_encrypted or "")
                        elif ai_config.ner_provider == "scaleway":
                            _api_key = decrypt_api_key(ai_config.scaleway_api_key_encrypted or "")
                        AnonymizationService.configure(ProviderConfig(
                            provider=ai_config.ner_provider or "ollama",
                            base_url=ai_config.ollama_base_url if ai_config.ner_provider == "ollama" else "",
                            api_key=_api_key,
                            model=ai_config.ner_model or "qwen2.5:14b",
                            scaleway_project_id=ai_config.scaleway_project_id or "",
                        ))
        except Exception as cfg_err:
            logger.warning("[doc:%s] Failed to load NER config — using defaults: %s", document_id, cfg_err)

        # ── Phase 3a: Anonymize chunks ──
        # If anonymization fails, we fall back to saving raw text as-is
        # so the document is still usable (just not anonymized).
        logger.info("[doc:%s] Phase 3a: Anonymizing %d chunks", document_id, len(chunks))
        ProgressTracker.update(document_id, "anonymizing")

        anonymized_texts = None

        def _anon_progress(done: int, total: int):
            ProgressTracker.update_sub_progress(document_id, done, total)

        try:
            async with TaskSession() as db:
                chunk_texts = [c["content"] for c in chunks]
                anonymized_texts = await AnonymizationService.anonymize_chunks_batch(
                    chunk_texts, uuid.UUID(project_id), db,
                    progress_callback=_anon_progress,
                )
                await db.commit()  # persist new anonymization mappings

            # Check if NER actually worked or just regex fallback
            ner_diag = AnonymizationService.get_ner_diagnostic()
            if not ner_diag.get("ollama_reachable"):
                logger.warning(
                    "[doc:%s] Anonymization completed with REGEX ONLY — "
                    "Ollama NER was not available. Reason: %s. "
                    "Company names, person names, etc. were NOT detected.",
                    document_id, ner_diag.get("failure_reason"),
                )
            elif ner_diag.get("last_ner_produced_entities") is False:
                logger.warning(
                    "[doc:%s] Anonymization completed but NER returned 0 entities. "
                    "Reason: %s",
                    document_id, ner_diag.get("failure_reason"),
                )
            else:
                logger.info("[doc:%s] Anonymization completed successfully (NER active)", document_id)

            # Log AI usage for anonymization NER
            try:
                from ..services.ai_service import log_ai_usage
                ner_in, ner_out = AnonymizationService.get_and_reset_token_usage()
                if ner_in > 0 or ner_out > 0:
                    ner_cfg = AnonymizationService._get_provider_config()
                    async with TaskSession() as usage_db:
                        await log_ai_usage(
                            usage_db, uuid.UUID(project_id), "anonymization_ner",
                            ner_cfg.provider, ner_cfg.model,
                            ner_in, ner_out,
                        )
            except Exception as cost_err:
                logger.warning("[doc:%s] Failed to log NER AI usage: %s", document_id, cost_err)

        except SoftTimeLimitExceeded:
            raise  # Don't catch timeout — let it propagate to the outer handler
        except Exception as anon_err:
            logger.error(
                "[doc:%s] Anonymization failed — saving raw chunks: %s",
                document_id, anon_err, exc_info=True,
            )
            # Fall back to raw text (not anonymized) so document is still usable
            anonymized_texts = [c["content"] for c in chunks]

        # ── Phase 3b: Save chunks to DB ──
        logger.info("[doc:%s] Phase 3b: Saving %d chunks to DB", document_id, len(chunks))
        ProgressTracker.update(document_id, "saving_chunks")
        async with TaskSession() as db:
            for chunk_data, anonymized in zip(chunks, anonymized_texts):
                db_chunk = DocumentChunk(
                    document_id=uuid.UUID(document_id),
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    anonymized_content=anonymized,
                    metadata_json={
                        "document_name": chunk_data["document_name"],
                        "category": chunk_data["category"],
                    },
                    page_number=chunk_data.get("page_number", 0),
                    section_title=chunk_data.get("section_title", ""),
                )
                db.add(db_chunk)
            await db.commit()

        # ── Phase 3c: Index in ChromaDB ──
        logger.info("[doc:%s] Phase 3c: Indexing %d chunks in ChromaDB", document_id, len(chunks))
        ProgressTracker.update(document_id, "indexing")

        vector_chunks = [
            {
                "id": chunk_data["id"],
                "content": chunk_data["content"],
                "document_id": document_id,
                "document_name": chunk_data["document_name"],
                "category": chunk_data["category"],
                "page_number": chunk_data.get("page_number", 0),
                "section_title": chunk_data.get("section_title", ""),
                "chunk_index": chunk_data["chunk_index"],
            }
            for chunk_data in chunks
        ]

        try:
            await asyncio.to_thread(VectorService.index_chunks, project_id, vector_chunks)
            logger.info("[doc:%s] ChromaDB indexing completed", document_id)
        except Exception as vec_err:
            # Indexing failure is non-fatal: document is saved, just not searchable
            logger.error(
                "[doc:%s] ChromaDB indexing failed (document saved but not searchable): %s",
                document_id, vec_err, exc_info=True,
            )

        # ── Phase 3d: Categorize images by size heuristics ──
        # Vision AI analysis is NO LONGER automatic — users select images
        # to analyze from the image gallery UI, then trigger analysis on demand.
        # Here we only assign a basic category based on dimensions.
        if images_data:
            from ..models.document import ImageAnalysisStatus

            logger.info("[doc:%s] Phase 3d: Categorizing %d images by size", document_id, len(images_data))

            for img_data in images_data:
                w = img_data.get("width", 0)
                h = img_data.get("height", 0)
                img_data["image_category"] = _guess_image_category(w, h)
                img_data["analysis_status"] = ImageAnalysisStatus.PENDING.value
                img_data["selected"] = False

            cats = {}
            for img in images_data:
                c = img["image_category"]
                cats[c] = cats.get(c, 0) + 1
            logger.info(
                "[doc:%s] Image categorization done: %s",
                document_id, ", ".join(f"{k}={v}" for k, v in cats.items()),
            )

        # ── Phase 3e: Save images + finalize document ──
        logger.info("[doc:%s] Phase 3e: Finalizing", document_id)
        ProgressTracker.update(document_id, "finalizing")
        async with TaskSession() as db:
            for img_data in images_data:
                db_image = DocumentImage(
                    document_id=uuid.UUID(document_id),
                    stored_filename=img_data["stored_filename"],
                    file_path=img_data["file_path"],
                    description=img_data.get("description", ""),
                    page_number=img_data.get("page_number", 0),
                    context=img_data.get("context", ""),
                    tags=img_data.get("tags", []),
                    width=img_data.get("width", 0),
                    height=img_data.get("height", 0),
                    content_hash=img_data.get("content_hash", ""),
                    # Gallery fields
                    image_category=img_data.get("image_category", "autre"),
                    selected=img_data.get("selected", False),
                    # Vision analysis fields (populated later on demand)
                    analysis_status=img_data.get("analysis_status", "pending"),
                    image_type=img_data.get("image_type", ""),
                    anonymized_description=img_data.get("anonymized_description", ""),
                    key_information=img_data.get("key_information", []),
                    pii_detected=img_data.get("pii_detected", []),
                    ocr_text=img_data.get("ocr_text", ""),
                    anonymized_ocr_text=img_data.get("anonymized_ocr_text", ""),
                    suggested_usage=img_data.get("suggested_usage", ""),
                    section_title=img_data.get("section_title", ""),
                )
                db.add(db_image)

            # Reuse mappings already created by anonymize_chunks_batch
            anonymized_full_text = await AnonymizationService.apply_existing_mappings(
                text, uuid.UUID(project_id), db
            )

            result = await db.execute(
                select(Document).where(Document.id == uuid.UUID(document_id))
            )
            document = result.scalar_one()
            document.full_text = text
            document.anonymized_full_text = anonymized_full_text
            if page_count is not None:
                document.page_count = page_count
            document.chunk_count = len(chunks)
            document.processing_status = ProcessingStatus.COMPLETED
            ProgressTracker.update(document_id, "completed")
            await db.commit()

        elapsed = time.monotonic() - t_start
        logger.info(
            "[doc:%s] Processing completed in %.1fs (%d chunks, %d pages)",
            document_id, elapsed, len(chunks), page_count or 0,
        )

    except SoftTimeLimitExceeded:
        elapsed = time.monotonic() - t_start
        logger.error(
            "[doc:%s] Soft time limit exceeded after %.1fs — saving partial progress",
            document_id, elapsed,
        )
        ProgressTracker.fail(document_id, f"Délai dépassé après {elapsed:.0f}s")
        await _mark_document_failed_safe(
            TaskSession, document_id, "Traitement trop long (délai dépassé)"
        )

    except Exception as e:
        elapsed = time.monotonic() - t_start
        logger.error(
            "[doc:%s] Processing failed after %.1fs: %s",
            document_id, elapsed, e, exc_info=True,
        )
        ProgressTracker.fail(document_id, str(e))
        await _mark_document_failed_safe(TaskSession, document_id, str(e)[:200])

    finally:
        # Release content-hash lock so other workers can proceed
        if _content_lock is not None:
            try:
                _content_lock.release()
            except Exception:
                pass  # Lock may have expired — that's fine
        await task_engine.dispose()


async def _mark_document_failed_safe(TaskSession, document_id: str, reason: str):
    """Mark a document as FAILED with multiple retry attempts.

    Uses fresh sessions on each attempt to handle transient DB errors.
    """
    from sqlalchemy import select
    from ..models.document import Document, ProcessingStatus

    for attempt in range(3):
        try:
            async with TaskSession() as db:
                result = await db.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                document = result.scalar_one_or_none()
                if document and document.processing_status != ProcessingStatus.FAILED:
                    document.processing_status = ProcessingStatus.FAILED
                    await db.commit()
                    logger.info("[doc:%s] Marked as FAILED (attempt %d)", document_id, attempt + 1)
            return
        except Exception as db_err:
            logger.warning(
                "[doc:%s] Failed to mark FAILED (attempt %d/3): %s",
                document_id, attempt + 1, db_err,
            )
            await asyncio.sleep(1 * (attempt + 1))


async def _mark_document_failed(document_id: str, reason: str):
    """Mark a document as FAILED (used by the redelivery guard)."""
    from sqlalchemy import select
    from ..database import create_task_engine
    from ..models.document import Document, ProcessingStatus
    from ..services.progress_service import ProgressTracker

    ProgressTracker.fail(document_id, reason)
    task_engine, TaskSession = create_task_engine()
    try:
        await _mark_document_failed_safe(TaskSession, document_id, reason)
    finally:
        await task_engine.dispose()


@celery.task(
    name="tasks.analyze_images",
    bind=True,
    max_retries=1,
    reject_on_worker_lost=True,
    soft_time_limit=7200,   # 2 h — large batches need room (global 15 min is too tight)
    time_limit=7500,        # 2 h 05 hard kill
)
def analyze_images_task(self, project_id: str, image_ids: list[str]):
    """Celery task: run Vision AI analysis on selected images.

    Triggered from the image gallery when the user clicks "Analyze".
    Results are saved to DB **incrementally** so that a timeout never
    loses already-completed work.
    """
    logger.info("[project:%s] analyze_images_task started (%d images)", project_id, len(image_ids))
    try:
        asyncio.run(_analyze_images_async(project_id, image_ids))
    except SoftTimeLimitExceeded:
        logger.warning(
            "[project:%s] Image analysis timed out — partial results already saved",
            project_id,
        )
        # Completed images were already persisted incrementally.
        # Mark whatever is still pending/in-progress as FAILED.
        try:
            asyncio.run(_finalize_after_timeout(project_id, image_ids))
        except Exception:
            logger.error("[project:%s] Failed to finalize after timeout", project_id, exc_info=True)



async def _analyze_images_async(project_id: str, image_ids: list[str]):
    """Run Vision AI on the given image IDs, saving each result to DB immediately."""
    from sqlalchemy import select
    from ..database import create_task_engine
    from ..models.document import DocumentImage, ImageAnalysisStatus
    from ..services.image_analysis_service import ImageAnalysisService
    from ..services.anonymization_service import AnonymizationService
    from ..services.progress_service import set_progress
    from ..models.project import AIConfig, RFPProject
    from ..services.llm_provider import ProviderConfig

    # Reset service state so the new event loop gets fresh asyncio primitives.
    ImageAnalysisService._reset()

    task_engine, TaskSession = create_task_engine()
    try:
        # ── Load vision + NER provider config from AIConfig ──
        async with TaskSession() as db:
            proj_result = await db.execute(
                select(RFPProject).where(RFPProject.id == uuid.UUID(project_id))
            )
            project = proj_result.scalar_one_or_none()
            if project:
                ai_cfg_result = await db.execute(
                    select(AIConfig).where(AIConfig.workspace_id == project.workspace_id)
                )
                ai_config = ai_cfg_result.scalar_one_or_none()
                if ai_config:
                    from ..security import decrypt_api_key as _dk
                    # Vision provider
                    _v_key = ""
                    if ai_config.vision_provider == "mistral":
                        _v_key = _dk(ai_config.mistral_api_key_encrypted or "")
                    elif ai_config.vision_provider == "scaleway":
                        _v_key = _dk(ai_config.scaleway_api_key_encrypted or "")
                    _scw_pid = ai_config.scaleway_project_id or ""
                    ImageAnalysisService.configure(ProviderConfig(
                        provider=ai_config.vision_provider or "ollama",
                        base_url=ai_config.ollama_base_url if ai_config.vision_provider == "ollama" else "",
                        api_key=_v_key,
                        model=ai_config.vision_model or "llama3.2-vision:11b",
                        scaleway_project_id=_scw_pid,
                    ))
                    # NER provider (used for OCR anonymization)
                    _n_key = ""
                    if ai_config.ner_provider == "mistral":
                        _n_key = _dk(ai_config.mistral_api_key_encrypted or "")
                    elif ai_config.ner_provider == "scaleway":
                        _n_key = _dk(ai_config.scaleway_api_key_encrypted or "")
                    AnonymizationService.configure(ProviderConfig(
                        provider=ai_config.ner_provider or "ollama",
                        base_url=ai_config.ollama_base_url if ai_config.ner_provider == "ollama" else "",
                        api_key=_n_key,
                        model=ai_config.ner_model or "qwen2.5:14b",
                        scaleway_project_id=_scw_pid,
                    ))

        # Load images from DB
        async with TaskSession() as db:
            result = await db.execute(
                select(DocumentImage).where(
                    DocumentImage.id.in_([uuid.UUID(iid) for iid in image_ids])
                )
            )
            db_images = result.scalars().all()

        total = len(db_images)
        if total == 0:
            logger.warning("[project:%s] No images found for analysis", project_id)
            return

        # Build batch data for the analysis service
        images_data = [
            {
                "file_path": img.file_path,
                "context": img.context or "",
                "section_title": img.section_title or "",
                "_db_id": str(img.id),
            }
            for img in db_images
        ]

        set_progress("image_analysis", project_id, {
            "status": "running",
            "step": "analyzing",
            "progress": 0,
            "message": f"Lancement de l'analyse de {total} images...",
        })

        done_count = 0

        async def _process_one(img_meta: dict):
            """Analyze one image and persist its result to DB immediately."""
            nonlocal done_count
            db_id = img_meta["_db_id"]
            status = ImageAnalysisStatus.COMPLETED.value

            try:
                analysis = await ImageAnalysisService.analyze_image(
                    file_path=img_meta["file_path"],
                    page_context=img_meta.get("context", ""),
                    section_title=img_meta.get("section_title", ""),
                )
            except Exception as e:
                logger.error(
                    "[project:%s] Image %s analysis error: %s",
                    project_id, db_id, e,
                )
                analysis = ImageAnalysisService._empty_analysis(
                    f"Erreur: {str(e)[:100]}"
                )
                status = ImageAnalysisStatus.FAILED.value

            # ── Persist result immediately ──
            async with TaskSession() as db:
                result = await db.execute(
                    select(DocumentImage).where(
                        DocumentImage.id == uuid.UUID(db_id)
                    )
                )
                img = result.scalar_one_or_none()
                if not img:
                    return

                img.image_type = analysis.get("type", "autre")
                img.description = analysis.get("description", "")
                img.key_information = analysis.get("key_information", [])
                img.pii_detected = analysis.get("pii_detected", [])
                img.ocr_text = analysis.get("ocr_text", "")
                img.suggested_usage = analysis.get("suggested_usage", "")
                img.tags = analysis.get("key_information", [])[:10]
                img.analysis_status = status

                # Anonymize OCR text
                ocr_text = analysis.get("ocr_text", "")
                if ocr_text:
                    try:
                        anon_ocr = await AnonymizationService.anonymize_text(
                            ocr_text, uuid.UUID(project_id), db,
                        )
                        img.anonymized_ocr_text = anon_ocr
                    except Exception:
                        img.anonymized_ocr_text = ""

                # Build anonymized description
                img.anonymized_description = ImageAnalysisService.build_anonymized_description(
                    analysis, img.anonymized_ocr_text or "",
                )

                await db.commit()

            done_count += 1
            set_progress("image_analysis", project_id, {
                "status": "running",
                "step": "analyzing",
                "progress": int(100 * done_count / total),
                "message": f"Analyse {done_count}/{total} images",
            })

        # Process all images concurrently (service semaphore controls parallelism)
        tasks = [asyncio.create_task(_process_one(img)) for img in images_data]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Log AI usage for image analysis (vision) + NER anonymization of OCR
        try:
            from ..services.ai_service import log_ai_usage
            vision_in, vision_out = ImageAnalysisService.get_and_reset_token_usage()
            if vision_in > 0 or vision_out > 0:
                vision_cfg = ImageAnalysisService._get_provider_config()
                async with TaskSession() as usage_db:
                    await log_ai_usage(
                        usage_db, uuid.UUID(project_id), "image_analysis",
                        vision_cfg.provider, vision_cfg.model,
                        vision_in, vision_out,
                    )
            ner_in, ner_out = AnonymizationService.get_and_reset_token_usage()
            if ner_in > 0 or ner_out > 0:
                ner_cfg = AnonymizationService._get_provider_config()
                async with TaskSession() as usage_db:
                    await log_ai_usage(
                        usage_db, uuid.UUID(project_id), "anonymization_ocr",
                        ner_cfg.provider, ner_cfg.model,
                        ner_in, ner_out,
                    )
        except Exception as cost_err:
            logger.warning("[project:%s] Failed to log AI usage: %s", project_id, cost_err)

        set_progress("image_analysis", project_id, {
            "status": "completed",
            "step": "completed",
            "progress": 100,
            "message": f"Analyse terminée : {done_count}/{total} images traitées",
        })
        logger.info("[project:%s] Image analysis completed: %d/%d images", project_id, done_count, total)

    except Exception as e:
        logger.error("[project:%s] Image analysis failed: %s", project_id, e, exc_info=True)
        set_progress("image_analysis", project_id, {
            "status": "error",
            "step": "error",
            "progress": -1,
            "message": f"Erreur: {str(e)[:120]}",
        })
        # Mark remaining unprocessed images as failed
        try:
            async with TaskSession() as db:
                result = await db.execute(
                    select(DocumentImage).where(
                        DocumentImage.id.in_([uuid.UUID(iid) for iid in image_ids]),
                        DocumentImage.analysis_status.notin_([
                            ImageAnalysisStatus.COMPLETED.value,
                            ImageAnalysisStatus.FAILED.value,
                        ]),
                    )
                )
                for img in result.scalars().all():
                    img.analysis_status = ImageAnalysisStatus.FAILED.value
                await db.commit()
        except Exception:
            pass
    finally:
        await task_engine.dispose()


async def _finalize_after_timeout(project_id: str, image_ids: list[str]):
    """Mark remaining unprocessed images as FAILED after a SoftTimeLimitExceeded."""
    from sqlalchemy import select
    from ..database import create_task_engine
    from ..models.document import DocumentImage, ImageAnalysisStatus
    from ..services.progress_service import set_progress

    task_engine, TaskSession = create_task_engine()
    try:
        async with TaskSession() as db:
            result = await db.execute(
                select(DocumentImage).where(
                    DocumentImage.id.in_([uuid.UUID(iid) for iid in image_ids]),
                    DocumentImage.analysis_status.notin_([
                        ImageAnalysisStatus.COMPLETED.value,
                        ImageAnalysisStatus.FAILED.value,
                    ]),
                )
            )
            remaining = result.scalars().all()
            for img in remaining:
                img.analysis_status = ImageAnalysisStatus.FAILED.value
            await db.commit()
            remaining_count = len(remaining)

        completed = len(image_ids) - remaining_count
        set_progress("image_analysis", project_id, {
            "status": "error",
            "step": "error",
            "progress": -1,
            "message": f"Timeout : {completed}/{len(image_ids)} images traitées avant expiration",
        })
    finally:
        await task_engine.dispose()


@celery.task(name="tasks.vector_search", queue="documents")
def vector_search_task(
    project_id: str,
    query: str,
    top_k: int = 10,
    category_filter: str | None = None,
) -> list[dict]:
    """Run a vector similarity search on the documents worker.

    This task exists so that AI workers (which handle LLM calls) don't need
    to load the ~800MB embedding model.  The documents worker already has it
    in memory, so we route search requests there via this lightweight task.

    Returns the list of search result dicts directly (small payload).
    """
    from ..services.vector_service import VectorService

    return VectorService.search(
        project_id, query, top_k=top_k, category_filter=category_filter,
    )


def _guess_image_category(width: int, height: int) -> str:
    """Guess an image category from its pixel dimensions.

    This is a rough heuristic to pre-sort images before the user reviews
    them in the gallery.  The Vision AI analysis (triggered on demand)
    will produce a more accurate classification.
    """
    area = width * height
    if area == 0:
        return "autre"

    # Tiny images are almost always icons / bullets
    if area < 4_000:          # < ~63×63
        return "icone"

    # Small square-ish images are usually logos
    ratio = max(width, height) / max(min(width, height), 1)
    if area < 40_000 and ratio < 2:  # < ~200×200 and roughly square
        return "logo"

    # Very wide images (banners, separators, headers)
    if ratio > 5:
        return "icone"

    # Medium images with landscape orientation → likely schema/diagram
    if area < 300_000 and ratio > 1.3:
        return "schema"

    # Large images → illustration or photo
    if area >= 300_000:
        return "illustration"

    return "autre"

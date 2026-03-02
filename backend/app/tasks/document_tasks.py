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
                _redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
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
                    logger.error("[doc:%s] DOC conversion failed: %s", document_id, doc_err, exc_info=True)
                    _text = ""

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
            ProgressTracker.fail(document_id, "Aucun texte extrait du document")
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

        # ── Phase 3d: Analyze images with local Vision AI ──
        # Uses a local vision model (LLaVA on DGX Spark) to generate structured
        # metadata for each image. This metadata (anonymized) is later used by
        # Mistral for intelligent image placement — Mistral never sees the images.
        analyzed_images = images_data  # fallback: use raw extraction data
        if images_data:
            from ..services.image_analysis_service import ImageAnalysisService
            from ..models.document import ImageAnalysisStatus

            logger.info("[doc:%s] Phase 3d: Analyzing %d images with Vision AI", document_id, len(images_data))
            ProgressTracker.update(document_id, "analyzing_images")

            def _img_progress(done: int, total: int):
                ProgressTracker.update_sub_progress(document_id, done, total)

            try:
                analysis_results = await ImageAnalysisService.analyze_images_batch(
                    images_data, progress_callback=_img_progress,
                )

                # Merge analysis results into images_data
                for img_data, analysis in zip(images_data, analysis_results):
                    img_data["image_type"] = analysis.get("type", "autre")
                    img_data["description"] = analysis.get("description", "")
                    img_data["key_information"] = analysis.get("key_information", [])
                    img_data["pii_detected"] = analysis.get("pii_detected", [])
                    img_data["ocr_text"] = analysis.get("ocr_text", "")
                    img_data["suggested_usage"] = analysis.get("suggested_usage", "")
                    img_data["tags"] = analysis.get("key_information", [])[:10]
                    img_data["is_informative"] = analysis.get("is_informative", True)
                    img_data["analysis_status"] = ImageAnalysisStatus.COMPLETED.value

                    # Anonymize OCR text using existing mappings
                    ocr_text = img_data.get("ocr_text", "")
                    if ocr_text:
                        try:
                            async with TaskSession() as db:
                                anon_ocr = await AnonymizationService.anonymize_text(
                                    ocr_text, uuid.UUID(project_id), db,
                                )
                                await db.commit()
                            img_data["anonymized_ocr_text"] = anon_ocr
                        except Exception:
                            img_data["anonymized_ocr_text"] = ""

                    # Build the anonymized description (what Mistral will see)
                    img_data["anonymized_description"] = ImageAnalysisService.build_anonymized_description(
                        analysis, img_data.get("anonymized_ocr_text", ""),
                    )

                # Filter out non-informative images (decorative)
                informative_count = sum(1 for img in images_data if img.get("is_informative", True))
                logger.info(
                    "[doc:%s] Image analysis done: %d/%d informative images",
                    document_id, informative_count, len(images_data),
                )

            except SoftTimeLimitExceeded:
                raise
            except Exception as vision_err:
                logger.warning(
                    "[doc:%s] Vision analysis failed (images saved without analysis): %s",
                    document_id, vision_err, exc_info=True,
                )
                # Non-fatal: images are still saved, just without analysis metadata
                for img_data in images_data:
                    img_data["analysis_status"] = ImageAnalysisStatus.FAILED.value

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
                    # Vision analysis fields
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

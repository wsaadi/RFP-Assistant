"""Celery tasks for document processing (upload, extraction, indexing)."""
import asyncio
import uuid

from ..celery_app import celery


@celery.task(name="tasks.process_document", bind=True, max_retries=2)
def process_document_task(self, document_id: str, project_id: str):
    """Celery wrapper — runs the async processing pipeline in its own event loop."""
    asyncio.run(_process_document_async(document_id, project_id))


async def _process_document_async(document_id: str, project_id: str):
    """Full document processing pipeline (async).

    Extracted from documents.py — logic is identical, just runs inside a
    Celery worker process instead of a FastAPI BackgroundTask.
    """
    from sqlalchemy import select
    from ..database import async_session
    from ..models.document import (
        Document, DocumentChunk, DocumentImage,
        FileType, ProcessingStatus,
    )
    from ..services.document_service import DocumentProcessor
    from ..services.vector_service import VectorService
    from ..services.anonymization_service import AnonymizationService
    from ..services.progress_service import ProgressTracker

    try:
        # ── Phase 1: Load document metadata + mark processing ──
        async with async_session() as db:
            result = await db.execute(
                select(Document).where(Document.id == uuid.UUID(document_id))
            )
            document = result.scalar_one_or_none()
            if not document:
                return

            ProgressTracker.start(document_id, document.original_filename)
            document.processing_status = ProcessingStatus.PROCESSING
            await db.commit()

            file_path = document.file_path
            file_type = document.file_type
            original_filename = document.original_filename
            category_value = document.category.value

        # ── Phase 2: File I/O + text extraction + chunking (CPU-bound) ──
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
                    print(f"DOC conversion/parsing failed: {doc_err}")
                    _text = ""

            elif file_type == FileType.DOCX:
                try:
                    _text, _sections = DocumentProcessor.extract_text_from_docx(file_content)
                    _page_count = max(1, len(_text.split()) // 300)
                    ProgressTracker.update(document_id, "extracting_images")
                    _images_data = DocumentProcessor.extract_images_from_docx(file_content, document_id)
                except (ValueError, Exception) as docx_err:
                    print(f"DOCX parsing failed: {docx_err}")
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

        # In a Celery worker, we're already in a separate process, so we can
        # run CPU-bound work directly (no need for to_thread).
        # But we still use to_thread to keep the async event loop free for
        # DB calls that happen during anonymization.
        text, pages_data, images_data, page_count, chunks = await asyncio.to_thread(
            _extract_and_chunk
        )

        if text is None:
            ProgressTracker.fail(document_id, "Aucun texte extrait du document")
            async with async_session() as db:
                result = await db.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                doc = result.scalar_one()
                doc.processing_status = ProcessingStatus.FAILED
                await db.commit()
            return

        # ── Phase 3: Anonymize + save everything ──
        ProgressTracker.update(document_id, "anonymizing")
        async with async_session() as db:
            chunk_texts = [c["content"] for c in chunks]
            anonymized_texts = await AnonymizationService.anonymize_chunks_batch(
                chunk_texts, uuid.UUID(project_id), db
            )
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
            await asyncio.to_thread(VectorService.index_chunks, project_id, vector_chunks)

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
                )
                db.add(db_image)

            # Reuse mappings already created by anonymize_chunks_batch
            # instead of running GLiNER again on the full text (which would
            # double processing time and risk hitting Celery time limits).
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

    except Exception as e:
        import traceback
        print(f"Error processing document {document_id}: {e}")
        traceback.print_exc()
        ProgressTracker.fail(document_id, str(e))
        # Try to mark the document as FAILED in the database.
        # Use multiple attempts with fresh sessions to handle transient
        # DB issues that could otherwise leave the document stuck forever.
        for _attempt in range(3):
            try:
                async with async_session() as db:
                    result = await db.execute(
                        select(Document).where(Document.id == uuid.UUID(document_id))
                    )
                    document = result.scalar_one_or_none()
                    if document and document.processing_status != ProcessingStatus.FAILED:
                        document.processing_status = ProcessingStatus.FAILED
                        await db.commit()
                break  # success
            except Exception as db_err:
                print(f"Failed to mark document {document_id} as FAILED (attempt {_attempt + 1}): {db_err}")
                await asyncio.sleep(1)

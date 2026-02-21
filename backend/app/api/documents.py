"""Document API routes for upload, processing, and search."""
import uuid
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db, async_session
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.document import (
    Document, DocumentChunk, DocumentImage,
    DocumentCategory, FileType, ProcessingStatus,
)
from ..schemas.document import DocumentOut, DocumentImageOut, SearchRequest, SearchResult
from ..services.document_service import DocumentProcessor
from ..services.vector_service import VectorService
from ..services.anonymization_service import AnonymizationService
from ..services.ai_service import MistralAIService
from ..services.progress_service import ProgressTracker
from ..config import settings
from .deps import get_current_user

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "pptx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


async def process_document_background(document_id: str, project_id: str):
    """Background task to process an uploaded document."""
    async with async_session() as db:
        try:
            result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
            document = result.scalar_one_or_none()
            if not document:
                return

            ProgressTracker.start(document_id, document.original_filename)
            document.processing_status = ProcessingStatus.PROCESSING
            await db.commit()

            # Read file content
            with open(document.file_path, "rb") as f:
                file_content = f.read()

            # Extract text based on file type
            text = ""
            pages_data = None
            images_data = []

            ProgressTracker.update(document_id, "extracting_text")

            if document.file_type == FileType.PDF:
                text, page_count, pages_data = DocumentProcessor.extract_text_from_pdf(file_content)
                document.page_count = page_count
                ProgressTracker.update(document_id, "extracting_images")
                images_data = DocumentProcessor.extract_images_from_pdf(file_content, document_id)

            elif document.file_type == FileType.DOC:
                # Convert .doc to .docx via LibreOffice, then process as DOCX
                try:
                    docx_content = DocumentProcessor.convert_doc_to_docx(file_content)
                    text, sections = DocumentProcessor.extract_text_from_docx(docx_content)
                    document.page_count = max(1, len(text.split()) // 300)
                    ProgressTracker.update(document_id, "extracting_images")
                    images_data = DocumentProcessor.extract_images_from_docx(docx_content, document_id)
                except Exception as doc_err:
                    print(f"DOC conversion/parsing failed: {doc_err}")
                    text = ""

            elif document.file_type == FileType.DOCX:
                try:
                    text, sections = DocumentProcessor.extract_text_from_docx(file_content)
                    document.page_count = max(1, len(text.split()) // 300)
                    ProgressTracker.update(document_id, "extracting_images")
                    images_data = DocumentProcessor.extract_images_from_docx(file_content, document_id)
                except (ValueError, Exception) as docx_err:
                    print(f"DOCX parsing failed: {docx_err}")
                    text = ""

            elif document.file_type in (FileType.XLSX, FileType.XLS):
                text = DocumentProcessor.extract_text_from_excel(file_content)
                document.page_count = 1

            if not text.strip():
                ProgressTracker.fail(document_id, "Aucun texte extrait du document")
                document.processing_status = ProcessingStatus.FAILED
                await db.commit()
                return

            # Create chunks
            ProgressTracker.update(document_id, "chunking")
            chunks = DocumentProcessor.create_chunks(
                text=text,
                document_id=document_id,
                document_name=document.original_filename,
                category=document.category.value,
                pages_data=pages_data,
            )

            # Anonymize chunks in batch (single NER pass + single DB round-trip)
            ProgressTracker.update(document_id, "anonymizing")
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

            # Index anonymized chunks in vector DB
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
            VectorService.index_chunks(project_id, vector_chunks)

            # Store extracted images
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

            # Try to describe images with AI if config available
            try:
                config_result = await db.execute(
                    select(AIConfig)
                    .join(RFPProject, RFPProject.workspace_id == AIConfig.workspace_id)
                    .where(RFPProject.id == uuid.UUID(project_id))
                )
                ai_config = config_result.scalar_one_or_none()
                if ai_config and ai_config.mistral_api_key_encrypted:
                    ai_service = MistralAIService.from_config(ai_config, ai_config.mistral_api_key_encrypted)
                    for db_image_obj in []:  # Skip for now, can be enabled later
                        desc = await ai_service.describe_image(
                            db_image_obj.stored_filename, db_image_obj.context
                        )
                        db_image_obj.description = desc.get("description", "")
                        db_image_obj.tags = desc.get("tags", [])
            except Exception:
                pass

            document.chunk_count = len(chunks)
            document.processing_status = ProcessingStatus.COMPLETED
            ProgressTracker.update(document_id, "completed")
            await db.commit()

        except Exception as e:
            print(f"Error processing document {document_id}: {e}")
            ProgressTracker.fail(document_id, str(e))
            try:
                result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
                document = result.scalar_one_or_none()
                if document:
                    document.processing_status = ProcessingStatus.FAILED
                    await db.commit()
            except Exception:
                pass


@router.post("/upload/{project_id}", response_model=DocumentOut)
async def upload_document(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    category: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to a project."""
    # Validate project exists
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nom de fichier manquant")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Type de fichier non supporté. Extensions autorisées: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Validate category
    try:
        doc_category = DocumentCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Catégorie invalide. Valeurs: old_rfp, old_response, new_rfp",
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 50MB)")

    # Save file
    filepath = DocumentProcessor.save_uploaded_file(content, str(project_id), file.filename)
    file_type = DocumentProcessor.detect_file_type(file.filename)

    # Create document record
    document = Document(
        project_id=project_id,
        category=doc_category,
        original_filename=file.filename,
        stored_filename=os.path.basename(filepath),
        file_type=file_type,
        file_size=len(content),
        file_path=filepath,
        uploaded_by=current_user.id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Start background processing
    background_tasks.add_task(
        process_document_background, str(document.id), str(project_id)
    )

    return DocumentOut(
        id=str(document.id),
        project_id=str(document.project_id),
        category=document.category.value,
        original_filename=document.original_filename,
        file_type=document.file_type.value,
        file_size=document.file_size,
        processing_status=document.processing_status.value,
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        uploaded_by=str(document.uploaded_by),
        created_at=document.created_at,
    )


@router.get("/project/{project_id}", response_model=list[DocumentOut])
async def list_documents(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in a project."""
    result = await db.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.category, Document.created_at)
    )
    documents = result.scalars().all()

    return [
        DocumentOut(
            id=str(d.id),
            project_id=str(d.project_id),
            category=d.category.value,
            original_filename=d.original_filename,
            file_type=d.file_type.value,
            file_size=d.file_size,
            processing_status=d.processing_status.value,
            page_count=d.page_count,
            chunk_count=d.chunk_count,
            uploaded_by=str(d.uploaded_by),
            created_at=d.created_at,
        )
        for d in documents
    ]


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its chunks."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    # Remove from vector DB
    VectorService.delete_document_chunks(str(document.project_id), str(document_id))

    # Delete file from disk
    if document.file_path and os.path.exists(document.file_path):
        os.remove(document.file_path)

    await db.delete(document)
    await db.commit()


@router.get("/{document_id}/images", response_model=list[DocumentImageOut])
async def list_document_images(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List images extracted from a document."""
    result = await db.execute(
        select(DocumentImage)
        .where(DocumentImage.document_id == document_id)
        .order_by(DocumentImage.page_number)
    )
    images = result.scalars().all()

    return [
        DocumentImageOut(
            id=str(img.id),
            document_id=str(img.document_id),
            stored_filename=img.stored_filename,
            description=img.description,
            page_number=img.page_number,
            context=img.context,
            tags=img.tags or [],
            width=img.width,
            height=img.height,
        )
        for img in images
    ]


@router.get("/images/{project_id}", response_model=list[DocumentImageOut])
async def list_project_images(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all images across all documents in a project."""
    result = await db.execute(
        select(DocumentImage)
        .join(Document, Document.id == DocumentImage.document_id)
        .where(Document.project_id == project_id)
        .order_by(Document.category, DocumentImage.page_number)
    )
    images = result.scalars().all()

    return [
        DocumentImageOut(
            id=str(img.id),
            document_id=str(img.document_id),
            stored_filename=img.stored_filename,
            description=img.description,
            page_number=img.page_number,
            context=img.context,
            tags=img.tags or [],
            width=img.width,
            height=img.height,
        )
        for img in images
    ]


@router.get("/image-file/{image_id}")
async def get_image_file(
    image_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve an image file."""
    result = await db.execute(select(DocumentImage).where(DocumentImage.id == image_id))
    image = result.scalar_one_or_none()
    if not image or not os.path.exists(image.file_path):
        raise HTTPException(status_code=404, detail="Image non trouvée")

    return FileResponse(image.file_path)


@router.post("/search/{project_id}")
async def search_documents(
    project_id: uuid.UUID,
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search across indexed document chunks."""
    results = VectorService.search(
        str(project_id),
        request.query,
        top_k=request.top_k,
        category_filter=request.category,
    )

    return {
        "success": True,
        "results": [
            SearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                document_name=r["document_name"],
                category=r["category"],
                page_number=r["page_number"],
                score=r["score"],
            )
            for r in results
        ],
    }


@router.get("/progress/{project_id}")
async def get_processing_progress(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get processing progress for all documents in a project."""
    result = await db.execute(
        select(Document.id).where(
            Document.project_id == project_id,
            Document.processing_status.in_([ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]),
        )
    )
    doc_ids = [str(row[0]) for row in result.all()]
    progress_list = ProgressTracker.get_for_project(doc_ids)
    return {"progress": progress_list}

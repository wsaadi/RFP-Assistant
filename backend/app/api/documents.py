"""Document API routes for upload, processing, and search."""
import uuid
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject
from ..models.document import (
    Document, DocumentChunk, DocumentImage,
    DocumentCategory, FileType, ProcessingStatus,
)
from ..schemas.document import DocumentOut, DocumentImageOut, SearchRequest, SearchResult
from ..services.document_service import DocumentProcessor
from ..services.vector_service import VectorService
from ..services.progress_service import ProgressTracker
from ..config import settings
from .deps import get_current_user

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "pptx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload/{project_id}", response_model=DocumentOut)
async def upload_document(
    project_id: uuid.UUID,
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
        valid = ", ".join(c.value for c in DocumentCategory)
        raise HTTPException(
            status_code=400,
            detail=f"Catégorie invalide. Valeurs: {valid}",
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

    # Dispatch processing to Celery worker
    from ..tasks.document_tasks import process_document_task
    process_document_task.delay(str(document.id), str(project_id))

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
        select(
            Document.id,
            Document.original_filename,
            Document.processing_status,
            Document.created_at,
        ).where(
            Document.project_id == project_id,
            Document.processing_status.in_([ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]),
        )
    )
    rows = result.all()
    if not rows:
        return {"progress": []}

    doc_ids = [str(row[0]) for row in rows]
    progress_list = ProgressTracker.get_for_project(doc_ids)

    # Build a set of document IDs that have Redis progress entries
    tracked_ids = {p["document_id"] for p in progress_list if "document_id" in p}

    # For documents in PROCESSING/PENDING state without Redis progress
    # (e.g. Redis key expired, worker crashed), detect stalled processing
    # and auto-mark as FAILED so the user isn't stuck forever.
    now = datetime.now(timezone.utc)
    # Beyond the Celery hard time limit (15 min) + margin, the task is dead.
    stall_threshold = timedelta(minutes=20)

    for row in rows:
        doc_id_str = str(row[0])
        if doc_id_str not in tracked_ids:
            age = now - row[3] if row[3] else timedelta(0)
            if age > stall_threshold:
                # Task is certainly dead — auto-mark as FAILED in the DB
                doc_result = await db.execute(
                    select(Document).where(Document.id == row[0])
                )
                doc = doc_result.scalar_one_or_none()
                if doc:
                    doc.processing_status = ProcessingStatus.FAILED
                    await db.commit()
                progress_list.append({
                    "document_id": doc_id_str,
                    "filename": row[1],
                    "step": "failed",
                    "step_label": "Traitement interrompu — veuillez relancer",
                    "progress": -1,
                })
            else:
                progress_list.append({
                    "document_id": doc_id_str,
                    "filename": row[1],
                    "step": "stalled",
                    "step_label": "Traitement interrompu",
                    "progress": -1,
                })

    return {"progress": progress_list}

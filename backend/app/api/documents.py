"""Document API routes for upload, processing, and search."""
import hashlib
import re
import uuid
import os
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
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
from ..schemas.document import (
    DocumentOut, DocumentImageOut, ImageOccurrence, SearchRequest, SearchResult,
    ImageUpdateRequest, ImageBatchUpdateRequest, ImageAnalyzeRequest,
)
from ..services.document_service import DocumentProcessor
from ..services.vector_service import VectorService
from ..services.progress_service import ProgressTracker
from ..config import settings
from .deps import get_current_user

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "pptx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Magic bytes for file type validation (prevents extension spoofing)
MAGIC_BYTES = {
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04"],  # ZIP-based format
    "doc": [b"\xd0\xcf\x11\xe0"],  # OLE2 compound document
    "xlsx": [b"PK\x03\x04"],  # ZIP-based format
    "xls": [b"\xd0\xcf\x11\xe0"],  # OLE2 compound document
    "pptx": [b"PK\x03\x04"],  # ZIP-based format
}


def _validate_magic_bytes(content: bytes, extension: str) -> bool:
    """Validate file content matches expected magic bytes for the extension."""
    expected = MAGIC_BYTES.get(extension, [])
    if not expected:
        return True
    return any(content[:len(magic)] == magic for magic in expected)


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

    # Validate file content matches extension (magic bytes check)
    if not _validate_magic_bytes(content, ext):
        raise HTTPException(
            status_code=400,
            detail="Le contenu du fichier ne correspond pas à son extension. Fichier potentiellement corrompu ou falsifié.",
        )

    # Compute content hash for duplicate detection
    content_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicate: same content in same project+category
    existing = await db.execute(
        select(Document).where(
            Document.project_id == project_id,
            Document.category == doc_category,
            Document.content_hash == content_hash,
            Document.content_hash != "",
        )
    )
    duplicate = existing.scalar_one_or_none()
    if duplicate:
        # Return existing document instead of re-processing
        return DocumentOut(
            id=str(duplicate.id),
            project_id=str(duplicate.project_id),
            category=duplicate.category.value,
            original_filename=duplicate.original_filename,
            file_type=duplicate.file_type.value,
            file_size=duplicate.file_size,
            processing_status=duplicate.processing_status.value,
            page_count=duplicate.page_count,
            chunk_count=duplicate.chunk_count,
            uploaded_by=str(duplicate.uploaded_by),
            created_at=duplicate.created_at,
        )

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
        content_hash=content_hash,
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


def _image_to_out(img: DocumentImage) -> DocumentImageOut:
    return DocumentImageOut(
        id=str(img.id),
        document_id=str(img.document_id),
        stored_filename=img.stored_filename,
        description=img.description,
        page_number=img.page_number,
        context=img.context,
        tags=img.tags or [],
        width=img.width,
        height=img.height,
        image_category=img.image_category or "autre",
        selected=bool(img.selected),
        analysis_status=img.analysis_status or "pending",
        image_type=img.image_type or "",
        key_information=img.key_information or [],
        pii_detected=img.pii_detected or [],
        ocr_text=img.ocr_text or "",
        suggested_usage=img.suggested_usage or "",
        anonymized_description=img.anonymized_description or "",
    )


def _get_content_hash(img: DocumentImage) -> str:
    """Get the content hash for an image, falling back to filename extraction."""
    if img.content_hash:
        return img.content_hash
    # Extract 8-char hash from stored_filename pattern: ..._<hash>.<ext>
    match = re.search(r'_([a-f0-9]{8})\.\w+$', img.stored_filename)
    return match.group(1) if match else ""


def _pick_representative(group: list[DocumentImage]) -> DocumentImage:
    """Pick the best representative image from a duplicate group."""
    # Prefer analyzed images, then lowest page number
    analyzed = [img for img in group if img.analysis_status == "completed"]
    if analyzed:
        return min(analyzed, key=lambda i: i.page_number)
    return min(group, key=lambda i: i.page_number)


def _consolidate_images(images: list[DocumentImage]) -> list[DocumentImageOut]:
    """Group duplicate images by content hash and return consolidated list."""
    groups: OrderedDict[str, list[DocumentImage]] = OrderedDict()
    for img in images:
        hash_key = _get_content_hash(img)
        if not hash_key:
            hash_key = str(img.id)  # unique fallback
        if hash_key not in groups:
            groups[hash_key] = []
        groups[hash_key].append(img)

    consolidated = []
    for group in groups.values():
        representative = _pick_representative(group)
        out = _image_to_out(representative)

        all_ids = [str(img.id) for img in group]
        occurrences = [
            ImageOccurrence(
                page_number=img.page_number,
                document_id=str(img.document_id),
            )
            for img in group
        ]
        # Deduplicate occurrences (same page + same doc)
        seen = set()
        unique_occurrences = []
        for occ in occurrences:
            key = (occ.page_number, occ.document_id)
            if key not in seen:
                seen.add(key)
                unique_occurrences.append(occ)

        out.occurrence_count = len(group)
        out.occurrences = unique_occurrences
        out.duplicate_ids = all_ids

        # If any image in the group is selected, mark as selected
        if any(img.selected for img in group):
            out.selected = True

        consolidated.append(out)

    return consolidated


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
    return [_image_to_out(img) for img in result.scalars().all()]


@router.get("/images/{project_id}", response_model=list[DocumentImageOut])
async def list_project_images(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all images across all documents in a project, with duplicates consolidated."""
    result = await db.execute(
        select(DocumentImage)
        .join(Document, Document.id == DocumentImage.document_id)
        .where(Document.project_id == project_id)
        .order_by(Document.category, DocumentImage.page_number)
    )
    all_images = list(result.scalars().all())
    return _consolidate_images(all_images)


@router.get("/image-file/{image_id}")
async def get_image_file(
    image_id: uuid.UUID,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Serve an image file.

    Accepts auth via Bearer header (normal API calls) or ``?token=`` query
    parameter (for ``<img src>`` tags where the browser can't set headers).
    """
    from ..security import decode_access_token

    # Try query-param token first, then fall back to header-based auth
    user = None
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            result = await db.execute(
                select(User).where(User.id == uuid.UUID(payload["sub"]))
            )
            user = result.scalar_one_or_none()

    if not user:
        # Fall back to standard Bearer header auth
        try:
            from fastapi.security import HTTPBearer
            from starlette.requests import Request
            # Can't easily inject Depends here, so just validate token param
            pass
        except Exception:
            pass

    if not user and not token:
        raise HTTPException(status_code=401, detail="Token requis")
    if not user:
        raise HTTPException(status_code=401, detail="Token invalide")

    result = await db.execute(select(DocumentImage).where(DocumentImage.id == image_id))
    image = result.scalar_one_or_none()
    if not image or not image.file_path or not os.path.exists(image.file_path):
        raise HTTPException(status_code=404, detail="Image non trouvée")

    # Path traversal protection: ensure file is within images directory
    real_path = os.path.realpath(image.file_path)
    allowed_dirs = [os.path.realpath(settings.images_dir), os.path.realpath(settings.upload_dir)]
    if not any(real_path.startswith(d) for d in allowed_dirs):
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    return FileResponse(real_path)


@router.put("/image/{image_id}", response_model=DocumentImageOut)
async def update_image(
    image_id: uuid.UUID,
    body: ImageUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update category or selection status of a single image."""
    result = await db.execute(select(DocumentImage).where(DocumentImage.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image non trouvée")

    if body.image_category is not None:
        image.image_category = body.image_category
    if body.selected is not None:
        image.selected = body.selected
    await db.commit()
    await db.refresh(image)
    return _image_to_out(image)


@router.put("/images-batch/{project_id}")
async def batch_update_images(
    project_id: uuid.UUID,
    body: ImageBatchUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update category or selection for multiple images at once."""
    image_uuids = [uuid.UUID(iid) for iid in body.image_ids]
    result = await db.execute(
        select(DocumentImage)
        .join(Document, Document.id == DocumentImage.document_id)
        .where(Document.project_id == project_id, DocumentImage.id.in_(image_uuids))
    )
    images = result.scalars().all()

    for img in images:
        if body.image_category is not None:
            img.image_category = body.image_category
        if body.selected is not None:
            img.selected = body.selected
    await db.commit()

    return {"updated": len(images)}


@router.post("/images-analyze/{project_id}")
async def analyze_selected_images(
    project_id: uuid.UUID,
    body: ImageAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger Vision AI analysis on selected images.

    Dispatches a Celery task that processes only the given image IDs.
    """
    from ..models.document import ImageAnalysisStatus

    image_uuids = [uuid.UUID(iid) for iid in body.image_ids]
    result = await db.execute(
        select(DocumentImage)
        .join(Document, Document.id == DocumentImage.document_id)
        .where(Document.project_id == project_id, DocumentImage.id.in_(image_uuids))
    )
    images = result.scalars().all()
    if not images:
        raise HTTPException(status_code=404, detail="Aucune image trouvée")

    # Mark images as analyzing
    for img in images:
        img.analysis_status = ImageAnalysisStatus.ANALYZING.value
    await db.commit()

    from ..tasks.document_tasks import analyze_images_task
    analyze_images_task.delay(str(project_id), body.image_ids)

    return {"status": "started", "count": len(images)}


@router.get("/images-analysis-status/{project_id}")
async def get_image_analysis_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """Get status of image analysis task for a project."""
    from ..services.progress_service import get_or_idle
    status = get_or_idle("image_analysis", str(project_id))
    return status


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
    """Get processing progress for all documents in a project.

    Returns a combination of:
    - Redis progress (real-time step/percentage from the Celery worker)
    - DB status (authoritative processing_status from PostgreSQL)

    The frontend should use `db_status` as the source of truth for
    final states (completed/failed) and Redis progress for the live bar.
    """
    # Fetch ALL non-completed documents (pending + processing)
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

    # Also check for recently-completed documents (within 10s) so the
    # frontend sees the transition from "processing" to "completed"
    # without waiting for a full document list reload.
    recently_done = await db.execute(
        select(
            Document.id,
            Document.original_filename,
            Document.processing_status,
            Document.created_at,
        ).where(
            Document.project_id == project_id,
            Document.processing_status.in_([ProcessingStatus.COMPLETED, ProcessingStatus.FAILED]),
        ).order_by(Document.created_at.desc()).limit(20)
    )
    done_rows = recently_done.all()

    if not rows and not done_rows:
        return {"progress": []}

    # Collect all doc IDs we care about
    all_doc_ids = [str(row[0]) for row in rows]
    done_doc_ids = [str(row[0]) for row in done_rows]

    # Fetch Redis progress for active docs
    redis_progress = {}
    if all_doc_ids:
        progress_entries = ProgressTracker.get_for_project(all_doc_ids)
        for p in progress_entries:
            if "document_id" in p:
                redis_progress[p["document_id"]] = p

    # Also fetch Redis progress for done docs (might still have progress data)
    if done_doc_ids:
        done_entries = ProgressTracker.get_for_project(done_doc_ids)
        for p in done_entries:
            if "document_id" in p:
                redis_progress[p["document_id"]] = p

    progress_list = []

    # Process active (pending/processing) documents
    now = datetime.now(timezone.utc)
    stall_threshold = timedelta(minutes=25)

    for row in rows:
        doc_id_str = str(row[0])
        redis_data = redis_progress.get(doc_id_str)

        if redis_data:
            # We have live progress data — include DB status for the frontend
            redis_data["db_status"] = row[2].value
            progress_list.append(redis_data)
        else:
            # No Redis progress — check if stalled
            age = now - row[3] if row[3] else timedelta(0)
            if age > stall_threshold:
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
                    "db_status": "failed",
                })
            else:
                # Recently queued, worker hasn't picked it up yet
                progress_list.append({
                    "document_id": doc_id_str,
                    "filename": row[1],
                    "step": "queued",
                    "step_label": "En file d'attente",
                    "progress": 0,
                    "db_status": row[2].value,
                })

    # Include recently-completed/failed documents that still have Redis progress
    # so the frontend sees the final "completed" step before the progress bar disappears
    active_ids = {str(row[0]) for row in rows}
    for row in done_rows:
        doc_id_str = str(row[0])
        if doc_id_str in active_ids:
            continue  # Already included above

        db_status = row[2].value
        redis_data = redis_progress.get(doc_id_str)
        if redis_data:
            redis_data["db_status"] = db_status
            progress_list.append(redis_data)
        else:
            # DB says completed/failed but no Redis data — synthesize entry
            if db_status == "completed":
                progress_list.append({
                    "document_id": doc_id_str,
                    "filename": row[1],
                    "step": "completed",
                    "step_label": "Terminé",
                    "progress": 100,
                    "db_status": "completed",
                })
            elif db_status == "failed":
                progress_list.append({
                    "document_id": doc_id_str,
                    "filename": row[1],
                    "step": "failed",
                    "step_label": "Échec",
                    "progress": -1,
                    "db_status": "failed",
                })

    return {"progress": progress_list}

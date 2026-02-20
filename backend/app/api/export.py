"""Export/Import API routes."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.user import User
from ..models.project import RFPProject, AIConfig
from ..models.chapter import Chapter
from ..models.document import Document, DocumentImage
from ..services.word_service import RFPWordService
from ..services.export_service import ExportService
from ..services.anonymization_service import AnonymizationService
from .deps import get_current_user

router = APIRouter(prefix="/export", tags=["Export/Import"])


@router.post("/{project_id}/word")
async def export_word(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export project as a professional Word document."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # Get all chapters ordered
    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order)
    )
    all_chapters = chapters_result.scalars().all()

    # Build tree structure for Word generation
    chapter_map = {c.id: c for c in all_chapters}
    children_map = {}
    root_chapters = []

    for c in all_chapters:
        if c.parent_id:
            children_map.setdefault(c.parent_id, []).append(c)
        else:
            root_chapters.append(c)

    # Get images for chapters
    doc_ids = []
    docs_result = await db.execute(
        select(Document).where(Document.project_id == project_id)
    )
    docs = docs_result.scalars().all()
    doc_ids = [d.id for d in docs]

    images_by_doc = {}
    if doc_ids:
        img_result = await db.execute(
            select(DocumentImage).where(DocumentImage.document_id.in_(doc_ids))
        )
        for img in img_result.scalars().all():
            images_by_doc.setdefault(str(img.document_id), []).append({
                "file_path": img.file_path,
                "description": img.description,
                "tags": img.tags or [],
            })

    def build_chapter_data(chapter: Chapter) -> dict:
        children = children_map.get(chapter.id, [])
        # Deanonymized content is already stored in chapter.content
        return {
            "title": chapter.title,
            "content": chapter.content or "",
            "chapter_type": chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
            "numbering": chapter.numbering,
            "images": chapter.image_references or [],
            "children": [
                build_chapter_data(child) for child in sorted(children, key=lambda x: x.order)
            ],
        }

    chapters_data = [build_chapter_data(c) for c in root_chapters]

    file_stream = await RFPWordService.generate_full_document(
        project_name=project.name,
        client_name=project.client_name,
        rfp_reference=project.rfp_reference,
        chapters=chapters_data,
    )

    filename = f"reponse_ao_{project.rfp_reference or project.name}.docx"
    filename = filename.replace(" ", "_").replace("/", "_")

    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{project_id}/backup")
async def export_project_backup(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export complete project as a ZIP backup."""
    try:
        zip_buffer = await ExportService.export_project(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one()

    filename = f"backup_{project.name}_{project.rfp_reference or 'export'}.zip"
    filename = filename.replace(" ", "_").replace("/", "_")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/import/{workspace_id}")
async def import_project_backup(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a project from a ZIP backup."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Fichier ZIP requis")

    content = await file.read()

    try:
        project = await ExportService.import_project(
            db, content, workspace_id, current_user.id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur d'import: {str(e)}")

    return {
        "success": True,
        "project_id": str(project.id),
        "project_name": project.name,
        "message": "Projet importé avec succès",
    }


@router.get("/{project_id}/preview")
async def preview_document(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a full preview of the document content."""
    result = await db.execute(select(RFPProject).where(RFPProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.order)
    )
    all_chapters = chapters_result.scalars().all()

    # Build tree
    children_map = {}
    root_chapters = []
    for c in all_chapters:
        if c.parent_id:
            children_map.setdefault(c.parent_id, []).append(c)
        else:
            root_chapters.append(c)

    def build_preview(chapter, level=1, prefix=""):
        numbering = f"{prefix}" if prefix else ""
        children = children_map.get(chapter.id, [])
        return {
            "id": str(chapter.id),
            "title": chapter.title,
            "numbering": numbering,
            "level": level,
            "content": chapter.content or "",
            "status": chapter.status.value if hasattr(chapter.status, 'value') else str(chapter.status),
            "chapter_type": chapter.chapter_type.value if hasattr(chapter.chapter_type, 'value') else str(chapter.chapter_type),
            "children": [
                build_preview(child, level + 1, f"{numbering}.{i+1}" if numbering else str(i+1))
                for i, child in enumerate(sorted(children, key=lambda x: x.order))
            ],
        }

    preview = {
        "project_name": project.name,
        "client_name": project.client_name,
        "rfp_reference": project.rfp_reference,
        "chapters": [
            build_preview(c, 1, str(i+1))
            for i, c in enumerate(root_chapters)
        ],
    }

    return preview

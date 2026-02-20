"""Export/Import service for workspace data backup and restore."""
import io
import json
import os
import uuid
import zipfile
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.project import RFPProject, AnonymizationMapping
from ..models.document import Document, DocumentChunk, DocumentImage
from ..models.chapter import Chapter
from ..config import settings


class ExportService:
    """Service for exporting and importing workspace/project data."""

    @staticmethod
    async def export_project(
        db: AsyncSession, project_id: uuid.UUID
    ) -> io.BytesIO:
        """Export a complete project as a ZIP archive.

        Includes:
        - Project metadata
        - All chapters with content
        - All documents (original files + extracted data)
        - All images
        - Anonymization mappings
        """
        # Load project with all relations
        result = await db.execute(
            select(RFPProject).where(RFPProject.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        # Load chapters
        result = await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.order)
        )
        chapters = result.scalars().all()

        # Load documents
        result = await db.execute(
            select(Document).where(Document.project_id == project_id)
        )
        documents = result.scalars().all()

        # Load anonymization mappings
        result = await db.execute(
            select(AnonymizationMapping).where(AnonymizationMapping.project_id == project_id)
        )
        mappings = result.scalars().all()

        # Load images
        doc_ids = [d.id for d in documents]
        images = []
        if doc_ids:
            result = await db.execute(
                select(DocumentImage).where(DocumentImage.document_id.in_(doc_ids))
            )
            images = result.scalars().all()

        # Build export data
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "project": {
                "name": project.name,
                "description": project.description,
                "client_name": project.client_name,
                "rfp_reference": project.rfp_reference,
                "deadline": project.deadline,
                "status": project.status.value if hasattr(project.status, 'value') else str(project.status),
                "improvement_axes": project.improvement_axes,
            },
            "chapters": [
                {
                    "id": str(c.id),
                    "parent_id": str(c.parent_id) if c.parent_id else None,
                    "title": c.title,
                    "description": c.description,
                    "order": c.order,
                    "chapter_type": c.chapter_type.value if hasattr(c.chapter_type, 'value') else str(c.chapter_type),
                    "content": c.content,
                    "status": c.status.value if hasattr(c.status, 'value') else str(c.status),
                    "notes": c.notes,
                    "improvement_axes": c.improvement_axes,
                    "source_references": c.source_references,
                    "image_references": c.image_references,
                    "rfp_requirement": c.rfp_requirement,
                    "is_prefilled": c.is_prefilled,
                    "numbering": c.numbering,
                }
                for c in chapters
            ],
            "documents": [
                {
                    "id": str(d.id),
                    "category": d.category.value if hasattr(d.category, 'value') else str(d.category),
                    "original_filename": d.original_filename,
                    "file_type": d.file_type.value if hasattr(d.file_type, 'value') else str(d.file_type),
                    "file_size": d.file_size,
                    "page_count": d.page_count,
                }
                for d in documents
            ],
            "anonymization_mappings": [
                {
                    "entity_type": m.entity_type.value if hasattr(m.entity_type, 'value') else str(m.entity_type),
                    "original_value": m.original_value,
                    "anonymized_value": m.anonymized_value,
                    "is_active": m.is_active,
                }
                for m in mappings
            ],
            "images": [
                {
                    "id": str(img.id),
                    "document_id": str(img.document_id),
                    "stored_filename": img.stored_filename,
                    "description": img.description,
                    "page_number": img.page_number,
                    "context": img.context,
                    "tags": img.tags,
                }
                for img in images
            ],
        }

        # Create ZIP archive
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add metadata
            zf.writestr("project.json", json.dumps(export_data, ensure_ascii=False, indent=2))

            # Add original document files
            for doc in documents:
                if doc.file_path and os.path.exists(doc.file_path):
                    arcname = f"documents/{doc.original_filename}"
                    zf.write(doc.file_path, arcname)

            # Add images
            for img in images:
                if img.file_path and os.path.exists(img.file_path):
                    arcname = f"images/{img.stored_filename}"
                    zf.write(img.file_path, arcname)

        zip_buffer.seek(0)
        return zip_buffer

    @staticmethod
    async def import_project(
        db: AsyncSession,
        zip_content: bytes,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> RFPProject:
        """Import a project from a ZIP archive.

        Returns the newly created project.
        """
        zip_buffer = io.BytesIO(zip_content)

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            # Read metadata
            project_data = json.loads(zf.read("project.json"))

            # Create project
            project_info = project_data["project"]
            new_project = RFPProject(
                workspace_id=workspace_id,
                name=project_info["name"],
                description=project_info.get("description", ""),
                client_name=project_info.get("client_name", ""),
                rfp_reference=project_info.get("rfp_reference", ""),
                deadline=project_info.get("deadline", ""),
                improvement_axes=project_info.get("improvement_axes", ""),
                created_by=user_id,
            )
            db.add(new_project)
            await db.flush()

            # Map old chapter IDs to new ones
            chapter_id_map = {}

            # Import chapters (first pass - create all without parent_id)
            for ch_data in project_data.get("chapters", []):
                old_id = ch_data["id"]
                new_chapter = Chapter(
                    project_id=new_project.id,
                    title=ch_data["title"],
                    description=ch_data.get("description", ""),
                    order=ch_data.get("order", 0),
                    chapter_type=ch_data.get("chapter_type", "chapter"),
                    content=ch_data.get("content", ""),
                    status=ch_data.get("status", "not_started"),
                    notes=ch_data.get("notes", []),
                    improvement_axes=ch_data.get("improvement_axes", []),
                    source_references=ch_data.get("source_references", []),
                    image_references=ch_data.get("image_references", []),
                    rfp_requirement=ch_data.get("rfp_requirement", ""),
                    is_prefilled=ch_data.get("is_prefilled", False),
                    numbering=ch_data.get("numbering", ""),
                )
                db.add(new_chapter)
                await db.flush()
                chapter_id_map[old_id] = new_chapter.id

            # Second pass - set parent_ids
            for ch_data in project_data.get("chapters", []):
                old_parent = ch_data.get("parent_id")
                if old_parent and old_parent in chapter_id_map:
                    old_id = ch_data["id"]
                    new_id = chapter_id_map[old_id]
                    result = await db.execute(
                        select(Chapter).where(Chapter.id == new_id)
                    )
                    chapter = result.scalar_one()
                    chapter.parent_id = chapter_id_map[old_parent]

            # Import anonymization mappings
            for m_data in project_data.get("anonymization_mappings", []):
                mapping = AnonymizationMapping(
                    project_id=new_project.id,
                    entity_type=m_data["entity_type"],
                    original_value=m_data["original_value"],
                    anonymized_value=m_data["anonymized_value"],
                    is_active=m_data.get("is_active", True),
                )
                db.add(mapping)

            # Extract document files
            project_dir = os.path.join(settings.upload_dir, str(new_project.id))
            os.makedirs(project_dir, exist_ok=True)

            for doc_data in project_data.get("documents", []):
                arcname = f"documents/{doc_data['original_filename']}"
                try:
                    file_content = zf.read(arcname)
                    stored_name = f"{uuid.uuid4().hex}_{doc_data['original_filename']}"
                    filepath = os.path.join(project_dir, stored_name)
                    with open(filepath, "wb") as f:
                        f.write(file_content)

                    new_doc = Document(
                        project_id=new_project.id,
                        category=doc_data["category"],
                        original_filename=doc_data["original_filename"],
                        stored_filename=stored_name,
                        file_type=doc_data.get("file_type", "other"),
                        file_size=doc_data.get("file_size", 0),
                        file_path=filepath,
                        processing_status="pending",
                        page_count=doc_data.get("page_count", 0),
                        uploaded_by=user_id,
                    )
                    db.add(new_doc)
                except KeyError:
                    continue

            # Extract images
            images_dir = os.path.join(settings.images_dir, str(new_project.id))
            os.makedirs(images_dir, exist_ok=True)

            for img_data in project_data.get("images", []):
                arcname = f"images/{img_data['stored_filename']}"
                try:
                    img_content = zf.read(arcname)
                    filepath = os.path.join(images_dir, img_data["stored_filename"])
                    with open(filepath, "wb") as f:
                        f.write(img_content)
                except KeyError:
                    continue

            await db.commit()
            return new_project

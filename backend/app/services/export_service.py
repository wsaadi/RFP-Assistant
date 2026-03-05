"""Export/Import service for workspace data backup and restore."""
import io
import json
import os
import uuid
import zipfile
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.project import RFPProject, AnonymizationMapping, ComplianceResult, GapAnalysisResult, ContentReuseResult
from ..models.document import Document, DocumentChunk, DocumentImage
from ..models.chapter import Chapter
from ..models.response_document import ResponseDocument
from ..config import settings


class ExportService:
    """Service for exporting and importing workspace/project data."""

    @staticmethod
    async def collect_project_data(
        db: AsyncSession, project_id: uuid.UUID
    ) -> Tuple[dict, list, list]:
        """Collect all project data from DB (async, non-blocking).

        Returns (export_data_dict, documents_with_paths, images_with_paths).
        """
        result = await db.execute(
            select(RFPProject).where(RFPProject.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        result = await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.order)
        )
        chapters = result.scalars().all()

        result = await db.execute(
            select(Document).where(Document.project_id == project_id)
        )
        documents = result.scalars().all()

        result = await db.execute(
            select(AnonymizationMapping).where(AnonymizationMapping.project_id == project_id)
        )
        mappings = result.scalars().all()

        doc_ids = [d.id for d in documents]
        images = []
        if doc_ids:
            result = await db.execute(
                select(DocumentImage).where(DocumentImage.document_id.in_(doc_ids))
            )
            images = result.scalars().all()

        # Fetch response documents (deliverables)
        result = await db.execute(
            select(ResponseDocument)
            .where(ResponseDocument.project_id == project_id)
            .order_by(ResponseDocument.order)
        )
        response_documents = result.scalars().all()

        # Fetch compliance results
        result = await db.execute(
            select(ComplianceResult)
            .where(ComplianceResult.project_id == project_id)
            .order_by(ComplianceResult.created_at)
        )
        compliance_results = result.scalars().all()

        # Fetch gap analysis results
        result = await db.execute(
            select(GapAnalysisResult)
            .where(GapAnalysisResult.project_id == project_id)
            .order_by(GapAnalysisResult.created_at)
        )
        gap_analysis_results = result.scalars().all()

        # Fetch content reuse results
        result = await db.execute(
            select(ContentReuseResult)
            .where(ContentReuseResult.project_id == project_id)
            .order_by(ContentReuseResult.created_at)
        )
        content_reuse_results = result.scalars().all()

        export_data = {
            "version": "2.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "project": {
                "name": project.name,
                "description": project.description,
                "client_name": project.client_name,
                "company_name": getattr(project, 'company_name', '') or '',
                "rfp_reference": project.rfp_reference,
                "deadline": project.deadline,
                "status": project.status.value if hasattr(project.status, 'value') else str(project.status),
                "improvement_axes": project.improvement_axes,
            },
            "chapters": [
                {
                    "id": str(c.id),
                    "parent_id": str(c.parent_id) if c.parent_id else None,
                    "response_document_id": str(c.response_document_id) if c.response_document_id else None,
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
                    "chunk_count": d.chunk_count,
                    "processing_status": d.processing_status if isinstance(d.processing_status, str) else (d.processing_status.value if hasattr(d.processing_status, 'value') else str(d.processing_status)),
                    "full_text": d.full_text or "",
                    "anonymized_full_text": d.anonymized_full_text or "",
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
                    "width": img.width,
                    "height": img.height,
                    "image_category": img.image_category,
                    "selected": img.selected,
                    "analysis_status": img.analysis_status,
                    "image_type": img.image_type,
                    "anonymized_description": img.anonymized_description,
                    "key_information": img.key_information,
                    "pii_detected": img.pii_detected,
                    "ocr_text": img.ocr_text,
                    "anonymized_ocr_text": img.anonymized_ocr_text,
                    "suggested_usage": img.suggested_usage,
                    "section_title": img.section_title,
                }
                for img in images
            ],
            "response_documents": [
                {
                    "id": str(rd.id),
                    "title": rd.title,
                    "description": rd.description,
                    "expected_format": rd.expected_format.value if hasattr(rd.expected_format, 'value') else str(rd.expected_format),
                    "content_type": rd.content_type.value if hasattr(rd.content_type, 'value') else str(rd.content_type),
                    "is_selected": rd.is_selected,
                    "order": rd.order,
                    "rfp_source": rd.rfp_source,
                    "fill_content": rd.fill_content,
                    "fill_status": rd.fill_status,
                }
                for rd in response_documents
            ],
            "compliance_results": [
                {
                    "score": cr.score,
                    "summary": cr.summary,
                    "covered_requirements": cr.covered_requirements,
                    "missing_elements": cr.missing_elements,
                    "recommendations": cr.recommendations,
                    "created_at": cr.created_at.isoformat() if cr.created_at else None,
                }
                for cr in compliance_results
            ],
            "gap_analysis_results": [
                {
                    "summary": gar.summary,
                    "new_requirements": gar.new_requirements,
                    "removed_requirements": gar.removed_requirements,
                    "modified_requirements": gar.modified_requirements,
                    "unchanged_requirements": gar.unchanged_requirements,
                    "created_at": gar.created_at.isoformat() if gar.created_at else None,
                }
                for gar in gap_analysis_results
            ],
            "content_reuse_results": [
                {
                    "has_old_response": crr.has_old_response,
                    "overall_reuse_percentage": crr.overall_reuse_percentage,
                    "chapters": crr.chapters,
                    "summary": crr.summary,
                    "created_at": crr.created_at.isoformat() if crr.created_at else None,
                }
                for crr in content_reuse_results
            ],
        }

        # Extract file paths (before DB session closes and ORM objects expire)
        doc_paths = [
            {"file_path": d.file_path, "original_filename": d.original_filename}
            for d in documents
        ]
        img_paths = [
            {"file_path": img.file_path, "stored_filename": img.stored_filename}
            for img in images
        ]

        return export_data, doc_paths, img_paths

    @staticmethod
    def create_zip_archive(
        export_data: dict,
        doc_paths: list,
        img_paths: list,
        progress_callback: Optional[Callable] = None,
    ) -> io.BytesIO:
        """Create ZIP archive from collected data (sync, runs in thread pool).

        progress_callback(step, progress_pct, message) if provided.
        """
        total_files = len(doc_paths) + len(img_paths)
        processed = 0

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", json.dumps(export_data, ensure_ascii=False, indent=2))

            for doc in doc_paths:
                if doc["file_path"] and os.path.exists(doc["file_path"]):
                    arcname = f"documents/{doc['original_filename']}"
                    zf.write(doc["file_path"], arcname)
                processed += 1
                if progress_callback and total_files > 0:
                    pct = 30 + int(60 * processed / total_files)
                    progress_callback("packaging", pct, f"Ajout des fichiers ({processed}/{total_files})...")

            for img in img_paths:
                if img["file_path"] and os.path.exists(img["file_path"]):
                    arcname = f"images/{img['stored_filename']}"
                    zf.write(img["file_path"], arcname)
                processed += 1
                if progress_callback and total_files > 0:
                    pct = 30 + int(60 * processed / total_files)
                    progress_callback("packaging", pct, f"Ajout des fichiers ({processed}/{total_files})...")

        zip_buffer.seek(0)
        return zip_buffer

    @staticmethod
    async def export_project(
        db: AsyncSession, project_id: uuid.UUID
    ) -> io.BytesIO:
        """Export a complete project as a ZIP archive (legacy method)."""
        export_data, doc_paths, img_paths = await ExportService.collect_project_data(db, project_id)
        return ExportService.create_zip_archive(export_data, doc_paths, img_paths)

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
                company_name=project_info.get("company_name", ""),
                rfp_reference=project_info.get("rfp_reference", ""),
                deadline=project_info.get("deadline", ""),
                improvement_axes=project_info.get("improvement_axes", ""),
                status=project_info.get("status", "draft"),
                created_by=user_id,
            )
            db.add(new_project)
            await db.flush()

            # Import response documents (deliverables) first, so chapters can reference them
            response_doc_id_map = {}
            for rd_data in project_data.get("response_documents", []):
                old_id = rd_data.get("id")
                new_rd = ResponseDocument(
                    project_id=new_project.id,
                    title=rd_data["title"],
                    description=rd_data.get("description", ""),
                    expected_format=rd_data.get("expected_format", "docx"),
                    content_type=rd_data.get("content_type", "redaction"),
                    is_selected=rd_data.get("is_selected", True),
                    order=rd_data.get("order", 0),
                    rfp_source=rd_data.get("rfp_source", ""),
                    fill_content=rd_data.get("fill_content", ""),
                    fill_status=rd_data.get("fill_status", "pending"),
                )
                db.add(new_rd)
                await db.flush()
                if old_id:
                    response_doc_id_map[old_id] = new_rd.id

            # Map old chapter IDs to new ones
            chapter_id_map = {}

            # Import chapters (first pass - create all without parent_id and response_document_id)
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

            # Second pass - set parent_ids and response_document_ids
            for ch_data in project_data.get("chapters", []):
                old_id = ch_data["id"]
                old_parent = ch_data.get("parent_id")
                old_rd_id = ch_data.get("response_document_id")
                needs_update = False

                if old_parent and old_parent in chapter_id_map:
                    needs_update = True
                if old_rd_id and old_rd_id in response_doc_id_map:
                    needs_update = True

                if needs_update:
                    new_id = chapter_id_map[old_id]
                    result = await db.execute(
                        select(Chapter).where(Chapter.id == new_id)
                    )
                    chapter = result.scalar_one()
                    if old_parent and old_parent in chapter_id_map:
                        chapter.parent_id = chapter_id_map[old_parent]
                    if old_rd_id and old_rd_id in response_doc_id_map:
                        chapter.response_document_id = response_doc_id_map[old_rd_id]

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

            # Extract document files and create DB records
            project_dir = os.path.join(settings.upload_dir, str(new_project.id))
            os.makedirs(project_dir, exist_ok=True)

            # Map old document IDs to new ones (needed for images)
            doc_id_map = {}

            for doc_data in project_data.get("documents", []):
                old_doc_id = doc_data.get("id")
                arcname = f"documents/{doc_data['original_filename']}"
                try:
                    file_content = zf.read(arcname)
                    stored_name = f"{uuid.uuid4().hex}_{doc_data['original_filename']}"
                    filepath = os.path.join(project_dir, stored_name)
                    with open(filepath, "wb") as f:
                        f.write(file_content)

                    # Use the backed-up processing status; default to completed for v2 backups
                    backup_version = project_data.get("version", "1.0")
                    if backup_version >= "2.0":
                        processing_status = doc_data.get("processing_status", "completed")
                    else:
                        processing_status = "pending"

                    new_doc = Document(
                        project_id=new_project.id,
                        category=doc_data["category"],
                        original_filename=doc_data["original_filename"],
                        stored_filename=stored_name,
                        file_type=doc_data.get("file_type", "other"),
                        file_size=doc_data.get("file_size", 0),
                        file_path=filepath,
                        processing_status=processing_status,
                        page_count=doc_data.get("page_count", 0),
                        chunk_count=doc_data.get("chunk_count", 0),
                        full_text=doc_data.get("full_text", ""),
                        anonymized_full_text=doc_data.get("anonymized_full_text", ""),
                        uploaded_by=user_id,
                    )
                    db.add(new_doc)
                    await db.flush()
                    if old_doc_id:
                        doc_id_map[old_doc_id] = new_doc.id
                except KeyError:
                    continue

            # Extract images and create DB records
            images_dir = os.path.join(settings.images_dir, str(new_project.id))
            os.makedirs(images_dir, exist_ok=True)

            # Map old image IDs to new ones (needed to remap chapter references)
            image_id_map: Dict[str, str] = {}

            for img_data in project_data.get("images", []):
                arcname = f"images/{img_data['stored_filename']}"
                try:
                    img_content = zf.read(arcname)
                    filepath = os.path.join(images_dir, img_data["stored_filename"])
                    with open(filepath, "wb") as f:
                        f.write(img_content)

                    # Map old document_id to new one
                    old_doc_id = img_data.get("document_id")
                    new_doc_id = doc_id_map.get(old_doc_id)
                    if not new_doc_id:
                        continue

                    old_img_id = img_data.get("id")
                    new_image = DocumentImage(
                        document_id=new_doc_id,
                        stored_filename=img_data["stored_filename"],
                        file_path=filepath,
                        description=img_data.get("description", ""),
                        page_number=img_data.get("page_number", 0),
                        context=img_data.get("context", ""),
                        tags=img_data.get("tags", []),
                        width=img_data.get("width", 0),
                        height=img_data.get("height", 0),
                        image_category=img_data.get("image_category", "autre"),
                        selected=img_data.get("selected", False),
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
                    db.add(new_image)
                    await db.flush()
                    if old_img_id:
                        image_id_map[old_img_id] = str(new_image.id)
                except KeyError:
                    continue

            # Remap image references in chapters (content and image_references)
            if image_id_map:
                for ch_data in project_data.get("chapters", []):
                    old_ch_id = ch_data["id"]
                    new_ch_id = chapter_id_map.get(old_ch_id)
                    if not new_ch_id:
                        continue

                    result = await db.execute(
                        select(Chapter).where(Chapter.id == new_ch_id)
                    )
                    chapter = result.scalar_one()
                    updated = False

                    # Remap [INSERT_IMAGE:old_uuid] markers in content
                    if chapter.content:
                        new_content = chapter.content
                        for old_id, new_id in image_id_map.items():
                            new_content = new_content.replace(
                                f"[INSERT_IMAGE:{old_id}]",
                                f"[INSERT_IMAGE:{new_id}]",
                            )
                        if new_content != chapter.content:
                            chapter.content = new_content
                            updated = True

                    # Remap image_id and file_path in image_references
                    if chapter.image_references:
                        new_refs = []
                        for ref in chapter.image_references:
                            old_ref_id = ref.get("image_id", "")
                            if old_ref_id in image_id_map:
                                ref = dict(ref)
                                ref["image_id"] = image_id_map[old_ref_id]
                                # Update file_path to point to new project images dir
                                if ref.get("file_path"):
                                    filename = os.path.basename(ref["file_path"])
                                    ref["file_path"] = os.path.join(images_dir, filename)
                            new_refs.append(ref)
                        chapter.image_references = new_refs
                        updated = True

            # Import compliance results
            for cr_data in project_data.get("compliance_results", []):
                cr = ComplianceResult(
                    project_id=new_project.id,
                    score=cr_data.get("score", 0),
                    summary=cr_data.get("summary", ""),
                    covered_requirements=cr_data.get("covered_requirements", []),
                    missing_elements=cr_data.get("missing_elements", []),
                    recommendations=cr_data.get("recommendations", []),
                )
                db.add(cr)

            # Import gap analysis results
            for gar_data in project_data.get("gap_analysis_results", []):
                gar = GapAnalysisResult(
                    project_id=new_project.id,
                    summary=gar_data.get("summary", ""),
                    new_requirements=gar_data.get("new_requirements", []),
                    removed_requirements=gar_data.get("removed_requirements", []),
                    modified_requirements=gar_data.get("modified_requirements", []),
                    unchanged_requirements=gar_data.get("unchanged_requirements", []),
                )
                db.add(gar)

            # Import content reuse results
            for crr_data in project_data.get("content_reuse_results", []):
                crr = ContentReuseResult(
                    project_id=new_project.id,
                    has_old_response=crr_data.get("has_old_response", False),
                    overall_reuse_percentage=crr_data.get("overall_reuse_percentage", 0.0),
                    chapters=crr_data.get("chapters", []),
                    summary=crr_data.get("summary", {}),
                )
                db.add(crr)

            await db.commit()
            return new_project

"""Document processing service: extraction, chunking, image extraction."""
import os
import io
import re
import uuid
import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from typing import List, Dict, Tuple, Optional

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from openpyxl import load_workbook
from PIL import Image

from ..config import settings


# Chunk size configuration (aligned with multilingual-e5-base 512 token limit)
CHUNK_SIZE = 350  # words
CHUNK_OVERLAP = 50  # words overlap between chunks


class DocumentProcessor:
    """Process documents: extract text, images, and create chunks."""

    @staticmethod
    def detect_file_type(filename: str) -> str:
        """Detect file type from extension."""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        type_map = {
            "pdf": "pdf",
            "docx": "docx",
            "doc": "doc",
            "xlsx": "xlsx",
            "xls": "xls",
            "pptx": "pptx",
        }
        return type_map.get(ext, "other")

    @staticmethod
    def convert_doc_to_docx(file_content: bytes) -> bytes:
        """Convert old .doc format to .docx using LibreOffice.

        Returns the .docx file content as bytes.
        Raises RuntimeError if conversion fails.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_path = os.path.join(tmpdir, "input.doc")
            with open(doc_path, "wb") as f:
                f.write(file_content)

            result = subprocess.run(
                [
                    "libreoffice", "--headless", "--norestore",
                    "--convert-to", "docx",
                    "--outdir", tmpdir,
                    doc_path,
                ],
                capture_output=True,
                timeout=120,
            )

            docx_path = os.path.join(tmpdir, "input.docx")
            if result.returncode != 0 or not os.path.exists(docx_path):
                stderr = result.stderr.decode(errors="ignore")
                raise RuntimeError(f"LibreOffice conversion failed: {stderr[:200]}")

            with open(docx_path, "rb") as f:
                return f.read()

    @staticmethod
    def _validate_docx(file_content: bytes) -> bool:
        """Check if file_content is a valid DOCX (ZIP with Word content type)."""
        if not zipfile.is_zipfile(io.BytesIO(file_content)):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
                if "[Content_Types].xml" not in zf.namelist():
                    return False
                ct = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore")
                return "wordprocessingml" in ct
        except Exception:
            return False

    @staticmethod
    def extract_text_from_pdf(file_content: bytes) -> Tuple[str, int, List[Dict]]:
        """Extract text from PDF with page-level metadata.

        Returns:
            Tuple of (full_text, page_count, pages_data)
            where pages_data is list of {page_number, text, sections}
        """
        doc = fitz.open(stream=file_content, filetype="pdf")
        pages_data = []
        full_text_parts = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            full_text_parts.append(text)

            # Try to detect section headers (lines that look like titles)
            sections = []
            for line in text.split("\n"):
                stripped = line.strip()
                if (
                    stripped
                    and len(stripped) < 200
                    and not stripped.endswith(".")
                    and (stripped[0].isupper() or stripped[0].isdigit())
                    and len(stripped.split()) < 20
                ):
                    sections.append(stripped)

            pages_data.append({
                "page_number": page_num + 1,
                "text": text,
                "sections": sections,
            })

        doc.close()
        return "\n\n".join(full_text_parts), len(pages_data), pages_data

    @staticmethod
    def extract_images_from_pdf(
        file_content: bytes, document_id: str
    ) -> List[Dict]:
        """Extract images from PDF document.

        Returns list of image metadata dicts with saved file paths.
        """
        doc = fitz.open(stream=file_content, filetype="pdf")
        images = []
        images_dir = os.path.join(settings.images_dir, document_id)
        os.makedirs(images_dir, exist_ok=True)

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image.get("ext", "png")
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Skip very small images (likely decorative)
                    if width < 50 or height < 50:
                        continue

                    # Generate filename
                    img_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                    filename = f"page{page_num + 1}_img{img_index + 1}_{img_hash}.{image_ext}"
                    filepath = os.path.join(images_dir, filename)

                    # Save image
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)

                    # Get surrounding text as context
                    page_text = page.get_text("text")
                    context_lines = page_text.split("\n")
                    context = " ".join(line.strip() for line in context_lines[:5] if line.strip())

                    images.append({
                        "stored_filename": filename,
                        "file_path": filepath,
                        "page_number": page_num + 1,
                        "width": width,
                        "height": height,
                        "context": context[:500],
                        "description": "",
                        "tags": [],
                    })

                except Exception as e:
                    print(f"Error extracting image from page {page_num + 1}: {e}")
                    continue

        doc.close()
        return images

    @staticmethod
    def extract_text_from_docx(file_content: bytes) -> Tuple[str, List[Dict]]:
        """Extract text from DOCX with structural metadata.

        Returns:
            Tuple of (full_text, sections_data)
        """
        if not DocumentProcessor._validate_docx(file_content):
            raise ValueError(
                "Le fichier n'est pas un document Word (.docx) valide. "
                "Les fichiers .doc (ancien format) ne sont pas supportés."
            )
        doc = DocxDocument(io.BytesIO(file_content))
        full_text_parts = []
        sections_data = []
        current_section = {"title": "", "content_parts": []}

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Detect headings
            if para.style and para.style.name and "heading" in para.style.name.lower():
                # Save previous section
                if current_section["content_parts"]:
                    sections_data.append({
                        "title": current_section["title"],
                        "content": "\n".join(current_section["content_parts"]),
                    })
                current_section = {"title": text, "content_parts": []}
            else:
                current_section["content_parts"].append(text)

            full_text_parts.append(text)

        # Save last section
        if current_section["content_parts"]:
            sections_data.append({
                "title": current_section["title"],
                "content": "\n".join(current_section["content_parts"]),
            })

        return "\n\n".join(full_text_parts), sections_data

    @staticmethod
    def extract_images_from_docx(
        file_content: bytes, document_id: str
    ) -> List[Dict]:
        """Extract images from DOCX document."""
        if not DocumentProcessor._validate_docx(file_content):
            return []
        doc = DocxDocument(io.BytesIO(file_content))
        images = []
        images_dir = os.path.join(settings.images_dir, document_id)
        os.makedirs(images_dir, exist_ok=True)

        for i, rel in enumerate(doc.part.rels.values()):
            if "image" in rel.reltype:
                try:
                    image_data = rel.target_part.blob
                    content_type = rel.target_part.content_type
                    ext = content_type.split("/")[-1] if "/" in content_type else "png"
                    if ext == "jpeg":
                        ext = "jpg"

                    img_hash = hashlib.md5(image_data).hexdigest()[:8]
                    filename = f"docx_img{i + 1}_{img_hash}.{ext}"
                    filepath = os.path.join(images_dir, filename)

                    with open(filepath, "wb") as f:
                        f.write(image_data)

                    # Get image dimensions
                    try:
                        img = Image.open(io.BytesIO(image_data))
                        width, height = img.size
                    except Exception:
                        width, height = 0, 0

                    if width < 50 or height < 50:
                        continue

                    images.append({
                        "stored_filename": filename,
                        "file_path": filepath,
                        "page_number": 0,
                        "width": width,
                        "height": height,
                        "context": "",
                        "description": "",
                        "tags": [],
                    })

                except Exception as e:
                    print(f"Error extracting image from DOCX: {e}")
                    continue

        return images

    @staticmethod
    def extract_text_from_excel(file_content: bytes) -> str:
        """Extract text from Excel file."""
        wb = load_workbook(io.BytesIO(file_content), data_only=True)
        text_parts = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            text_parts.append(f"\n=== Feuille: {sheet_name} ===\n")

            for row in ws.iter_rows(values_only=True):
                row_texts = []
                for cell in row:
                    if cell is not None:
                        row_texts.append(str(cell))
                if row_texts:
                    text_parts.append(" | ".join(row_texts))

        return "\n".join(text_parts)

    @staticmethod
    def create_chunks(
        text: str,
        document_id: str,
        document_name: str,
        category: str,
        pages_data: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """Split text into overlapping chunks with metadata.

        Args:
            text: Full document text
            document_id: Document UUID
            document_name: Original filename
            category: Document category
            pages_data: Optional page-level data for better chunking

        Returns:
            List of chunk dicts ready for indexing
        """
        chunks = []

        if pages_data:
            # Page-aware chunking
            for page in pages_data:
                page_text = page.get("text", "")
                if not page_text.strip():
                    continue

                words = page_text.split()
                page_num = page.get("page_number", 0)
                sections = page.get("sections", [])
                current_section = sections[0] if sections else ""

                for i in range(0, len(words), CHUNK_SIZE - CHUNK_OVERLAP):
                    chunk_words = words[i : i + CHUNK_SIZE]
                    if len(chunk_words) < 20:
                        continue

                    chunk_text = " ".join(chunk_words)
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "content": chunk_text,
                        "document_id": document_id,
                        "document_name": document_name,
                        "category": category,
                        "page_number": page_num,
                        "section_title": current_section,
                        "chunk_index": len(chunks),
                    })
        else:
            # Simple word-based chunking
            words = text.split()
            for i in range(0, len(words), CHUNK_SIZE - CHUNK_OVERLAP):
                chunk_words = words[i : i + CHUNK_SIZE]
                if len(chunk_words) < 20:
                    continue

                chunk_text = " ".join(chunk_words)
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "content": chunk_text,
                    "document_id": document_id,
                    "document_name": document_name,
                    "category": category,
                    "page_number": 0,
                    "section_title": "",
                    "chunk_index": len(chunks),
                })

        return chunks

    @staticmethod
    def save_uploaded_file(file_content: bytes, project_id: str, filename: str) -> str:
        """Save an uploaded file to disk.

        Returns the file path.
        """
        project_dir = os.path.join(settings.upload_dir, project_id)
        os.makedirs(project_dir, exist_ok=True)

        stored_name = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(project_dir, stored_name)

        with open(filepath, "wb") as f:
            f.write(file_content)

        return filepath

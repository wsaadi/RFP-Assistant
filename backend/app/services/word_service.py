"""Service for generating professional Word documents for RFP responses."""
import io
import os
import re
from typing import List, Optional
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

from ..config import settings


class RFPWordService:
    """Service for generating professional RFP response Word documents."""

    @staticmethod
    def create_styles(doc: Document):
        """Create professional custom styles."""
        styles = doc.styles

        # Heading 1
        h1 = styles["Heading 1"]
        h1.font.size = Pt(18)
        h1.font.bold = True
        h1.font.name = "Calibri"
        h1.font.color.rgb = RGBColor(0x1B, 0x3A, 0x5C)
        h1.paragraph_format.space_before = Pt(24)
        h1.paragraph_format.space_after = Pt(8)
        h1.paragraph_format.keep_with_next = True

        # Heading 2
        h2 = styles["Heading 2"]
        h2.font.size = Pt(14)
        h2.font.bold = True
        h2.font.name = "Calibri"
        h2.font.color.rgb = RGBColor(0x2C, 0x5F, 0x8A)
        h2.paragraph_format.space_before = Pt(16)
        h2.paragraph_format.space_after = Pt(6)

        # Heading 3
        h3 = styles["Heading 3"]
        h3.font.size = Pt(12)
        h3.font.bold = True
        h3.font.name = "Calibri"
        h3.font.color.rgb = RGBColor(0x3D, 0x7A, 0xB5)
        h3.paragraph_format.space_before = Pt(12)
        h3.paragraph_format.space_after = Pt(4)

        # Normal text
        normal = styles["Normal"]
        normal.font.size = Pt(11)
        normal.font.name = "Calibri"
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15

    @staticmethod
    def add_cover_page(doc: Document, project_name: str, client_name: str,
                       rfp_reference: str, company_name: str = ""):
        """Add a professional cover page."""
        # Spacing at top
        for _ in range(4):
            doc.add_paragraph()

        # Title
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("RÉPONSE À L'APPEL D'OFFRES")
        run.bold = True
        run.font.size = Pt(28)
        run.font.color.rgb = RGBColor(0x1B, 0x3A, 0x5C)

        doc.add_paragraph()

        # RFP Reference
        if rfp_reference:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(f"Référence: {rfp_reference}")
            run.font.size = Pt(14)
            run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        # Project name
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(project_name)
        run.bold = True
        run.font.size = Pt(20)
        run.font.color.rgb = RGBColor(0x2C, 0x5F, 0x8A)

        for _ in range(3):
            doc.add_paragraph()

        # Separator
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("━" * 40)
        run.font.color.rgb = RGBColor(0x2C, 0x5F, 0x8A)

        doc.add_paragraph()

        # Client
        if client_name:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(f"Client: {client_name}")
            run.font.size = Pt(14)

        # Company
        if company_name:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(f"Soumissionnaire: {company_name}")
            run.font.size = Pt(14)

        for _ in range(6):
            doc.add_paragraph()

        # Confidentiality notice
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("DOCUMENT CONFIDENTIEL")
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x99, 0x00, 0x00)

        doc.add_page_break()

    @staticmethod
    def add_table_of_contents(doc: Document):
        """Add a Table of Contents field."""
        doc.add_heading("Sommaire", level=1)

        # Add TOC field code
        paragraph = doc.add_paragraph()
        run = paragraph.add_run()
        fldChar = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>')
        run._r.append(fldChar)

        run = paragraph.add_run()
        instrText = parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u</w:instrText>')
        run._r.append(instrText)

        run = paragraph.add_run()
        fldChar = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>')
        run._r.append(fldChar)

        run = paragraph.add_run("[Mettre à jour le sommaire dans Word: clic droit > Mettre à jour les champs]")
        run.italic = True
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

        run = paragraph.add_run()
        fldChar = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>')
        run._r.append(fldChar)

        doc.add_page_break()

    @staticmethod
    def add_chapter_content(doc: Document, title: str, content: str,
                            numbering: str, level: int = 1,
                            images: Optional[List[dict]] = None):
        """Add a chapter with content and optional images."""
        heading_text = f"{numbering} {title}" if numbering else title
        doc.add_heading(heading_text, level=min(level, 3))

        if content and content.strip():
            # Parse content into paragraphs
            paragraphs = content.split("\n\n")
            for para_text in paragraphs:
                para_text = para_text.strip()
                if not para_text:
                    continue

                # Handle sub-paragraphs (single newlines)
                lines = para_text.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    p = doc.add_paragraph()
                    p.paragraph_format.first_line_indent = Cm(0.5)
                    p.add_run(line)
        else:
            p = doc.add_paragraph("[Section à compléter]")
            p.runs[0].italic = True
            p.runs[0].font.color.rgb = RGBColor(0x99, 0x99, 0x99)

        # Add images if any
        if images:
            for img_info in images:
                filepath = img_info.get("file_path", "")
                description = img_info.get("description", "")
                if filepath and os.path.exists(filepath):
                    try:
                        doc.add_paragraph()
                        p = doc.add_paragraph()
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p.add_run()
                        run.add_picture(filepath, width=Inches(4.5))

                        if description:
                            caption = doc.add_paragraph()
                            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            run = caption.add_run(f"Figure: {description}")
                            run.italic = True
                            run.font.size = Pt(9)
                    except Exception as e:
                        print(f"Error adding image: {e}")

    @classmethod
    async def generate_full_document(
        cls,
        project_name: str,
        client_name: str,
        rfp_reference: str,
        chapters: List[dict],
        company_name: str = "",
    ) -> io.BytesIO:
        """Generate a complete Word document for the RFP response."""
        doc = Document()

        # Set margins
        for section in doc.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(2.5)
            section.right_margin = Cm(2.5)

        # Create styles
        cls.create_styles(doc)

        # Cover page
        cls.add_cover_page(doc, project_name, client_name, rfp_reference, company_name)

        # Table of contents
        cls.add_table_of_contents(doc)

        # Add chapters
        def add_chapters_recursive(chapters_list: List[dict], level: int = 1, prefix: str = ""):
            for i, chapter in enumerate(chapters_list, 1):
                numbering = f"{prefix}{i}" if prefix else str(i)
                chapter["numbering"] = numbering

                cls.add_chapter_content(
                    doc,
                    title=chapter.get("title", ""),
                    content=chapter.get("content", ""),
                    numbering=numbering,
                    level=level,
                    images=chapter.get("images"),
                )

                children = chapter.get("children", [])
                if children:
                    add_chapters_recursive(children, level + 1, f"{numbering}.")

                # Page break after major chapters
                if level == 1:
                    doc.add_page_break()

        # Separate main chapters from annexes
        main_chapters = [c for c in chapters if c.get("chapter_type") != "annexe"]
        annexes = [c for c in chapters if c.get("chapter_type") == "annexe"]

        add_chapters_recursive(main_chapters)

        # Add annexes section
        if annexes:
            doc.add_heading("ANNEXES", level=1)
            doc.add_paragraph()
            for i, annexe in enumerate(annexes, 1):
                cls.add_chapter_content(
                    doc,
                    title=annexe.get("title", ""),
                    content=annexe.get("content", ""),
                    numbering=f"A{i}",
                    level=2,
                    images=annexe.get("images"),
                )

        # Save to BytesIO
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        return file_stream

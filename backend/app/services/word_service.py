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

        # List styles
        try:
            list_bullet = styles["List Bullet"]
            list_bullet.font.size = Pt(11)
            list_bullet.font.name = "Calibri"
            list_bullet.paragraph_format.space_after = Pt(3)
            list_bullet.paragraph_format.space_before = Pt(1)
        except KeyError:
            pass

        try:
            list_number = styles["List Number"]
            list_number.font.size = Pt(11)
            list_number.font.name = "Calibri"
            list_number.paragraph_format.space_after = Pt(3)
            list_number.paragraph_format.space_before = Pt(1)
        except KeyError:
            pass

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
    def _add_inline_formatting(paragraph, text: str):
        """Parse inline markdown (bold, italic) and add formatted runs to a paragraph."""
        # Pattern to match **bold**, *italic*, ***bold italic***
        parts = re.split(r'(\*{1,3}[^*]+?\*{1,3})', text)
        for part in parts:
            if not part:
                continue
            if part.startswith('***') and part.endswith('***'):
                run = paragraph.add_run(part[3:-3])
                run.bold = True
                run.italic = True
            elif part.startswith('**') and part.endswith('**'):
                run = paragraph.add_run(part[2:-2])
                run.bold = True
            elif part.startswith('*') and part.endswith('*') and len(part) > 2:
                run = paragraph.add_run(part[1:-1])
                run.italic = True
            else:
                paragraph.add_run(part)

    @classmethod
    def _add_markdown_table(cls, doc: Document, lines: List[str]):
        """Parse a markdown table and add it to the document."""
        # Filter out separator lines (|---|---|)
        data_lines = []
        for line in lines:
            stripped = line.strip().strip('|')
            if stripped and not re.match(r'^[\s\-:|]+$', stripped):
                data_lines.append(line)

        if not data_lines:
            return

        # Parse cells
        rows_data = []
        for line in data_lines:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows_data.append(cells)

        if not rows_data:
            return

        num_cols = max(len(row) for row in rows_data)
        num_rows = len(rows_data)

        table = doc.add_table(rows=num_rows, cols=num_cols)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        for r_idx, row_data in enumerate(rows_data):
            for c_idx, cell_text in enumerate(row_data):
                if c_idx < num_cols:
                    cell = table.rows[r_idx].cells[c_idx]
                    cell.text = ''
                    p = cell.paragraphs[0]
                    cls._add_inline_formatting(p, cell_text)
                    # Bold header row
                    if r_idx == 0:
                        for run in p.runs:
                            run.bold = True
                            run.font.size = Pt(10)

        # Style header row with background
        if rows_data:
            for cell in table.rows[0].cells:
                shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="1B3A5C"/>')
                cell._tc.get_or_add_tcPr().append(shading_elm)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

        doc.add_paragraph()  # spacing after table

    @classmethod
    def add_chapter_content(cls, doc: Document, title: str, content: str,
                            numbering: str, level: int = 1,
                            images: Optional[List[dict]] = None):
        """Add a chapter with content parsed from markdown."""
        heading_text = f"{numbering} {title}" if numbering else title
        doc.add_heading(heading_text, level=min(level, 3))

        if content and content.strip():
            cls._parse_markdown_to_docx(doc, content, base_heading_level=min(level + 1, 3))
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
    def _parse_markdown_to_docx(cls, doc: Document, content: str, base_heading_level: int = 2):
        """Parse markdown content and add properly formatted elements to the Word document.

        Handles: headings (##), bold/italic, bullet lists (- *), numbered lists (1.),
        tables (|...|), horizontal rules (---), and regular paragraphs.
        """
        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                i += 1
                continue

            # Horizontal rule
            if re.match(r'^-{3,}$|^\*{3,}$|^_{3,}$', stripped):
                # Add a thin horizontal line
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(6)
                pPr = p._p.get_or_add_pPr()
                pBdr = parse_xml(
                    f'<w:pBdr {nsdecls("w")}>'
                    f'  <w:bottom w:val="single" w:sz="4" w:space="1" w:color="CCCCCC"/>'
                    f'</w:pBdr>'
                )
                pPr.append(pBdr)
                i += 1
                continue

            # Markdown headings (## Title)
            heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped)
            if heading_match:
                hashes = heading_match.group(1)
                heading_text = heading_match.group(2).strip()
                md_level = len(hashes)
                # Map markdown level: ## -> base, ### -> base+1, etc.
                doc_level = min(base_heading_level + md_level - 2, 4)
                doc_level = max(1, doc_level)
                h = doc.add_heading(level=min(doc_level, 3))
                cls._add_inline_formatting(h, heading_text)
                i += 1
                continue

            # Table (lines starting with |)
            if stripped.startswith('|'):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i])
                    i += 1
                cls._add_markdown_table(doc, table_lines)
                continue

            # Bullet list (- item or * item)
            if re.match(r'^[\-\*]\s+', stripped):
                while i < len(lines) and re.match(r'^\s*[\-\*]\s+', lines[i]):
                    item_text = re.sub(r'^\s*[\-\*]\s+', '', lines[i]).strip()
                    p = doc.add_paragraph(style='List Bullet')
                    cls._add_inline_formatting(p, item_text)
                    i += 1
                continue

            # Numbered list (1. item)
            if re.match(r'^\d+[\.\)]\s+', stripped):
                while i < len(lines) and re.match(r'^\s*\d+[\.\)]\s+', lines[i]):
                    item_text = re.sub(r'^\s*\d+[\.\)]\s+', '', lines[i]).strip()
                    p = doc.add_paragraph(style='List Number')
                    cls._add_inline_formatting(p, item_text)
                    i += 1
                continue

            # Regular paragraph - collect consecutive non-special lines
            para_lines = []
            while i < len(lines):
                l = lines[i].strip()
                if not l:
                    i += 1
                    break
                # Stop if next line is a special element
                if (re.match(r'^#{1,6}\s+', l) or
                    re.match(r'^[\-\*]\s+', l) or
                    re.match(r'^\d+[\.\)]\s+', l) or
                    l.startswith('|') or
                    re.match(r'^-{3,}$|^\*{3,}$|^_{3,}$', l)):
                    break
                para_lines.append(lines[i].strip())
                i += 1

            if para_lines:
                para_text = ' '.join(para_lines)
                p = doc.add_paragraph()
                cls._add_inline_formatting(p, para_text)

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

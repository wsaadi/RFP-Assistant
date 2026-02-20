"""Service for generating Word documents."""
import io
import re
from typing import List, Tuple
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from ..models.report import ReportData, ReportSection
from .ai_service import AIService
from ..models.report import AIProviderConfig


class MarkdownParser:
    """Parser to convert Markdown text to Word formatting."""

    @staticmethod
    def parse_inline_formatting(text: str, paragraph: Paragraph) -> None:
        """Parse inline Markdown formatting and add runs to paragraph."""
        # Pattern to match **bold**, *italic*, ***bold italic***, `code`
        # Process text segment by segment

        # Combined pattern for all inline formatting
        pattern = r'(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__|_(.+?)_|`(.+?)`)'

        last_end = 0
        text_to_process = text

        for match in re.finditer(pattern, text_to_process):
            # Add text before this match as normal text
            if match.start() > last_end:
                normal_text = text_to_process[last_end:match.start()]
                if normal_text:
                    paragraph.add_run(normal_text)

            full_match = match.group(0)

            # Bold and italic (***text***)
            if match.group(2):
                run = paragraph.add_run(match.group(2))
                run.bold = True
                run.italic = True
            # Bold (**text** or __text__)
            elif match.group(3):
                run = paragraph.add_run(match.group(3))
                run.bold = True
            elif match.group(5):
                run = paragraph.add_run(match.group(5))
                run.bold = True
            # Italic (*text* or _text_)
            elif match.group(4):
                run = paragraph.add_run(match.group(4))
                run.italic = True
            elif match.group(6):
                run = paragraph.add_run(match.group(6))
                run.italic = True
            # Code (`text`)
            elif match.group(7):
                run = paragraph.add_run(match.group(7))
                run.font.name = "Courier New"
                run.font.size = Pt(10)

            last_end = match.end()

        # Add remaining text after last match
        if last_end < len(text_to_process):
            remaining = text_to_process[last_end:]
            if remaining:
                paragraph.add_run(remaining)

        # If no matches were found, add the entire text
        if last_end == 0 and text:
            paragraph.add_run(text)

    @staticmethod
    def clean_markdown_artifacts(text: str) -> str:
        """Remove common Markdown artifacts that shouldn't appear in final text."""
        # Remove horizontal rules
        text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\*{3,}$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^_{3,}$', '', text, flags=re.MULTILINE)

        # Remove HTML comments
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

        # Remove bold markers ** and __
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)

        # Remove italic markers * and _
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)

        # Remove code markers `
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Remove code blocks ```
        text = re.sub(r'```[a-z]*\n?(.*?)```', r'\1', text, flags=re.DOTALL)

        # Remove heading markers #
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Remove bullet points - and *
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)

        # Remove numbered list markers
        text = re.sub(r'^[\s]*\d+[.)]\s+', '', text, flags=re.MULTILINE)

        # Remove blockquote markers >
        text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)

        # Remove link syntax [text](url)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Remove image syntax ![alt](url)
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)

        # Clean orphaned markdown symbols
        text = re.sub(r'^\s*\*\*\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*__\s*$', '', text, flags=re.MULTILINE)

        # Clean up multiple blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    @staticmethod
    def parse_content(doc: Document, content: str, base_heading_level: int = 2) -> None:
        """Parse Markdown content and add it to the document with proper formatting."""
        if not content:
            return

        # Clean artifacts first
        content = MarkdownParser.clean_markdown_artifacts(content)

        lines = content.split('\n')
        i = 0
        current_paragraph_lines: List[str] = []
        in_list = False
        list_indent = 0

        def flush_paragraph():
            """Flush accumulated paragraph lines."""
            nonlocal current_paragraph_lines
            if current_paragraph_lines:
                para_text = ' '.join(current_paragraph_lines).strip()
                if para_text:
                    p = doc.add_paragraph()
                    p.paragraph_format.first_line_indent = Cm(1)
                    MarkdownParser.parse_inline_formatting(para_text, p)
                current_paragraph_lines = []

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines (they mark paragraph breaks)
            if not stripped:
                flush_paragraph()
                i += 1
                continue

            # Check for headings (# ## ### etc.)
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                # Remove any trailing # characters
                heading_text = re.sub(r'\s*#+\s*$', '', heading_text)
                # Adjust heading level based on context
                actual_level = min(level + base_heading_level - 1, 4)
                doc.add_heading(heading_text, level=actual_level)
                i += 1
                continue

            # Check for unordered list items (- or * or +)
            list_match = re.match(r'^(\s*)([-*+])\s+(.+)$', stripped)
            if list_match or re.match(r'^(\s*)([-*+])\s+(.+)$', line):
                flush_paragraph()
                # Re-match with original line to preserve indentation info
                list_match = re.match(r'^(\s*)([-*+])\s+(.+)$', line)
                if list_match:
                    item_text = list_match.group(3).strip()
                    p = doc.add_paragraph(style='List Bullet')
                    MarkdownParser.parse_inline_formatting(item_text, p)
                i += 1
                continue

            # Check for ordered list items (1. 2. etc.)
            ordered_match = re.match(r'^(\s*)(\d+)[.)]\s+(.+)$', line)
            if ordered_match:
                flush_paragraph()
                item_text = ordered_match.group(3).strip()
                p = doc.add_paragraph(style='List Number')
                MarkdownParser.parse_inline_formatting(item_text, p)
                i += 1
                continue

            # Check for blockquotes (>)
            quote_match = re.match(r'^>\s*(.*)$', stripped)
            if quote_match:
                flush_paragraph()
                quote_text = quote_match.group(1).strip()
                if quote_text:
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Cm(1)
                    run = p.add_run(quote_text)
                    run.italic = True
                i += 1
                continue

            # Regular text - accumulate for paragraph
            # Remove any leading/trailing formatting markers that might be orphaned
            clean_line = stripped
            current_paragraph_lines.append(clean_line)
            i += 1

        # Flush any remaining paragraph
        flush_paragraph()


class WordService:
    """Service for generating Word documents from report data."""

    @staticmethod
    def create_styles(doc: Document):
        """Create custom styles for the document."""
        styles = doc.styles

        # Title style
        if "Report Title" not in [s.name for s in styles]:
            title_style = styles.add_style("Report Title", WD_STYLE_TYPE.PARAGRAPH)
            title_style.font.size = Pt(24)
            title_style.font.bold = True
            title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_style.paragraph_format.space_after = Pt(12)

        # Heading 1 style customization
        h1 = styles["Heading 1"]
        h1.font.size = Pt(16)
        h1.font.bold = True
        h1.font.name = "Arial"
        h1.paragraph_format.space_before = Pt(18)
        h1.paragraph_format.space_after = Pt(6)

        # Heading 2 style customization
        h2 = styles["Heading 2"]
        h2.font.size = Pt(14)
        h2.font.bold = True
        h2.font.name = "Arial"
        h2.paragraph_format.space_before = Pt(12)
        h2.paragraph_format.space_after = Pt(6)

        # Heading 3 style customization
        h3 = styles["Heading 3"]
        h3.font.size = Pt(12)
        h3.font.bold = True
        h3.font.name = "Arial"
        h3.paragraph_format.space_before = Pt(10)
        h3.paragraph_format.space_after = Pt(4)

        # Normal text
        normal = styles["Normal"]
        normal.font.size = Pt(12)
        normal.font.name = "Times New Roman"
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15

    @staticmethod
    def add_cover_page(doc: Document, report: ReportData):
        """Add the cover page to the document."""
        # Add some space at the top
        for _ in range(3):
            doc.add_paragraph()

        # UTC Logo placeholder
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run("[Logo UTC]")
        run.italic = True

        # Student info (top right)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.add_run(f"{report.student_name.upper()} {report.student_firstname}\n")
        p.add_run(f"Semestre {report.semester}")

        # Add space
        for _ in range(4):
            doc.add_paragraph()

        # Title
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("RAPPORT DE STAGE TN05")
        run.bold = True
        run.font.size = Pt(24)

        doc.add_paragraph()

        # Company name
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(report.company_name)
        run.bold = True
        run.font.size = Pt(18)

        # Location
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(report.company_location)

        # Dates
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(f"Du {report.internship_start_date} au {report.internship_end_date}")

        # Add space before tutor
        for _ in range(6):
            doc.add_paragraph()

        # Tutor info (bottom left)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.add_run(f"Tuteur entreprise : {report.tutor_name}")

        # Page break
        doc.add_page_break()

    @staticmethod
    def add_section_content(
        doc: Document,
        section: ReportSection,
        level: int = 1,
        section_number: str = "",
    ):
        """Add a section and its content to the document."""
        # Add section title with number
        title = f"{section_number} {section.title}" if section_number else section.title
        doc.add_heading(title, level=min(level, 3))

        # Add content if available
        if section.content and section.content.strip():
            # Use Markdown parser to handle formatting
            MarkdownParser.parse_content(doc, section.content, base_heading_level=level + 1)
        elif section.notes:
            # If no content but has notes, use notes
            for note in section.notes:
                if note.content.strip():
                    p = doc.add_paragraph()
                    p.paragraph_format.first_line_indent = Cm(1)
                    MarkdownParser.parse_inline_formatting(note.content.strip(), p)
        else:
            # Placeholder for empty sections
            p = doc.add_paragraph("[Section à compléter]")
            p.runs[0].italic = True

        # Add subsections
        if section.subsections:
            for i, subsection in enumerate(section.subsections, 1):
                sub_number = f"{section_number}.{i}" if section_number else str(i)
                WordService.add_section_content(
                    doc, subsection, level + 1, sub_number
                )

    @staticmethod
    async def generate_document(
        report: ReportData, ai_config: AIProviderConfig | None = None
    ) -> io.BytesIO:
        """Generate a complete Word document from the report data."""
        doc = Document()

        # Set document margins
        for section in doc.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(2.5)
            section.right_margin = Cm(2.5)

        # Create custom styles
        WordService.create_styles(doc)

        # Add cover page
        WordService.add_cover_page(doc, report)

        # Process each main section
        section_counter = 0
        for section in report.plan.sections:
            # Skip cover page in body (already added)
            if section.id == "cover_page":
                continue

            # Handle special sections
            if section.id == "table_of_contents":
                doc.add_heading("Sommaire", level=1)
                p = doc.add_paragraph("[Le sommaire sera généré automatiquement dans Word]")
                p.runs[0].italic = True
                doc.add_page_break()
                continue

            section_counter += 1
            WordService.add_section_content(
                doc, section, level=1, section_number=str(section_counter)
            )

            # Add page break after major sections
            if section.id in ["introduction", "company_presentation", "tasks_accomplished", "conclusion"]:
                doc.add_page_break()

        # Save to BytesIO
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)

        return file_stream

    @staticmethod
    async def generate_document_with_ai(
        report: ReportData, ai_config: AIProviderConfig
    ) -> io.BytesIO:
        """Generate a Word document with AI-enhanced content."""
        ai_service = AIService(ai_config)

        # Build company context
        company_context = f"""
Entreprise : {report.company_name}
Lieu : {report.company_location}
Période : du {report.internship_start_date} au {report.internship_end_date}
Tuteur : {report.tutor_name}
"""

        # Enhance sections with AI
        async def enhance_section(section: ReportSection):
            notes_text = "\n".join([note.content for note in section.notes]) if section.notes else ""

            if notes_text.strip() and not section.content:
                # No content yet but has notes: generate content from notes
                section.content = await ai_service.generate_section_content(
                    section_title=section.title,
                    section_description=section.description,
                    notes=notes_text,
                    company_context=company_context,
                )
            elif notes_text.strip() and section.content and section.content.strip():
                # Has both content and notes: improve content by integrating new notes
                # without duplicating information already present
                section.content = await ai_service.improve_text(
                    text=section.content,
                    section_context=section.title,
                    notes=notes_text,
                )

            # Process subsections
            for subsection in section.subsections:
                await enhance_section(subsection)

        # Enhance all sections
        for section in report.plan.sections:
            await enhance_section(section)

        # Generate the document
        return await WordService.generate_document(report, ai_config)

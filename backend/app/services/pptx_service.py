"""Service for generating professional PowerPoint presentations for RFP soutenance."""
import io
import logging
import re
from typing import Dict, List, Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

logger = logging.getLogger(__name__)

# Color palette
COLOR_PRIMARY = RGBColor(0x1B, 0x3A, 0x5C)
COLOR_SECONDARY = RGBColor(0x2C, 0x5F, 0x8A)
COLOR_ACCENT = RGBColor(0x3D, 0x7A, 0xB5)
COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
COLOR_LIGHT_BG = RGBColor(0xF0, 0xF4, 0xF8)
COLOR_DARK_TEXT = RGBColor(0x2C, 0x3E, 0x50)
COLOR_MUTED = RGBColor(0x7F, 0x8C, 0x8D)
COLOR_SUCCESS = RGBColor(0x27, 0xAE, 0x60)
COLOR_WARN = RGBColor(0xE6, 0x7E, 0x22)


class RFPPptxService:
    """Service for generating professional soutenance PowerPoint presentations."""

    @staticmethod
    def _add_background(slide, color: RGBColor):
        """Set slide background color."""
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = color

    @staticmethod
    def _add_shape_rect(slide, left, top, width, height, color: RGBColor):
        """Add a filled rectangle shape."""
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        return shape

    @staticmethod
    def _add_text_box(slide, left, top, width, height, text: str,
                      font_size: int = 14, bold: bool = False,
                      color: RGBColor = COLOR_DARK_TEXT,
                      alignment=PP_ALIGN.LEFT):
        """Add a text box with formatted text."""
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.color.rgb = color
        p.alignment = alignment
        return txBox

    @classmethod
    def _create_title_slide(cls, prs: Presentation, project_name: str,
                            client_name: str, company_name: str,
                            rfp_reference: str):
        """Create an impactful cover slide."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout
        cls._add_background(slide, COLOR_PRIMARY)

        # Top accent bar
        cls._add_shape_rect(slide, Inches(0), Inches(0), prs.slide_width, Inches(0.08), COLOR_ACCENT)

        # Main title
        cls._add_text_box(
            slide, Inches(1), Inches(1.5), Inches(8), Inches(1),
            "SOUTENANCE", font_size=40, bold=True,
            color=COLOR_WHITE, alignment=PP_ALIGN.CENTER,
        )

        # Project name
        cls._add_text_box(
            slide, Inches(1), Inches(2.5), Inches(8), Inches(0.8),
            project_name, font_size=28, bold=True,
            color=COLOR_ACCENT, alignment=PP_ALIGN.CENTER,
        )

        # Separator
        cls._add_shape_rect(
            slide, Inches(3.5), Inches(3.5), Inches(3), Inches(0.04), COLOR_ACCENT,
        )

        # Client & reference
        info_lines = []
        if client_name:
            info_lines.append(f"Client : {client_name}")
        if company_name:
            info_lines.append(f"Soumissionnaire : {company_name}")
        if rfp_reference:
            info_lines.append(f"Reference : {rfp_reference}")
        if info_lines:
            cls._add_text_box(
                slide, Inches(1), Inches(3.8), Inches(8), Inches(1.5),
                "\n".join(info_lines), font_size=16,
                color=COLOR_WHITE, alignment=PP_ALIGN.CENTER,
            )

        # Bottom bar
        cls._add_shape_rect(
            slide, Inches(0), Inches(7.2), prs.slide_width, Inches(0.3), COLOR_SECONDARY,
        )
        cls._add_text_box(
            slide, Inches(1), Inches(7.2), Inches(8), Inches(0.3),
            "DOCUMENT CONFIDENTIEL", font_size=10, bold=True,
            color=COLOR_WHITE, alignment=PP_ALIGN.CENTER,
        )

    @classmethod
    def _create_agenda_slide(cls, prs: Presentation, sections: List[dict]):
        """Create an agenda/summary slide."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_WHITE)

        # Header bar
        cls._add_shape_rect(slide, Inches(0), Inches(0), prs.slide_width, Inches(1.1), COLOR_PRIMARY)
        cls._add_text_box(
            slide, Inches(0.5), Inches(0.2), Inches(9), Inches(0.7),
            "AGENDA", font_size=32, bold=True,
            color=COLOR_WHITE, alignment=PP_ALIGN.LEFT,
        )

        # Agenda items
        y = Inches(1.5)
        for i, section in enumerate(sections, 1):
            title = section.get("title", "")
            duration = section.get("duration", "")

            # Number circle
            num_shape = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, Inches(0.8), y, Inches(0.5), Inches(0.5),
            )
            num_shape.fill.solid()
            num_shape.fill.fore_color.rgb = COLOR_SECONDARY
            num_shape.line.fill.background()
            tf = num_shape.text_frame
            tf.paragraphs[0].text = str(i)
            tf.paragraphs[0].font.size = Pt(16)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = COLOR_WHITE
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE

            # Title
            cls._add_text_box(
                slide, Inches(1.5), y + Inches(0.05), Inches(6), Inches(0.4),
                title, font_size=16, bold=True, color=COLOR_PRIMARY,
            )

            # Duration
            if duration:
                cls._add_text_box(
                    slide, Inches(7.5), y + Inches(0.05), Inches(2), Inches(0.4),
                    duration, font_size=12, color=COLOR_MUTED, alignment=PP_ALIGN.RIGHT,
                )

            y += Inches(0.65)

    @classmethod
    def _create_section_divider(cls, prs: Presentation, section_number: int,
                                section_title: str):
        """Create a section divider slide."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_SECONDARY)

        # Large section number
        cls._add_text_box(
            slide, Inches(1), Inches(2), Inches(8), Inches(1),
            f"0{section_number}" if section_number < 10 else str(section_number),
            font_size=72, bold=True,
            color=RGBColor(0xFF, 0xFF, 0xFF), alignment=PP_ALIGN.CENTER,
        )

        # Section title
        cls._add_text_box(
            slide, Inches(1), Inches(3.2), Inches(8), Inches(1),
            section_title.upper(), font_size=28, bold=True,
            color=COLOR_WHITE, alignment=PP_ALIGN.CENTER,
        )

        # Accent bar under title
        cls._add_shape_rect(
            slide, Inches(3.5), Inches(4.3), Inches(3), Inches(0.04), COLOR_ACCENT,
        )

    @classmethod
    def _create_content_slide(cls, prs: Presentation, title: str,
                              bullet_points: List[str],
                              subtitle: str = "",
                              speaker_notes: str = ""):
        """Create a content slide with bullet points."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_WHITE)

        # Top accent line
        cls._add_shape_rect(slide, Inches(0), Inches(0), prs.slide_width, Inches(0.06), COLOR_PRIMARY)

        # Title
        cls._add_text_box(
            slide, Inches(0.5), Inches(0.3), Inches(9), Inches(0.6),
            title, font_size=24, bold=True, color=COLOR_PRIMARY,
        )

        # Subtitle
        if subtitle:
            cls._add_text_box(
                slide, Inches(0.5), Inches(0.9), Inches(9), Inches(0.4),
                subtitle, font_size=14, color=COLOR_MUTED,
            )

        # Bullet points
        start_y = Inches(1.5) if subtitle else Inches(1.2)
        txBox = slide.shapes.add_textbox(
            Inches(0.7), start_y, Inches(8.5), Inches(5),
        )
        tf = txBox.text_frame
        tf.word_wrap = True

        for idx, point in enumerate(bullet_points):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            # Handle sub-bullets (lines starting with "  -")
            if point.strip().startswith("- ") and point.startswith("  "):
                p.text = point.strip()[2:]
                p.font.size = Pt(13)
                p.font.color.rgb = COLOR_DARK_TEXT
                p.level = 1
                p.space_before = Pt(4)
            else:
                p.text = point.lstrip("- ").strip()
                p.font.size = Pt(15)
                p.font.color.rgb = COLOR_DARK_TEXT
                p.font.bold = False
                p.level = 0
                p.space_before = Pt(8)

            # Add bullet character
            pPr = p._pPr
            if pPr is None:
                from pptx.oxml.ns import qn
                pPr = p._p.get_or_add_pPr()

        # Speaker notes
        if speaker_notes:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = speaker_notes

    @classmethod
    def _create_key_figures_slide(cls, prs: Presentation, title: str,
                                  figures: List[dict]):
        """Create a slide with key figures/metrics."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_WHITE)

        # Top accent line
        cls._add_shape_rect(slide, Inches(0), Inches(0), prs.slide_width, Inches(0.06), COLOR_PRIMARY)

        # Title
        cls._add_text_box(
            slide, Inches(0.5), Inches(0.3), Inches(9), Inches(0.6),
            title, font_size=24, bold=True, color=COLOR_PRIMARY,
        )

        # Display figures in a grid
        cols = min(len(figures), 4)
        box_width = Inches(8) / cols
        start_x = Inches(1)

        for i, fig in enumerate(figures):
            col = i % cols
            row = i // cols
            x = start_x + col * box_width
            y = Inches(1.8) + row * Inches(2.2)

            # Value
            cls._add_text_box(
                slide, x, y, box_width - Inches(0.3), Inches(0.8),
                fig.get("value", ""), font_size=36, bold=True,
                color=COLOR_SECONDARY, alignment=PP_ALIGN.CENTER,
            )
            # Label
            cls._add_text_box(
                slide, x, y + Inches(0.8), box_width - Inches(0.3), Inches(0.5),
                fig.get("label", ""), font_size=13,
                color=COLOR_MUTED, alignment=PP_ALIGN.CENTER,
            )

    @classmethod
    def _create_strengths_slide(cls, prs: Presentation, strengths: List[str]):
        """Create a slide highlighting key strengths."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_LIGHT_BG)

        # Header
        cls._add_shape_rect(slide, Inches(0), Inches(0), prs.slide_width, Inches(1.1), COLOR_PRIMARY)
        cls._add_text_box(
            slide, Inches(0.5), Inches(0.2), Inches(9), Inches(0.7),
            "NOS FORCES", font_size=28, bold=True,
            color=COLOR_WHITE, alignment=PP_ALIGN.LEFT,
        )

        # Strength items as cards
        y = Inches(1.5)
        for i, strength in enumerate(strengths[:8]):
            # Card background
            card = cls._add_shape_rect(
                slide, Inches(0.6), y, Inches(8.8), Inches(0.6), COLOR_WHITE,
            )

            # Check icon area
            icon_shape = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, Inches(0.8), y + Inches(0.1), Inches(0.35), Inches(0.35),
            )
            icon_shape.fill.solid()
            icon_shape.fill.fore_color.rgb = COLOR_SUCCESS
            icon_shape.line.fill.background()
            tf = icon_shape.text_frame
            tf.paragraphs[0].text = "\u2713"
            tf.paragraphs[0].font.size = Pt(14)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = COLOR_WHITE
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE

            # Strength text
            cls._add_text_box(
                slide, Inches(1.4), y + Inches(0.1), Inches(7.8), Inches(0.4),
                strength, font_size=14, color=COLOR_DARK_TEXT,
            )

            y += Inches(0.7)

    @classmethod
    def _create_closing_slide(cls, prs: Presentation, company_name: str,
                              client_name: str):
        """Create a closing/Q&A slide."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_PRIMARY)

        cls._add_text_box(
            slide, Inches(1), Inches(2), Inches(8), Inches(1),
            "MERCI", font_size=48, bold=True,
            color=COLOR_WHITE, alignment=PP_ALIGN.CENTER,
        )

        cls._add_shape_rect(
            slide, Inches(3.5), Inches(3.2), Inches(3), Inches(0.04), COLOR_ACCENT,
        )

        cls._add_text_box(
            slide, Inches(1), Inches(3.6), Inches(8), Inches(0.6),
            "Questions & Echanges", font_size=24,
            color=COLOR_ACCENT, alignment=PP_ALIGN.CENTER,
        )

        contact_text = ""
        if company_name:
            contact_text += company_name
        if client_name:
            if contact_text:
                contact_text += f"  |  Client : {client_name}"
        if contact_text:
            cls._add_text_box(
                slide, Inches(1), Inches(5), Inches(8), Inches(0.5),
                contact_text, font_size=14,
                color=COLOR_WHITE, alignment=PP_ALIGN.CENTER,
            )

        # Bottom bar
        cls._add_shape_rect(
            slide, Inches(0), Inches(7.2), prs.slide_width, Inches(0.3), COLOR_SECONDARY,
        )

    @classmethod
    def generate_presentation(
        cls,
        project_name: str,
        client_name: str,
        company_name: str,
        rfp_reference: str,
        soutenance_data: dict,
    ) -> io.BytesIO:
        """Generate a complete soutenance PowerPoint from structured AI data.

        Args:
            soutenance_data: Dict with keys:
                - sections: list of {title, duration, slides: [{title, subtitle, bullets, speaker_notes}]}
                - key_figures: list of {value, label}
                - strengths: list of strings
        """
        prs = Presentation()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)

        # 1. Cover slide
        cls._create_title_slide(prs, project_name, client_name, company_name, rfp_reference)

        # 2. Agenda slide
        sections = soutenance_data.get("sections", [])
        cls._create_agenda_slide(prs, sections)

        # 3. Content slides per section
        for sec_idx, section in enumerate(sections, 1):
            # Section divider
            cls._create_section_divider(prs, sec_idx, section.get("title", ""))

            # Section content slides
            for slide_data in section.get("slides", []):
                cls._create_content_slide(
                    prs,
                    title=slide_data.get("title", ""),
                    bullet_points=slide_data.get("bullets", []),
                    subtitle=slide_data.get("subtitle", ""),
                    speaker_notes=slide_data.get("speaker_notes", ""),
                )

        # 4. Key figures slide (if provided)
        key_figures = soutenance_data.get("key_figures", [])
        if key_figures:
            cls._create_key_figures_slide(prs, "CHIFFRES CLES", key_figures)

        # 5. Strengths slide
        strengths = soutenance_data.get("strengths", [])
        if strengths:
            cls._create_strengths_slide(prs, strengths)

        # 6. Closing slide
        cls._create_closing_slide(prs, company_name, client_name)

        # Save
        file_stream = io.BytesIO()
        prs.save(file_stream)
        file_stream.seek(0)
        return file_stream

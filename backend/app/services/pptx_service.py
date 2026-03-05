"""Service for generating professional PowerPoint presentations for RFP soutenance."""
import io
import logging
import math
from typing import Dict, List, Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

logger = logging.getLogger(__name__)

# ── Color palette ──
COLOR_PRIMARY = RGBColor(0x1B, 0x3A, 0x5C)      # Dark navy
COLOR_SECONDARY = RGBColor(0x2C, 0x5F, 0x8A)     # Medium blue
COLOR_ACCENT = RGBColor(0x3D, 0x7A, 0xB5)        # Bright blue
COLOR_ACCENT_LIGHT = RGBColor(0x5A, 0x9F, 0xD4)  # Light accent
COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
COLOR_LIGHT_BG = RGBColor(0xF0, 0xF4, 0xF8)      # Very light gray-blue
COLOR_CARD_BG = RGBColor(0xF8, 0xFA, 0xFC)        # Card background
COLOR_DARK_TEXT = RGBColor(0x2C, 0x3E, 0x50)
COLOR_MUTED = RGBColor(0x7F, 0x8C, 0x8D)
COLOR_SUCCESS = RGBColor(0x27, 0xAE, 0x60)
COLOR_WARN = RGBColor(0xE6, 0x7E, 0x22)
COLOR_PURPLE = RGBColor(0x8E, 0x44, 0xAD)
COLOR_TEAL = RGBColor(0x00, 0x89, 0x7B)
COLOR_CORAL = RGBColor(0xE7, 0x4C, 0x3C)

# Unicode icons for visual decoration
ICON_CHECK = "\u2713"      # ✓
ICON_ARROW = "\u279C"      # ➜
ICON_STAR = "\u2605"        # ★
ICON_DIAMOND = "\u25C6"    # ◆
ICON_CIRCLE = "\u25CF"     # ●
ICON_BULLET = "\u2022"     # •
ICON_QUOTE_L = "\u201C"    # "
ICON_QUOTE_R = "\u201D"    # "
ICON_TARGET = "\u25CE"     # ◎
ICON_LIGHT = "\u2600"      # ☀
ICON_SHIELD = "\u25D0"     # ◐
ICON_CHART = "\u25A0"      # ■


class RFPPptxService:
    """Service for generating professional soutenance PowerPoint presentations."""

    SLIDE_W = Inches(13.333)  # 16:9 widescreen
    SLIDE_H = Inches(7.5)

    # ── Low-level helpers ──

    @staticmethod
    def _add_background(slide, color: RGBColor):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = color

    @staticmethod
    def _rect(slide, left, top, width, height, color: RGBColor, alpha=None):
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        shape.rotation = 0
        return shape

    @staticmethod
    def _rounded_rect(slide, left, top, width, height, color: RGBColor):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        return shape

    @staticmethod
    def _oval(slide, left, top, w, h, color: RGBColor):
        shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        return shape

    @staticmethod
    def _text_box(slide, left, top, width, height, text: str,
                  font_size=14, bold=False, color=COLOR_DARK_TEXT,
                  alignment=PP_ALIGN.LEFT, font_name="Calibri"):
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.color.rgb = color
        p.font.name = font_name
        p.alignment = alignment
        return txBox

    @staticmethod
    def _add_notes(slide, text: str):
        if text:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = text

    # ── Decorative elements ──

    @classmethod
    def _add_corner_accent(cls, slide, position="top-right"):
        """Add a decorative corner triangle/shape."""
        if position == "top-right":
            # Large decorative circle in top-right corner (partially off-slide)
            cls._oval(slide, cls.SLIDE_W - Inches(2.5), Inches(-1.5),
                      Inches(4), Inches(4), COLOR_ACCENT_LIGHT)
        elif position == "bottom-left":
            cls._oval(slide, Inches(-1.5), cls.SLIDE_H - Inches(2.5),
                      Inches(4), Inches(4), COLOR_ACCENT_LIGHT)

    @classmethod
    def _add_footer_bar(cls, slide, text="", show_page=False, page_num=0, total=0):
        """Add a professional footer bar."""
        cls._rect(slide, Inches(0), cls.SLIDE_H - Inches(0.4),
                  cls.SLIDE_W, Inches(0.4), COLOR_PRIMARY)
        # Accent line above footer
        cls._rect(slide, Inches(0), cls.SLIDE_H - Inches(0.43),
                  cls.SLIDE_W, Inches(0.03), COLOR_ACCENT)
        if text:
            cls._text_box(slide, Inches(0.5), cls.SLIDE_H - Inches(0.38),
                          Inches(6), Inches(0.35), text,
                          font_size=8, color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)
        if show_page:
            cls._text_box(slide, cls.SLIDE_W - Inches(1.5), cls.SLIDE_H - Inches(0.38),
                          Inches(1.2), Inches(0.35), f"{page_num}/{total}",
                          font_size=8, color=COLOR_WHITE, alignment=PP_ALIGN.RIGHT)

    @classmethod
    def _add_slide_header(cls, slide, title: str, subtitle: str = "",
                          section_label: str = ""):
        """Add a professional header to content slides."""
        # Top accent line
        cls._rect(slide, Inches(0), Inches(0), cls.SLIDE_W, Inches(0.05), COLOR_ACCENT)
        # Header background
        cls._rect(slide, Inches(0), Inches(0.05), cls.SLIDE_W, Inches(1.0), COLOR_PRIMARY)

        # Section label (small)
        if section_label:
            cls._text_box(slide, Inches(0.8), Inches(0.12), Inches(10), Inches(0.3),
                          section_label.upper(), font_size=9, bold=True,
                          color=COLOR_ACCENT_LIGHT, alignment=PP_ALIGN.LEFT)

        # Title
        title_y = Inches(0.35) if section_label else Inches(0.2)
        cls._text_box(slide, Inches(0.8), title_y, Inches(10), Inches(0.6),
                      title, font_size=24, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)

        # Subtitle
        if subtitle:
            cls._text_box(slide, Inches(0.8), Inches(1.15), Inches(10), Inches(0.35),
                          subtitle, font_size=13, color=COLOR_MUTED)

    # ── Slide types ──

    @classmethod
    def _create_title_slide(cls, prs, project_name, client_name, company_name, rfp_reference):
        """Create an impactful cover slide with decorative elements."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_PRIMARY)

        # Decorative circles in corners
        cls._oval(slide, cls.SLIDE_W - Inches(4), Inches(-2),
                  Inches(7), Inches(7), COLOR_SECONDARY)
        cls._oval(slide, Inches(-3), cls.SLIDE_H - Inches(4),
                  Inches(6), Inches(6), COLOR_SECONDARY)
        # Smaller accent circles
        cls._oval(slide, cls.SLIDE_W - Inches(2), Inches(5),
                  Inches(3), Inches(3), COLOR_ACCENT)

        # Top accent bar
        cls._rect(slide, Inches(0), Inches(0), cls.SLIDE_W, Inches(0.06), COLOR_ACCENT)

        # "SOUTENANCE" label
        cls._text_box(slide, Inches(1), Inches(1.2), Inches(8), Inches(0.5),
                      "SOUTENANCE COMMERCIALE", font_size=14, bold=True,
                      color=COLOR_ACCENT_LIGHT, alignment=PP_ALIGN.LEFT)

        # Project name - main title
        cls._text_box(slide, Inches(1), Inches(1.8), Inches(8), Inches(1.5),
                      project_name, font_size=36, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)

        # Separator line
        cls._rect(slide, Inches(1), Inches(3.5), Inches(3), Inches(0.05), COLOR_ACCENT)

        # Info block with icons
        info_y = Inches(3.9)
        if client_name:
            cls._text_box(slide, Inches(1), info_y, Inches(8), Inches(0.4),
                          f"{ICON_TARGET}  Client : {client_name}", font_size=16,
                          color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)
            info_y += Inches(0.5)
        if company_name:
            cls._text_box(slide, Inches(1), info_y, Inches(8), Inches(0.4),
                          f"{ICON_DIAMOND}  Soumissionnaire : {company_name}", font_size=16,
                          color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)
            info_y += Inches(0.5)
        if rfp_reference:
            cls._text_box(slide, Inches(1), info_y, Inches(8), Inches(0.4),
                          f"{ICON_BULLET}  Reference : {rfp_reference}", font_size=14,
                          color=COLOR_ACCENT_LIGHT, alignment=PP_ALIGN.LEFT)

        # Bottom bar
        cls._rect(slide, Inches(0), cls.SLIDE_H - Inches(0.5),
                  cls.SLIDE_W, Inches(0.5), COLOR_SECONDARY)
        cls._text_box(slide, Inches(1), cls.SLIDE_H - Inches(0.45),
                      Inches(10), Inches(0.4),
                      "DOCUMENT CONFIDENTIEL", font_size=10, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)

    @classmethod
    def _create_agenda_slide(cls, prs, sections: List[dict]):
        """Create an agenda slide with visual timeline."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_WHITE)

        cls._add_slide_header(slide, "AGENDA")

        # Vertical timeline line
        line_x = Inches(1.6)
        cls._rect(slide, line_x + Inches(0.17), Inches(1.5),
                  Inches(0.04), Inches(5.3), COLOR_ACCENT)

        y = Inches(1.5)
        colors = [COLOR_SECONDARY, COLOR_ACCENT, COLOR_TEAL, COLOR_PURPLE,
                  COLOR_SUCCESS, COLOR_WARN, COLOR_CORAL, COLOR_PRIMARY]

        for i, section in enumerate(sections):
            title = section.get("title", "")
            duration = section.get("duration", "")
            dot_color = colors[i % len(colors)]

            # Timeline dot
            cls._oval(slide, line_x, y + Inches(0.06),
                      Inches(0.38), Inches(0.38), dot_color)
            # Number in dot
            dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, line_x + Inches(0.04),
                                         y + Inches(0.1), Inches(0.3), Inches(0.3))
            dot.fill.solid()
            dot.fill.fore_color.rgb = dot_color
            dot.line.fill.background()
            tf = dot.text_frame
            tf.paragraphs[0].text = str(i + 1)
            tf.paragraphs[0].font.size = Pt(12)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = COLOR_WHITE
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE

            # Title
            cls._text_box(slide, Inches(2.3), y, Inches(7), Inches(0.45),
                          title, font_size=15, bold=True, color=COLOR_PRIMARY)

            # Duration badge
            if duration:
                badge = cls._rounded_rect(slide, Inches(10), y + Inches(0.05),
                                          Inches(1.8), Inches(0.35), COLOR_LIGHT_BG)
                cls._text_box(slide, Inches(10), y + Inches(0.05),
                              Inches(1.8), Inches(0.35), duration,
                              font_size=11, color=COLOR_MUTED, alignment=PP_ALIGN.CENTER)

            y += Inches(0.55)

        cls._add_footer_bar(slide, "CONFIDENTIEL")

    @classmethod
    def _create_section_divider(cls, prs, section_number, section_title, duration=""):
        """Create a visually striking section divider."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_SECONDARY)

        # Decorative circles
        cls._oval(slide, Inches(-2), Inches(-2), Inches(6), Inches(6), COLOR_PRIMARY)
        cls._oval(slide, cls.SLIDE_W - Inches(3), cls.SLIDE_H - Inches(3),
                  Inches(5), Inches(5), COLOR_ACCENT)

        # Section number - large
        num_text = f"0{section_number}" if section_number < 10 else str(section_number)
        cls._text_box(slide, Inches(1), Inches(1.5), Inches(11), Inches(1.5),
                      num_text, font_size=80, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.CENTER)

        # Section title
        cls._text_box(slide, Inches(1), Inches(3.2), Inches(11), Inches(1),
                      section_title.upper(), font_size=30, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.CENTER)

        # Accent bar
        cls._rect(slide, Inches(5), Inches(4.4), Inches(3.3), Inches(0.05), COLOR_ACCENT)

        # Duration
        if duration:
            cls._text_box(slide, Inches(1), Inches(4.8), Inches(11), Inches(0.5),
                          f"{ICON_CIRCLE}  {duration}", font_size=16,
                          color=COLOR_ACCENT_LIGHT, alignment=PP_ALIGN.CENTER)

    @classmethod
    def _create_content_slide(cls, prs, title, bullet_points, subtitle="",
                              speaker_notes="", section_label="",
                              layout="bullets", icon_char=None):
        """Create a content slide with bullet points and optional 2-column layout."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_WHITE)

        cls._add_slide_header(slide, title, subtitle, section_label)
        cls._add_footer_bar(slide, "CONFIDENTIEL")

        start_y = Inches(1.5) if subtitle else Inches(1.3)

        if layout == "two_columns" and len(bullet_points) >= 4:
            mid = (len(bullet_points) + 1) // 2
            left_bullets = bullet_points[:mid]
            right_bullets = bullet_points[mid:]

            # Left column
            cls._add_bullet_list(slide, Inches(0.6), start_y,
                                 Inches(5.8), Inches(5), left_bullets)
            # Vertical separator
            cls._rect(slide, Inches(6.5), start_y + Inches(0.2),
                      Inches(0.02), Inches(4.5), COLOR_LIGHT_BG)
            # Right column
            cls._add_bullet_list(slide, Inches(6.8), start_y,
                                 Inches(5.8), Inches(5), right_bullets)
        elif layout == "cards" and len(bullet_points) <= 6:
            cls._add_card_layout(slide, start_y, bullet_points, icon_char)
        else:
            cls._add_bullet_list(slide, Inches(0.6), start_y,
                                 Inches(11.5), Inches(5.2), bullet_points)

        cls._add_notes(slide, speaker_notes)

    @classmethod
    def _add_bullet_list(cls, slide, left, top, width, height, bullets):
        """Add a formatted bullet list to a slide."""
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True

        for idx, point in enumerate(bullets):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            if point.strip().startswith("- ") and point.startswith("  "):
                p.text = f"  {ICON_ARROW}  {point.strip()[2:]}"
                p.font.size = Pt(13)
                p.font.color.rgb = COLOR_MUTED
                p.level = 1
                p.space_before = Pt(4)
            else:
                clean = point.lstrip("- ").strip()
                p.text = f"{ICON_DIAMOND}  {clean}"
                p.font.size = Pt(14)
                p.font.color.rgb = COLOR_DARK_TEXT
                p.font.bold = False
                p.level = 0
                p.space_before = Pt(10)

    @classmethod
    def _add_card_layout(cls, slide, start_y, items, icon_char=None):
        """Layout items as card-style blocks."""
        cols = 2 if len(items) <= 4 else 3
        col_width = Inches(11) / cols
        card_h = Inches(1.8)
        x_start = Inches(0.8)
        gap = Inches(0.3)

        icon = icon_char or ICON_DIAMOND

        for i, item in enumerate(items):
            col = i % cols
            row = i // cols
            x = x_start + col * (col_width + gap)
            y = start_y + row * (card_h + gap)

            # Card background
            cls._rounded_rect(slide, x, y, col_width, card_h, COLOR_LIGHT_BG)

            # Icon circle
            icon_colors = [COLOR_SECONDARY, COLOR_ACCENT, COLOR_TEAL,
                           COLOR_SUCCESS, COLOR_PURPLE, COLOR_WARN]
            ic = icon_colors[i % len(icon_colors)]
            circ = cls._oval(slide, x + Inches(0.2), y + Inches(0.3),
                             Inches(0.5), Inches(0.5), ic)
            tf = circ.text_frame
            tf.paragraphs[0].text = icon
            tf.paragraphs[0].font.size = Pt(16)
            tf.paragraphs[0].font.color.rgb = COLOR_WHITE
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE

            # Text
            clean = item.lstrip("- ").strip()
            cls._text_box(slide, x + Inches(0.9), y + Inches(0.2),
                          col_width - Inches(1.2), card_h - Inches(0.4),
                          clean, font_size=12, color=COLOR_DARK_TEXT)

    @classmethod
    def _create_key_figures_slide(cls, prs, title, figures):
        """Create an impactful key figures slide with large numbers."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_WHITE)

        cls._add_slide_header(slide, title)
        cls._add_footer_bar(slide, "CONFIDENTIEL")

        cols = min(len(figures), 4)
        rows = math.ceil(len(figures) / cols)
        box_width = Inches(11) / cols
        start_x = Inches(1)

        colors = [COLOR_SECONDARY, COLOR_TEAL, COLOR_PURPLE, COLOR_WARN,
                  COLOR_ACCENT, COLOR_SUCCESS, COLOR_CORAL, COLOR_PRIMARY]

        for i, fig in enumerate(figures):
            col = i % cols
            row = i // cols
            x = start_x + col * box_width
            y = Inches(1.8) + row * Inches(2.5)

            # Card background
            card_w = box_width - Inches(0.4)
            cls._rounded_rect(slide, x, y, card_w, Inches(2.2), COLOR_LIGHT_BG)

            # Color accent bar at top of card
            color_idx = i % len(colors)
            cls._rect(slide, x, y, card_w, Inches(0.06), colors[color_idx])

            # Value
            cls._text_box(slide, x, y + Inches(0.3), card_w, Inches(0.9),
                          fig.get("value", ""), font_size=40, bold=True,
                          color=colors[color_idx], alignment=PP_ALIGN.CENTER)

            # Separator
            cls._rect(slide, x + Inches(0.5), y + Inches(1.3),
                      card_w - Inches(1), Inches(0.02), colors[color_idx])

            # Label
            cls._text_box(slide, x + Inches(0.2), y + Inches(1.4),
                          card_w - Inches(0.4), Inches(0.7),
                          fig.get("label", ""), font_size=12,
                          color=COLOR_MUTED, alignment=PP_ALIGN.CENTER)

    @classmethod
    def _create_strengths_slide(cls, prs, strengths):
        """Create a strengths slide with numbered cards and icons."""
        # Split into multiple slides if needed (max 5 per slide)
        per_slide = 5
        for page in range(0, len(strengths), per_slide):
            chunk = strengths[page:page + per_slide]
            slide_num = page // per_slide + 1
            total_pages = math.ceil(len(strengths) / per_slide)

            slide = prs.slides.add_slide(prs.slide_layouts[6])
            cls._add_background(slide, COLOR_LIGHT_BG)

            title_suffix = f" ({slide_num}/{total_pages})" if total_pages > 1 else ""
            cls._add_slide_header(slide, f"NOS FORCES{title_suffix}")
            cls._add_footer_bar(slide, "CONFIDENTIEL")

            y = Inches(1.4)
            for i, strength in enumerate(chunk):
                global_idx = page + i

                # Card
                cls._rounded_rect(slide, Inches(0.5), y, Inches(12), Inches(0.9), COLOR_WHITE)

                # Number circle
                colors = [COLOR_SECONDARY, COLOR_TEAL, COLOR_ACCENT,
                          COLOR_SUCCESS, COLOR_PURPLE]
                nc = colors[global_idx % len(colors)]
                circ = cls._oval(slide, Inches(0.7), y + Inches(0.15),
                                 Inches(0.6), Inches(0.6), nc)
                tf = circ.text_frame
                tf.paragraphs[0].text = str(global_idx + 1)
                tf.paragraphs[0].font.size = Pt(18)
                tf.paragraphs[0].font.bold = True
                tf.paragraphs[0].font.color.rgb = COLOR_WHITE
                tf.paragraphs[0].alignment = PP_ALIGN.CENTER
                tf.vertical_anchor = MSO_ANCHOR.MIDDLE

                # Star icon
                cls._text_box(slide, Inches(11.2), y + Inches(0.2),
                              Inches(0.6), Inches(0.5), ICON_STAR,
                              font_size=18, color=COLOR_WARN, alignment=PP_ALIGN.CENTER)

                # Text
                cls._text_box(slide, Inches(1.5), y + Inches(0.15),
                              Inches(9.5), Inches(0.6), strength,
                              font_size=14, color=COLOR_DARK_TEXT)

                y += Inches(1.05)

    @classmethod
    def _create_qa_slide(cls, prs, questions):
        """Create Q&A preparation slides."""
        per_slide = 3
        for page in range(0, len(questions), per_slide):
            chunk = questions[page:page + per_slide]

            slide = prs.slides.add_slide(prs.slide_layouts[6])
            cls._add_background(slide, COLOR_WHITE)

            cls._add_slide_header(slide, "QUESTIONS ANTICIPEES")
            cls._add_footer_bar(slide, "CONFIDENTIEL")

            y = Inches(1.4)
            for i, qa in enumerate(chunk):
                q = qa.get("question", "")
                a = qa.get("answer", "")

                # Question card
                cls._rounded_rect(slide, Inches(0.5), y, Inches(12), Inches(1.6), COLOR_LIGHT_BG)

                # Q icon
                q_circ = cls._oval(slide, Inches(0.7), y + Inches(0.15),
                                   Inches(0.45), Inches(0.45), COLOR_PURPLE)
                tf = q_circ.text_frame
                tf.paragraphs[0].text = "Q"
                tf.paragraphs[0].font.size = Pt(16)
                tf.paragraphs[0].font.bold = True
                tf.paragraphs[0].font.color.rgb = COLOR_WHITE
                tf.paragraphs[0].alignment = PP_ALIGN.CENTER
                tf.vertical_anchor = MSO_ANCHOR.MIDDLE

                # Question text
                cls._text_box(slide, Inches(1.3), y + Inches(0.1),
                              Inches(10.5), Inches(0.5), q,
                              font_size=13, bold=True, color=COLOR_PRIMARY)

                # Answer
                if a:
                    # Truncate long answers
                    display_answer = a[:250] + "..." if len(a) > 250 else a
                    cls._text_box(slide, Inches(1.3), y + Inches(0.65),
                                  Inches(10.5), Inches(0.8),
                                  f"{ICON_ARROW} {display_answer}",
                                  font_size=11, color=COLOR_MUTED)

                y += Inches(1.8)

    @classmethod
    def _create_summary_slide(cls, prs, project_name, strengths, key_messages=None):
        """Create a visual summary/recap slide."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_PRIMARY)

        # Decorative
        cls._oval(slide, cls.SLIDE_W - Inches(3.5), Inches(-1.5),
                  Inches(5), Inches(5), COLOR_SECONDARY)

        cls._text_box(slide, Inches(0.8), Inches(0.5), Inches(10), Inches(0.8),
                      "EN RESUME", font_size=32, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.LEFT)

        cls._rect(slide, Inches(0.8), Inches(1.3), Inches(3), Inches(0.04), COLOR_ACCENT)

        # Key takeaways
        y = Inches(1.8)
        items = strengths[:6] if strengths else []
        for i, item in enumerate(items):
            cls._text_box(slide, Inches(0.8), y, Inches(11), Inches(0.5),
                          f"{ICON_CHECK}  {item}", font_size=15,
                          color=COLOR_WHITE)
            y += Inches(0.6)

        cls._add_footer_bar(slide, "CONFIDENTIEL")

    @classmethod
    def _create_closing_slide(cls, prs, company_name, client_name):
        """Create a professional closing slide."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        cls._add_background(slide, COLOR_PRIMARY)

        # Decorative circles
        cls._oval(slide, Inches(-2), Inches(-2), Inches(6), Inches(6), COLOR_SECONDARY)
        cls._oval(slide, cls.SLIDE_W - Inches(3), cls.SLIDE_H - Inches(3),
                  Inches(5), Inches(5), COLOR_SECONDARY)
        cls._oval(slide, Inches(4), Inches(1), Inches(2), Inches(2), COLOR_ACCENT)

        # Main message
        cls._text_box(slide, Inches(1), Inches(2), Inches(11), Inches(1.2),
                      "MERCI", font_size=56, bold=True,
                      color=COLOR_WHITE, alignment=PP_ALIGN.CENTER)

        cls._rect(slide, Inches(5), Inches(3.3), Inches(3.3), Inches(0.05), COLOR_ACCENT)

        cls._text_box(slide, Inches(1), Inches(3.7), Inches(11), Inches(0.6),
                      "Questions & Echanges", font_size=26,
                      color=COLOR_ACCENT_LIGHT, alignment=PP_ALIGN.CENTER)

        # Contact info
        contact_parts = []
        if company_name:
            contact_parts.append(company_name)
        if client_name:
            contact_parts.append(f"Client : {client_name}")
        if contact_parts:
            cls._text_box(slide, Inches(1), Inches(5.2), Inches(11), Inches(0.5),
                          "  |  ".join(contact_parts), font_size=14,
                          color=COLOR_WHITE, alignment=PP_ALIGN.CENTER)

        # Bottom bar
        cls._rect(slide, Inches(0), cls.SLIDE_H - Inches(0.5),
                  cls.SLIDE_W, Inches(0.5), COLOR_SECONDARY)

    @classmethod
    def generate_presentation(cls, project_name, client_name, company_name,
                              rfp_reference, soutenance_data):
        """Generate a complete soutenance PowerPoint from structured AI data."""
        prs = Presentation()
        prs.slide_width = cls.SLIDE_W
        prs.slide_height = cls.SLIDE_H

        sections = soutenance_data.get("sections", [])
        key_figures = soutenance_data.get("key_figures", [])
        strengths = soutenance_data.get("strengths", [])
        script = soutenance_data.get("script", {})
        qa_prep = script.get("qa_preparation", {})

        # 1. Cover slide
        cls._create_title_slide(prs, project_name, client_name, company_name, rfp_reference)

        # 2. Agenda slide
        cls._create_agenda_slide(prs, sections)

        # 3. Content slides per section
        for sec_idx, section in enumerate(sections, 1):
            section_title = section.get("title", "")
            duration = section.get("duration", "")

            # Section divider
            cls._create_section_divider(prs, sec_idx, section_title, duration)

            # Section content slides
            slides_data = section.get("slides", [])
            for slide_idx, slide_data in enumerate(slides_data):
                bullets = slide_data.get("bullets", [])

                # Choose layout based on content
                layout = "bullets"
                if len(bullets) >= 6 and slide_idx == 0:
                    layout = "two_columns"
                elif len(bullets) <= 4 and all(len(b) < 80 for b in bullets):
                    layout = "cards"

                cls._create_content_slide(
                    prs,
                    title=slide_data.get("title", ""),
                    bullet_points=bullets,
                    subtitle=slide_data.get("subtitle", ""),
                    speaker_notes=slide_data.get("speaker_notes", ""),
                    section_label=section_title,
                    layout=layout,
                )

        # 4. Key figures slide
        if key_figures:
            cls._create_key_figures_slide(prs, "CHIFFRES CLES", key_figures)

        # 5. Strengths slides
        if strengths:
            cls._create_strengths_slide(prs, strengths)

        # 6. Q&A preparation slides
        expected_qs = qa_prep.get("expected_questions", [])
        if expected_qs:
            cls._create_qa_slide(prs, expected_qs)

        # 7. Summary slide
        cls._create_summary_slide(prs, project_name, strengths)

        # 8. Closing slide
        cls._create_closing_slide(prs, company_name, client_name)

        # Save
        file_stream = io.BytesIO()
        prs.save(file_stream)
        file_stream.seek(0)
        return file_stream

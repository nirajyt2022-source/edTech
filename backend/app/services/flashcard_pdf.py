"""
PDF generation service for printable flashcards.

Produces a 2-page A4 PDF:
- Page 1: FRONTS — 3×4 grid, light green background, dashed cut lines
- Page 2: BACKS  — 3×4 grid, light amber background, columns MIRRORED (3,2,1)
           for correct double-sided print alignment

Fonts are registered independently (FlashcardFont / FlashcardFont-Bold)
to avoid conflicts with other PDF services.
"""

import io
import logging
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas as pdf_canvas

logger = logging.getLogger(__name__)

# ── Font registration ────────────────────────────────────────────────────

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fonts")
_NOTO_VARIABLE = os.path.join(_FONT_DIR, "NotoSans-Variable.ttf")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_USE_UNICODE_FONT = False

from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402

if os.path.exists(_NOTO_VARIABLE):
    try:
        pdfmetrics.registerFont(TTFont("FlashcardFont", _NOTO_VARIABLE))
        pdfmetrics.registerFont(TTFont("FlashcardFont-Bold", _NOTO_VARIABLE))
        _USE_UNICODE_FONT = True
    except Exception as e:
        logger.warning("Failed to register Noto Sans font for flashcards: %s", e)

if not _USE_UNICODE_FONT and os.path.exists(_DEJAVU):
    try:
        pdfmetrics.registerFont(TTFont("FlashcardFont", _DEJAVU))
        pdfmetrics.registerFont(TTFont("FlashcardFont-Bold", _DEJAVU_BOLD if os.path.exists(_DEJAVU_BOLD) else _DEJAVU))
        _USE_UNICODE_FONT = True
    except Exception as e:
        logger.warning("Failed to register DejaVu font for flashcards: %s", e)

FONT_REGULAR = "FlashcardFont" if _USE_UNICODE_FONT else "Helvetica"
FONT_BOLD = "FlashcardFont-Bold" if _USE_UNICODE_FONT else "Helvetica-Bold"

# ── Colour palette ────────────────────────────────────────────────────────

_FOREST_GREEN = colors.HexColor("#1B4332")
_AMBER = colors.HexColor("#D97706")
_LIGHT_GREEN_BG = colors.HexColor("#E8F5E9")
_LIGHT_AMBER_BG = colors.HexColor("#FFF8E1")
_MUTED_TEXT = colors.HexColor("#6B7280")
_BODY_TEXT = colors.HexColor("#1F2937")
_DASHED_LINE = colors.HexColor("#9CA3AF")
_WHITE = colors.white

PAGE_WIDTH, PAGE_HEIGHT = A4

# Grid layout: 3 columns × 4 rows
COLS = 3
ROWS = 4
MARGIN_X = 1.5 * cm
MARGIN_Y = 1.5 * cm
HEADER_HEIGHT = 2.0 * cm
FOOTER_HEIGHT = 1.0 * cm

CELL_WIDTH = (PAGE_WIDTH - 2 * MARGIN_X) / COLS
CELL_HEIGHT = (PAGE_HEIGHT - MARGIN_Y - HEADER_HEIGHT - FOOTER_HEIGHT - MARGIN_Y) / ROWS

# Category emoji mapping
_CATEGORY_EMOJI = {
    "concept": "\u2728",  # ✨
    "fact": "\u2139\ufe0f",  # ℹ️
    "formula": "\U0001f4d0",  # 📐
    "question": "\u2753",  # ❓
}


def _get_emoji(category: str) -> str:
    return _CATEGORY_EMOJI.get(category, "\u2728")


def _wrap_text(
    c, text: str, x: float, y: float, max_width: float, font: str, font_size: float, color, max_lines: int = 4
):
    """Draw text with word wrapping within a cell. Returns the y position after drawing."""
    c.setFont(font, font_size)
    c.setFillColor(color)

    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = f"{current_line} {word}".strip()
        if c.stringWidth(test, font, font_size) <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    # Truncate if too many lines
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines[-1]:
            lines[-1] = lines[-1][: max(0, len(lines[-1]) - 3)] + "..."

    leading = font_size * 1.3
    for line in lines:
        c.drawString(x, y, line)
        y -= leading

    return y


class FlashcardPDFService:
    """Generate a 2-page flashcard PDF: fronts + mirrored backs."""

    @staticmethod
    def generate(data: dict) -> bytes:
        """Generate flashcard PDF from a FlashcardSet dict.

        Args:
            data: dict with keys 'title', 'grade', 'subject', 'topic', 'cards'.
                  Each card: {'front', 'back', 'category'}.

        Returns:
            PDF file as bytes.
        """
        buf = io.BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        c.setTitle(f"{data.get('title', 'Flashcards')}")
        c.setAuthor("Skolar")

        cards = data.get("cards", [])
        title = data.get("title", "Flashcards")

        # Pad to 12 if fewer cards provided
        while len(cards) < COLS * ROWS:
            cards.append({"front": "", "back": "", "category": "concept"})

        # Truncate to 12
        cards = cards[: COLS * ROWS]

        # ── Page 1: FRONTS ────────────────────────────────────────────
        _draw_header(c, title, "FRONTS — Print this side first")
        _draw_grid(c, cards, side="front")
        _draw_footer(c)
        c.showPage()

        # ── Page 2: BACKS (columns mirrored for double-sided printing) ─
        _draw_header(c, title, "BACKS — Print on reverse side")
        _draw_grid(c, cards, side="back")
        _draw_footer(c)
        c.showPage()

        c.save()
        return buf.getvalue()


def _draw_header(c, title: str, subtitle: str):
    """Draw page header with title and cut instruction."""
    y = PAGE_HEIGHT - MARGIN_Y

    # Title
    c.setFont(FONT_BOLD, 14)
    c.setFillColor(_FOREST_GREEN)
    c.drawString(MARGIN_X, y - 14, title)

    # Subtitle with scissors icon
    c.setFont(FONT_REGULAR, 9)
    c.setFillColor(_MUTED_TEXT)
    c.drawString(MARGIN_X, y - 28, f"\u2702 {subtitle} \u2014 Cut along dashed lines")

    # Right-aligned branding
    c.setFont(FONT_REGULAR, 8)
    c.drawRightString(PAGE_WIDTH - MARGIN_X, y - 14, "Skolar")


def _draw_footer(c):
    """Draw page footer."""
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(_MUTED_TEXT)
    c.drawCentredString(
        PAGE_WIDTH / 2,
        MARGIN_Y * 0.5,
        "Generated by Skolar \u2014 ed-tech-drab.vercel.app",
    )


def _draw_grid(c, cards: list, side: str):
    """Draw 3×4 grid of cards.

    For 'back' side, columns are mirrored (3,2,1 per row) so that
    when printed double-sided, each back aligns with its front.
    """
    grid_top = PAGE_HEIGHT - MARGIN_Y - HEADER_HEIGHT

    is_front = side == "front"
    bg_color = _LIGHT_GREEN_BG if is_front else _LIGHT_AMBER_BG
    text_color = _FOREST_GREEN if is_front else _BODY_TEXT

    for row in range(ROWS):
        for col in range(COLS):
            # Card index: row-major order
            card_idx = row * COLS + col

            # For backs, mirror columns: col 0→2, 1→1, 2→0
            draw_col = col if is_front else (COLS - 1 - col)

            x = MARGIN_X + draw_col * CELL_WIDTH
            y = grid_top - row * CELL_HEIGHT

            card = cards[card_idx] if card_idx < len(cards) else {"front": "", "back": "", "category": "concept"}
            text = card.get("front", "") if is_front else card.get("back", "")
            category = card.get("category", "concept")

            # Cell background
            c.setFillColor(bg_color)
            c.rect(x, y - CELL_HEIGHT, CELL_WIDTH, CELL_HEIGHT, fill=True, stroke=False)

            # Dashed border
            c.setStrokeColor(_DASHED_LINE)
            c.setLineWidth(0.5)
            c.setDash(3, 3)
            c.rect(x, y - CELL_HEIGHT, CELL_WIDTH, CELL_HEIGHT, fill=False, stroke=True)
            c.setDash()  # Reset to solid

            if not text:
                continue

            # Padding inside cell
            pad = 6 * mm
            inner_x = x + pad
            inner_y = y - pad
            inner_width = CELL_WIDTH - 2 * pad

            # Category emoji (front only)
            if is_front:
                emoji = _get_emoji(category)
                c.setFont(FONT_REGULAR, 8)
                c.setFillColor(_MUTED_TEXT)
                c.drawString(x + 3 * mm, y - 4 * mm - 6, emoji)
                inner_y -= 3 * mm  # shift text down below emoji

            # Card number (small, top-right corner)
            c.setFont(FONT_REGULAR, 7)
            c.setFillColor(_MUTED_TEXT)
            c.drawRightString(x + CELL_WIDTH - 3 * mm, y - 4 * mm - 5, str(card_idx + 1))

            # Main text
            font = FONT_BOLD if is_front else FONT_REGULAR
            font_size = 9.5 if is_front else 8.5
            _wrap_text(c, text, inner_x, inner_y - font_size, inner_width, font, font_size, text_color, max_lines=4)

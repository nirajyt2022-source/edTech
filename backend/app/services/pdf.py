"""PDF generation service for creating premium downloadable worksheets.

Gold-G8: Redesigned to match Pearson/Oxford primary workbook quality.
- Tiered difficulty sections (Foundation / Application / Stretch)
- Name / Date / Score header fields
- Generous margins, clean typography, adequate answer space
- Professional footer with page number + branding
"""

import io
import logging
import os
import re
import tempfile
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ── Register Unicode font (Latin + Devanagari + ₹) ──────────────────────
_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fonts")

_NOTO_DEVANAGARI = os.path.join(_FONT_DIR, "NotoSansDevanagari-Regular.ttf")
_NOTO_DEVANAGARI_BOLD = os.path.join(_FONT_DIR, "NotoSansDevanagari-Bold.ttf")
_NOTO_VARIABLE = os.path.join(_FONT_DIR, "NotoSans-Variable.ttf")
_NOTO_BOLD = os.path.join(_FONT_DIR, "NotoSans-Bold.ttf")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_DEJAVU_OBLIQUE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"

_USE_UNICODE_FONT = False

# Priority 1: Noto Sans Devanagari (best for Hindi conjuncts: क्ष, ज्ञ, श्र, त्र)
if os.path.exists(_NOTO_DEVANAGARI):
    try:
        pdfmetrics.registerFont(TTFont("SkolarFont", _NOTO_DEVANAGARI))
        bold = _NOTO_DEVANAGARI_BOLD if os.path.exists(_NOTO_DEVANAGARI_BOLD) else _NOTO_DEVANAGARI
        pdfmetrics.registerFont(TTFont("SkolarFont-Bold", bold))
        pdfmetrics.registerFont(TTFont("SkolarFont-Italic", _NOTO_DEVANAGARI))  # no italic variant
        registerFontFamily("SkolarFont", normal="SkolarFont", bold="SkolarFont-Bold", italic="SkolarFont-Italic")
        _USE_UNICODE_FONT = True
        logger.info("PDF font: NotoSansDevanagari (full Hindi support)")
    except Exception as e:
        logger.warning("NotoSansDevanagari registration failed: %s", e)

# Priority 2: Noto Sans Variable (Latin + partial Devanagari)
if not _USE_UNICODE_FONT and os.path.exists(_NOTO_VARIABLE):
    try:
        pdfmetrics.registerFont(TTFont("SkolarFont", _NOTO_VARIABLE))
        _bold_path = _NOTO_BOLD if os.path.exists(_NOTO_BOLD) else _NOTO_VARIABLE
        pdfmetrics.registerFont(TTFont("SkolarFont-Bold", _bold_path))
        pdfmetrics.registerFont(TTFont("SkolarFont-Italic", _NOTO_VARIABLE))
        registerFontFamily("SkolarFont", normal="SkolarFont", bold="SkolarFont-Bold", italic="SkolarFont-Italic")
        _USE_UNICODE_FONT = True
        logger.info("PDF font: NotoSans Variable")
    except Exception as e:
        logger.warning("NotoSans Variable registration failed: %s", e)

# Priority 3: DejaVu Sans (Latin only — Hindi WILL break)
if not _USE_UNICODE_FONT and os.path.exists(_DEJAVU):
    try:
        pdfmetrics.registerFont(TTFont("SkolarFont", _DEJAVU))
        pdfmetrics.registerFont(TTFont("SkolarFont-Bold", _DEJAVU_BOLD if os.path.exists(_DEJAVU_BOLD) else _DEJAVU))
        pdfmetrics.registerFont(
            TTFont("SkolarFont-Italic", _DEJAVU_OBLIQUE if os.path.exists(_DEJAVU_OBLIQUE) else _DEJAVU)
        )
        registerFontFamily("SkolarFont", normal="SkolarFont", bold="SkolarFont-Bold", italic="SkolarFont-Italic")
        _USE_UNICODE_FONT = True
        logger.warning("PDF font: DejaVuSans (Hindi conjuncts WILL NOT render correctly)")
    except Exception as e:
        logger.warning("DejaVuSans registration failed: %s", e)

# Final font names used throughout
FONT_REGULAR = "SkolarFont" if _USE_UNICODE_FONT else "Helvetica"
FONT_BOLD = "SkolarFont-Bold" if _USE_UNICODE_FONT else "Helvetica-Bold"
FONT_ITALIC = "SkolarFont-Italic" if _USE_UNICODE_FONT else "Helvetica-Oblique"

# ── HarfBuzz text shaping for Devanagari conjuncts ──────────────────────
# ReportLab doesn't apply OpenType GSUB rules, so conjuncts like क्ष, ज्ञ,
# श्र, त्र render as broken sequences. We use HarfBuzz to shape text into
# proper glyph sequences, then map shaped glyphs to Private Use Area (PUA)
# codepoints that ReportLab can render via the font's glyph table.

_HB_AVAILABLE = False
_hb_font = None
_hb_font_bold = None
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F\u200C\u200D]+(?:[\u0020][\u0900-\u097F\u200C\u200D]+)*")
_PUA_BASE = 0xE000
_next_pua = _PUA_BASE
_gid_to_pua: dict[int, int] = {}

# Determine which font path to use for shaping (must match what ReportLab uses)
_SHAPE_FONT_PATH = None  # type: str | None
_SHAPE_FONT_PATH_BOLD = None  # type: str | None

if _USE_UNICODE_FONT:
    # Pick the font file that was registered as SkolarFont
    for _candidate in [_NOTO_DEVANAGARI, _NOTO_VARIABLE, _DEJAVU]:
        if os.path.exists(_candidate):
            _SHAPE_FONT_PATH = _candidate
            break
    for _candidate_b in [
        _NOTO_DEVANAGARI_BOLD,
        _NOTO_BOLD if os.path.exists(_NOTO_BOLD) else None,
        _SHAPE_FONT_PATH,
    ]:
        if _candidate_b and os.path.exists(_candidate_b):
            _SHAPE_FONT_PATH_BOLD = _candidate_b
            break

if _SHAPE_FONT_PATH:
    try:
        import uharfbuzz as hb

        _blob = hb.Blob.from_file_path(_SHAPE_FONT_PATH)
        _face = hb.Face(_blob)
        _hb_font = hb.Font(_face)
        _HB_AVAILABLE = True
        # Bold font for shaping bold text
        if _SHAPE_FONT_PATH_BOLD and _SHAPE_FONT_PATH_BOLD != _SHAPE_FONT_PATH:
            _blob_b = hb.Blob.from_file_path(_SHAPE_FONT_PATH_BOLD)
            _face_b = hb.Face(_blob_b)
            _hb_font_bold = hb.Font(_face_b)
        else:
            _hb_font_bold = _hb_font
        logger.info("HarfBuzz shaping: enabled (Devanagari conjuncts will render correctly)")
    except ImportError:
        logger.warning("uharfbuzz not installed — Devanagari conjuncts may render incorrectly")
    except Exception as e:
        logger.warning("HarfBuzz init failed: %s — Devanagari conjuncts may render incorrectly", e)


def _shape_devanagari_segment(text: str, bold: bool = False) -> str:
    """Shape a Devanagari text segment using HarfBuzz.

    Returns a string of PUA-mapped characters that ReportLab can render
    as properly shaped glyphs (conjuncts, ligatures, etc.).
    """
    global _next_pua
    import uharfbuzz as hb

    hb_f = _hb_font_bold if bold and _hb_font_bold else _hb_font
    rl_font_name = "SkolarFont-Bold" if bold else "SkolarFont"
    rl_font_obj = pdfmetrics.getFont(rl_font_name)

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_f, buf)

    result = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gid = info.codepoint
        if gid not in _gid_to_pua:
            pua = _next_pua
            _next_pua += 1
            _gid_to_pua[gid] = pua
            # Inject into ALL registered SkolarFont variants
            for fn in ["SkolarFont", "SkolarFont-Bold", "SkolarFont-Italic"]:
                try:
                    f = pdfmetrics.getFont(fn)
                    f.face.charToGlyph[pua] = gid
                    f.face.charWidths[pua] = pos.x_advance
                except Exception as exc:
                    logger.debug("PUA glyph inject skipped for %s: %s", fn, exc)
                    continue
        else:
            # Update width if not yet set for this font variant
            pua = _gid_to_pua[gid]
            try:
                if pua not in rl_font_obj.face.charWidths:
                    rl_font_obj.face.charWidths[pua] = pos.x_advance
            except Exception:
                logger.debug("PUA width update skipped for gid=%d", gid)
        result.append(chr(_gid_to_pua[gid]))
    return "".join(result)


def _shape_text(text: str, bold: bool = False) -> str:
    """Shape all Devanagari segments in text using HarfBuzz.

    Non-Devanagari text (Latin, digits, punctuation) passes through unchanged.
    """
    if not _HB_AVAILABLE or not text:
        return text
    if not any("\u0900" <= c <= "\u097f" for c in text):
        return text

    parts: list[str] = []
    last_end = 0
    for m in _DEVANAGARI_RE.finditer(text):
        if m.start() > last_end:
            parts.append(text[last_end : m.start()])
        parts.append(_shape_devanagari_segment(m.group(), bold=bold))
        last_end = m.end()
    if last_end < len(text):
        parts.append(text[last_end:])
    return "".join(parts)


def _flatten_image_alpha(local_path: str) -> str:
    """Convert RGBA images to RGB with white background and optimize size.

    - Non-alpha RGB images: saved as JPEG quality=75 (60-80% smaller)
    - Alpha images: flattened to RGB, saved as JPEG quality=75
    Returns path to temp file (or original if no conversion needed).
    """
    try:
        from PIL import Image as PILImage

        img = PILImage.open(local_path)
        if img.mode in ("RGBA", "LA", "PA"):
            background = PILImage.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            flat_path = os.path.join(tempfile.gettempdir(), f"skolar_{os.path.basename(local_path)}.jpg")
            background.save(flat_path, "JPEG", quality=75, optimize=True)
            return flat_path
        elif img.mode == "RGB":
            # Already RGB — save as optimized JPEG
            opt_path = os.path.join(tempfile.gettempdir(), f"skolar_{os.path.basename(local_path)}.jpg")
            img.save(opt_path, "JPEG", quality=75, optimize=True)
            return opt_path
        return local_path
    except Exception as e:
        logger.warning("Failed to flatten image alpha for %s: %s", local_path, e)
        return local_path


# ──────────────────────────────────────────────
# Colours — warm, professional palette
# ──────────────────────────────────────────────
_PRIMARY = colors.HexColor("#1E1B4B")  # Skolar indigo
_ACCENT = colors.HexColor("#F97316")  # orange accent
_LIGHT_BG = colors.HexColor("#F8FAFC")  # soft slate bg
_TIER_BG = colors.HexColor("#F1F5F9")  # tier header bg
_MUTED = colors.HexColor("#94A3B8")  # muted slate
_RULE = colors.HexColor("#B0B4BC")  # ruled line colour — print-visible
_HINT_BG = colors.Color(0.95, 0.95, 0.93)  # hint box bg

# Section-specific colours — aligned with web view
_OBJECTIVE_BG = colors.HexColor("#F0FDF4")  # green-50 (learning objectives)
_OBJECTIVE_BORDER = colors.HexColor("#22C55E")  # green-500
_FOCUS_BG = colors.HexColor("#FFFBEB")  # amber-50 (today's focus box)
_FOCUS_BORDER = colors.HexColor("#F59E0B")  # amber-500
_PARENT_BG = colors.HexColor("#FFF7ED")  # orange-50 (parent tip)
_PARENT_BORDER = colors.HexColor("#F97316")  # orange-500

# Tier-specific accent colours
TIER_COLORS = {
    "Foundation": colors.HexColor("#059669"),  # emerald green
    "Application": colors.HexColor("#D97706"),  # amber
    "Stretch": colors.HexColor("#DC2626"),  # red
}


# ──────────────────────────────────────────────
# Unicode → simpler character replacements
# ──────────────────────────────────────────────
_UNICODE_REPLACEMENTS = {
    "\u2014": "-",  # em dash
    "\u2013": "-",  # en dash
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2026": "...",  # ellipsis
    # ×, ÷ are preserved when Unicode font is available (glyphs exist)
    "\u2264": "<=",  # less than or equal (not in NotoSans)
    "\u2265": ">=",  # greater than or equal
    "\u2260": "!=",  # not equal
    "\u25a1": "___",  # white square (blank marker) — wider for writing
    "\u25a2": "___",  # white square with rounded corners
    "\u2610": "___",  # ballot box
    "\u2192": "->",  # right arrow (not in NotoSans)
    "\u2605": "*",  # star (not in NotoSans)
    "\u2b50": "*",  # star emoji
    "\u2713": "[OK]",  # checkmark — safety net if font lacks glyph
}

# Only replace × and ÷ with ASCII when no Unicode font is available
if not _USE_UNICODE_FONT:
    _UNICODE_REPLACEMENTS["\u00d7"] = "x"  # multiplication sign
    _UNICODE_REPLACEMENTS["\u00f7"] = "/"  # division sign
    _UNICODE_REPLACEMENTS["\u20b9"] = "Rs."  # rupee sign


def _sanitize_text(text: str, bold: bool = False) -> str:
    """Normalize special Unicode characters and shape Devanagari for PDF rendering."""
    if not text:
        return ""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Shape Devanagari conjuncts via HarfBuzz (must happen before XML-escape)
    text = _shape_text(text, bold=bold)
    # XML-escape for ReportLab Paragraph (handles &, <, >)
    return xml_escape(text)


# ──────────────────────────────────────────────
# Tier grouping logic
# ──────────────────────────────────────────────
_FOUNDATION_ROLES = {"recognition", "representation"}
_APPLICATION_ROLES = {"application"}
_STRETCH_ROLES = {"error_detection", "thinking"}

_TIER_CONFIG = [
    ("foundation", _FOUNDATION_ROLES, "Foundation", "I can recall and recognise"),
    ("application", _APPLICATION_ROLES, "Application", "I can use what I know"),
    ("stretch", _STRETCH_ROLES, "Stretch", "I can think and reason"),
]

_TIER_CONFIG_HINDI = [
    (
        "foundation",
        _FOUNDATION_ROLES,
        "\u0906\u0927\u093e\u0930",
        "\u092e\u0948\u0902 \u092a\u0939\u091a\u093e\u0928 \u0938\u0915\u0924\u093e/\u0938\u0915\u0924\u0940 \u0939\u0942\u0902",
    ),
    (
        "application",
        _APPLICATION_ROLES,
        "\u0905\u0928\u0941\u092a\u094d\u0930\u092f\u094b\u0917",
        "\u092e\u0948\u0902 \u0907\u0938\u094d\u0924\u0947\u092e\u093e\u0932 \u0915\u0930 \u0938\u0915\u0924\u093e/\u0938\u0915\u0924\u0940 \u0939\u0942\u0902",
    ),
    (
        "stretch",
        _STRETCH_ROLES,
        "\u091a\u0941\u0928\u094c\u0924\u0940",
        "\u092e\u0948\u0902 \u0938\u094b\u091a \u0938\u0915\u0924\u093e/\u0938\u0915\u0924\u0940 \u0939\u0942\u0902",
    ),
]

# Hindi labels for PDF UI chrome
_HINDI_LABELS = {
    "learning_goal": "\u0906\u091c \u0915\u093e \u0905\u0927\u094d\u092f\u092f\u0928 \u0932\u0915\u094d\u0937\u094d\u092f",
    "instructions": "\u0928\u093f\u0930\u094d\u0926\u0947\u0936:",
    "instructions_body": "\u092a\u094d\u0930\u0924\u094d\u092f\u0947\u0915 \u092a\u094d\u0930\u0936\u094d\u0928 \u0915\u094b \u0927\u094d\u092f\u093e\u0928 \u0938\u0947 \u092a\u0922\u093c\u0947\u0902\u0964 \u0926\u0940 \u0917\u0908 \u091c\u0917\u0939 \u092e\u0947\u0902 \u0905\u092a\u0928\u093e \u0915\u093e\u092e \u0926\u093f\u0916\u093e\u090f\u0902\u0964 \u0938\u092d\u0940 \u092a\u094d\u0930\u0936\u094d\u0928\u094b\u0902 \u0915\u0947 \u0909\u0924\u094d\u0924\u0930 \u0926\u0947\u0902\u0964",
    "for_parents": "\u0905\u092d\u093f\u092d\u093e\u0935\u0915\u094b\u0902 \u0915\u0947 \u0932\u093f\u090f:",
    "difficulty": "\u0915\u0920\u093f\u0928\u093e\u0908:",
    "formats": "\u092a\u094d\u0930\u093e\u0930\u0942\u092a:",
    "foundation": "\u0906\u0927\u093e\u0930",
    "application": "\u0905\u0928\u0941\u092a\u094d\u0930\u092f\u094b\u0917",
    "stretch": "\u091a\u0941\u0928\u094c\u0924\u0940",
    "skill_focus": "\u0915\u094c\u0936\u0932 \u092b\u094b\u0915\u0938",
    "spot_success": "\u0938\u092b\u0932\u0924\u093e \u0915\u0940 \u092a\u0939\u091a\u093e\u0928",
    "common_mistake_label": "\u0938\u093e\u092e\u093e\u0928\u094d\u092f \u0917\u0932\u0924\u0940",
    "todays_focus": "\u0906\u091c \u0915\u093e \u092b\u094b\u0915\u0938",
    "skills_tested": "\u092a\u0930\u0940\u0915\u094d\u0937\u093f\u0924 \u0915\u094c\u0936\u0932",
    "answer_verified_high": "\u0938\u092d\u0940 \u0909\u0924\u094d\u0924\u0930 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924",
    "answer_verified_medium": "\u0909\u0924\u094d\u0924\u0930 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924",
    "answer_best_effort": "\u0909\u0924\u094d\u0924\u0930 \u0938\u0930\u094d\u0935\u094b\u0924\u094d\u0924\u092e \u092a\u094d\u0930\u092f\u093e\u0938",
    # Additional labels for full Hindi UI
    "name": "\u0928\u093e\u092e:",
    "date": "\u0926\u093f\u0928\u093e\u0902\u0915:",
    "score": "\u0905\u0902\u0915:",
    "true": "\u0938\u0939\u0940",
    "false": "\u0917\u0932\u0924",
    "answer_label": "\u0909\u0924\u094d\u0924\u0930:",
    "hint": "\u0938\u0902\u0915\u0947\u0924:",
    "answer_key": "\u0909\u0924\u094d\u0924\u0930 \u0915\u0941\u0902\u091c\u0940",
    "explanations": "\u0935\u094d\u092f\u093e\u0916\u094d\u092f\u093e\u090f\u0902",
    "watch_for": "\u0927\u094d\u092f\u093e\u0928 \u0926\u0947\u0902:",
    "bonus_challenge": "\u092c\u094b\u0928\u0938 \u091a\u0941\u0928\u094c\u0924\u0940",
    "bonus_desc": "\u0935\u0948\u0915\u0932\u094d\u092a\u093f\u0915 \u2014 \u0905\u092a\u0928\u0940 \u0938\u094b\u091a \u0915\u094b \u0906\u0917\u0947 \u092c\u0922\u093c\u093e\u0913!",
    "show_working": "\u0905\u092a\u0928\u093e \u0915\u093e\u092e \u0926\u093f\u0916\u093e\u090f\u0902:",
}

_FMT_LABELS_HINDI = {
    "mcq": "\u092c\u0939\u0941\u0935\u093f\u0915\u0932\u094d\u092a\u0940",
    "fill_blank": "\u0930\u093f\u0915\u094d\u0924 \u0938\u094d\u0925\u093e\u0928 \u092d\u0930\u0947\u0902",
    "true_false": "\u0938\u0939\u0940/\u0917\u0932\u0924",
    "short_answer": "\u0932\u0918\u0941 \u0909\u0924\u094d\u0924\u0930",
    "error_spot": "\u0924\u094d\u0930\u0941\u091f\u093f \u0916\u094b\u091c\u0947\u0902",
    "thinking": "\u091a\u093f\u0902\u0924\u0928",
    "match_columns": "\u0938\u0941\u092e\u0947\u0932\u093f\u0924 \u0915\u0930\u0947\u0902",
    "rewrite": "\u092a\u0941\u0928\u0930\u094d\u0932\u0947\u0916\u0928",
    "sentence_completion": "\u0935\u093e\u0915\u094d\u092f \u092a\u0942\u0930\u094d\u0924\u093f",
    "classify": "\u0935\u0930\u094d\u0917\u0940\u0915\u0930\u0923",
}

# Pre-shape all Hindi labels and tier config at module load time
if _HB_AVAILABLE:
    for _k, _v in _HINDI_LABELS.items():
        _HINDI_LABELS[_k] = _shape_text(_v, bold=("label" in _k or _k in ("for_parents", "instructions")))
    for _k2, _v2 in _FMT_LABELS_HINDI.items():
        _FMT_LABELS_HINDI[_k2] = _shape_text(_v2)
    _TIER_CONFIG_HINDI = [
        (key, roles, _shape_text(label, bold=True), _shape_text(desc)) for key, roles, label, desc in _TIER_CONFIG_HINDI
    ]


def _is_hindi(worksheet: dict) -> bool:
    return (worksheet.get("subject") or "").lower() == "hindi"


# Star labels for each tier
_TIER_STARS = {
    "foundation": "*",
    "application": "**",
    "stretch": "***",
}


def _group_questions_by_tier(questions: list, hindi: bool = False) -> list[tuple[str, str, str, list]]:
    """Group questions into Foundation / Application / Stretch tiers.

    Returns list of (tier_key, tier_label, tier_desc, questions) tuples.
    Only includes tiers that have questions. Bonus questions are excluded —
    they are rendered separately by _build_questions().
    """
    normal_questions = [q for q in questions if not q.get("is_bonus") and not q.get("_is_bonus")]
    config = _TIER_CONFIG_HINDI if hindi else _TIER_CONFIG
    tiers = []
    for tier_key, roles, label, desc in config:
        tier_qs = [q for q in normal_questions if q.get("role", "") in roles]
        if tier_qs:
            tiers.append((tier_key, label, desc, tier_qs))

    # If no role data, return all normal questions as a single unnamed tier
    if not tiers:
        return [("all", "", "", normal_questions)]

    return tiers


def _flatten_tier_order(questions: list) -> list:
    """Return questions in the same display order that _build_questions() uses.

    Order: Foundation (recognition/representation) → Application → Stretch
    (error_detection/thinking), with bonus questions appended last (they are
    rendered without a Q-number so they must not be counted in the answer key).

    Passing this list to both _build_questions() and _build_answer_key()
    guarantees that Q1 in the answer key matches Q1 printed on the worksheet.
    """
    tiers = _group_questions_by_tier(questions)
    result: list = []
    for _, _, _, tier_qs in tiers:
        result.extend(tier_qs)
    # Bonus questions are displayed without a number — keep them last
    bonus = [q for q in questions if q.get("is_bonus") or q.get("_is_bonus")]
    result.extend(bonus)
    return result


class PDFService:
    """Service for generating premium PDF worksheets."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        self._page_count = 0
        self._show_hints = True

    def _setup_custom_styles(self):
        """Set up premium paragraph styles."""

        # ── Title ──
        self.styles.add(
            ParagraphStyle(
                name="WorksheetTitle",
                fontName=FONT_BOLD,
                fontSize=20,
                leading=24,
                spaceAfter=4,
                alignment=TA_CENTER,
                textColor=_PRIMARY,
            )
        )

        # ── Subtitle (grade | subject | topic) ──
        self.styles.add(
            ParagraphStyle(
                name="WorksheetSubtitle",
                fontName=FONT_REGULAR,
                fontSize=10,
                textColor=_MUTED,
                alignment=TA_CENTER,
                spaceAfter=16,
            )
        )

        # ── Tier section header ──
        self.styles.add(
            ParagraphStyle(
                name="TierHeader",
                fontName=FONT_BOLD,
                fontSize=11,
                leading=14,
                textColor=_PRIMARY,
                spaceBefore=18,
                spaceAfter=4,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TierDesc",
                fontName=FONT_ITALIC,
                fontSize=8.5,
                textColor=_MUTED,
                spaceAfter=10,
                leftIndent=2,
            )
        )

        # ── Question text ──
        self.styles.add(
            ParagraphStyle(
                name="QuestionText",
                fontName=FONT_REGULAR,
                fontSize=11,
                leading=15,
                spaceAfter=6,
                leftIndent=28,
            )
        )

        # ── Question number ──
        self.styles.add(
            ParagraphStyle(
                name="QuestionNumber",
                fontName=FONT_BOLD,
                fontSize=11,
                leading=15,
                textColor=_PRIMARY,
            )
        )

        # ── Options (MCQ) ──
        self.styles.add(
            ParagraphStyle(
                name="OptionText",
                fontName=FONT_REGULAR,
                fontSize=10,
                leading=13,
                leftIndent=42,
                spaceAfter=2,
            )
        )

        # ── Instructions box ──
        self.styles.add(
            ParagraphStyle(
                name="Instructions",
                fontName=FONT_REGULAR,
                fontSize=9,
                leading=13,
                textColor=colors.Color(0.3, 0.3, 0.3),
                spaceAfter=12,
            )
        )

        # ── Parent tip (Trust P0) ──
        self.styles.add(
            ParagraphStyle(
                name="ParentTip",
                fontName=FONT_REGULAR,
                fontSize=9,
                leading=13,
                textColor=colors.Color(0.2, 0.2, 0.2),
            )
        )

        # ── Header fields (Name/Date/Score) ──
        self.styles.add(
            ParagraphStyle(
                name="HeaderField",
                fontName=FONT_REGULAR,
                fontSize=10,
                leading=13,
            )
        )

        # ── Hint text ──
        self.styles.add(
            ParagraphStyle(
                name="HintText",
                fontName=FONT_ITALIC,
                fontSize=8.5,
                leading=11,
                textColor=_MUTED,
                leftIndent=28,
                spaceAfter=4,
            )
        )

        # ── Learning objective ──
        self.styles.add(
            ParagraphStyle(
                name="ObjectiveTitle",
                fontName=FONT_BOLD,
                fontSize=9.5,
                leading=12,
                textColor=_PRIMARY,
                spaceAfter=4,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="ObjectiveItem",
                fontName=FONT_REGULAR,
                fontSize=9,
                leading=12,
                leftIndent=12,
                textColor=colors.Color(0.25, 0.25, 0.25),
            )
        )

        # ── Answer key ──
        self.styles.add(
            ParagraphStyle(
                name="AnswerKeyTitle",
                fontName=FONT_BOLD,
                fontSize=16,
                leading=22,
                textColor=_PRIMARY,
                spaceBefore=8,
                spaceAfter=10,
                alignment=TA_CENTER,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="AnswerText",
                fontName=FONT_REGULAR,
                fontSize=9,
                leading=12,
                leftIndent=8,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="ExplanationText",
                fontName=FONT_ITALIC,
                fontSize=8.5,
                leading=11,
                leftIndent=8,
                textColor=_MUTED,
            )
        )

        # ── Verification footer (answer key) ──
        self.styles.add(
            ParagraphStyle(
                name="VerificationFooter",
                fontName=FONT_ITALIC,
                fontSize=7,
                textColor=_MUTED,
                alignment=TA_CENTER,
                spaceBefore=4,
            )
        )

        # ── Curriculum badge ──
        self.styles.add(
            ParagraphStyle(
                name="CurriculumBadge",
                fontName=FONT_ITALIC,
                fontSize=8.5,
                textColor=colors.HexColor("#059669"),  # emerald
                alignment=TA_CENTER,
                spaceAfter=4,
            )
        )

    # ──────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────
    def generate_worksheet_pdf(
        self,
        worksheet: dict,
        pdf_type: str = "full",
        show_hints: bool = True,
        watermark: str | None = None,
        encrypt_password: str | None = None,
    ) -> bytes:
        """Generate a premium PDF from a worksheet.

        Args:
            worksheet: Worksheet data with title, questions, etc.
            pdf_type: "full" (questions + answer key), "student" (questions only),
                      "answer_key" (answer key only)
            watermark: Text to draw as diagonal watermark (e.g. "Skolar", "SAMPLE").
                       None means no watermark.
            encrypt_password: If set, encrypt the PDF with this password (for answer keys).

        Returns:
            PDF file as bytes
        """
        self._show_hints = show_hints
        self._watermark = watermark
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2.0 * cm,
            leftMargin=2.0 * cm,
            topMargin=2.0 * cm,
            bottomMargin=2.0 * cm,
            pageCompression=1,
        )

        # Store worksheet metadata for header/footer callbacks
        self._current_worksheet = worksheet
        self._page_count = 0
        self._hindi = _is_hindi(worksheet)
        self._goal_title = _HINDI_LABELS["learning_goal"] if self._hindi else "Today's Learning Goal"

        story = []
        questions = worksheet.get("questions", [])

        # Switch colour palette based on visual_theme
        global _PRIMARY, _ACCENT, _LIGHT_BG
        _theme = (worksheet.get("visual_theme") or "color").lower()
        if _theme == "black_and_white":
            _PRIMARY = colors.Color(0.1, 0.1, 0.1)
            _ACCENT = colors.Color(0.3, 0.3, 0.3)
            _LIGHT_BG = colors.white
        elif _theme == "minimal":
            _PRIMARY = colors.Color(0.2, 0.2, 0.2)
            _ACCENT = colors.Color(0.4, 0.4, 0.4)
            _LIGHT_BG = colors.white
        else:
            # Restore Skolar brand defaults in case a prior call changed them
            _PRIMARY = colors.HexColor("#1E1B4B")
            _ACCENT = colors.HexColor("#F97316")
            _LIGHT_BG = colors.HexColor("#F8FAFC")

        # Compute display order once — tier-sorted (Foundation → Application →
        # Stretch), bonus last.  Both _build_questions and _build_answer_key
        # must iterate the *same* list so Q-numbers stay in sync.
        display_questions = _flatten_tier_order(questions)

        if pdf_type == "answer_key":
            self._build_answer_key(story, worksheet, display_questions)
        else:
            self._build_questions(story, worksheet, display_questions)
            if pdf_type == "full" and display_questions:
                story.append(PageBreak())
                self._build_answer_key(story, worksheet, display_questions)

        doc.build(
            story,
            onFirstPage=self._draw_page_furniture,
            onLaterPages=self._draw_page_furniture,
        )
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()

        # Optional password encryption (for answer key PDFs)
        if encrypt_password:
            try:
                from PyPDF2 import PdfReader, PdfWriter

                reader = PdfReader(io.BytesIO(pdf_bytes))
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                writer.encrypt(user_password=encrypt_password, owner_password=encrypt_password)
                enc_buffer = io.BytesIO()
                writer.write(enc_buffer)
                pdf_bytes = enc_buffer.getvalue()
            except Exception as e:
                logger.warning("PDF encryption failed, returning unencrypted: %s", e)

        return pdf_bytes

    # ──────────────────────────────────────────
    # Page furniture (header rule + footer)
    # ──────────────────────────────────────────
    def _draw_page_furniture(self, canvas, doc):
        """Draw footer with page number and branding on every page."""
        canvas.saveState()
        page_width, page_height = A4
        self._page_count += 1

        # ── Watermark (drawn first, behind content) ──
        watermark = getattr(self, "_watermark", None)
        if watermark:
            canvas.saveState()
            canvas.setFont(FONT_BOLD, 54)
            canvas.setFillColor(colors.Color(0.7, 0.7, 0.7, alpha=0.35))
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, watermark)
            canvas.restoreState()

        # ── Top rule line ──
        canvas.setStrokeColor(_PRIMARY)
        canvas.setLineWidth(1.5)
        canvas.line(2.0 * cm, page_height - 1.6 * cm, page_width - 2.0 * cm, page_height - 1.6 * cm)

        # ── Footer ──
        y_footer = 1.0 * cm

        # Left: branding
        canvas.setFont(FONT_REGULAR, 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(2.0 * cm, y_footer, "Generated by Skolar")

        # Right: page number
        canvas.drawRightString(page_width - 2.0 * cm, y_footer, f"Page {self._page_count}")

        # Footer rule line
        canvas.setStrokeColor(_RULE)
        canvas.setLineWidth(0.5)
        canvas.line(2.0 * cm, y_footer + 10, page_width - 2.0 * cm, y_footer + 10)

        canvas.restoreState()

    # ──────────────────────────────────────────
    # Questions section
    # ──────────────────────────────────────────
    def _build_questions(self, story: list, worksheet: dict, questions: list) -> None:
        """Build the questions section with tiered layout."""

        # ── Title ──
        title = _sanitize_text(worksheet.get("title", "Practice Worksheet"))
        story.append(Paragraph(title, self.styles["WorksheetTitle"]))

        # ── Subtitle (grade | subject | topic) ──
        subtitle_parts = []
        if worksheet.get("grade"):
            subtitle_parts.append(worksheet["grade"])
        if worksheet.get("subject"):
            subtitle_parts.append(worksheet["subject"])
        if worksheet.get("topic"):
            subtitle_parts.append(worksheet["topic"])
        if subtitle_parts:
            subtitle = _sanitize_text("  |  ".join(subtitle_parts))
            story.append(Paragraph(subtitle, self.styles["WorksheetSubtitle"]))

        # ── NCERT Curriculum badge ──
        chapter_ref = worksheet.get("chapter_ref")
        if chapter_ref:
            story.append(
                Paragraph(
                    f"<i>Aligned to NCERT \u2014 {_sanitize_text(chapter_ref)}</i>",
                    self.styles["CurriculumBadge"],
                )
            )

        story.append(Spacer(1, 4))

        # ── Learning Objectives (Gold-G5) ──
        objectives = worksheet.get("learning_objectives", [])
        if objectives:
            self._build_learning_objectives(story, objectives)
            story.append(Spacer(1, 6))

        # ── Today's Focus (Trust S2.1) ──
        self._build_todays_focus(story, worksheet)

        # ── Skill coverage one-liner (Trust S2.1) ──
        skill_coverage = worksheet.get("skill_coverage")
        if skill_coverage:
            _sc_label = _HINDI_LABELS["skills_tested"] if self._hindi else "Skills tested"
            sc_parts = [f"{_sanitize_text(skill)} ({count})" for skill, count in skill_coverage.items()]
            story.append(
                Paragraph(
                    f"<font size='8' color='#6B7280'><b>{_sc_label}:</b> {' | '.join(sc_parts)}</font>",
                    self.styles["AnswerText"],
                )
            )
            story.append(Spacer(1, 6))

        # ── Parent Tip (Trust P0) ──
        parent_tip = worksheet.get("parent_tip", "")
        if parent_tip:
            page_w = A4[0] - 4.0 * cm
            tip_table = Table(
                [
                    [
                        Paragraph(
                            f"<b>{_HINDI_LABELS['for_parents'] if self._hindi else 'For Parents:'}</b> {_sanitize_text(parent_tip)}",
                            self.styles["ParentTip"],
                        )
                    ]
                ],
                colWidths=[page_w],
            )
            tip_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), _PARENT_BG),
                        ("BOX", (0, 0), (-1, -1), 0.5, _PARENT_BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ]
                )
            )
            story.append(tip_table)
            story.append(Spacer(1, 6))

        # ── Name / Date / Score header fields ──
        self._build_header_fields(story, worksheet, questions)

        story.append(Spacer(1, 6))

        # ── Instructions ──
        story.append(
            Paragraph(
                f"<b>{_HINDI_LABELS['instructions']}</b> {_HINDI_LABELS['instructions_body']}"
                if self._hindi
                else "<b>Instructions:</b> Read each question carefully. "
                "Show your working in the space provided. Answer all questions.",
                self.styles["Instructions"],
            )
        )

        # ── Thin separator ──
        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=_RULE,
                spaceBefore=2,
                spaceAfter=12,
            )
        )

        # ── Group questions by tier and render ──
        tiers = _group_questions_by_tier(questions, hindi=self._hindi)
        q_number = 1  # continuous question numbering across tiers

        _TIER_COLORS_BY_KEY = {
            "foundation": TIER_COLORS["Foundation"],
            "application": TIER_COLORS["Application"],
            "stretch": TIER_COLORS["Stretch"],
        }
        for tier_key, tier_label, tier_desc, tier_qs in tiers:
            if tier_label:
                stars = _TIER_STARS.get(tier_key, "")
                tier_color = _TIER_COLORS_BY_KEY.get(tier_key, _PRIMARY)
                # Colored indicator line before tier header
                story.append(
                    HRFlowable(
                        width="20%",
                        thickness=2.5,
                        color=tier_color,
                        spaceBefore=14,
                        spaceAfter=2,
                        hAlign="LEFT",
                    )
                )
                story.append(Paragraph(f"{stars}  {tier_label}", self.styles["TierHeader"]))
                story.append(Paragraph(tier_desc, self.styles["TierDesc"]))

            for question in tier_qs:
                elements = self._build_single_question(
                    question, q_number, tier_key, subject=worksheet.get("subject", "")
                )
                # KeepTogether prevents a question from breaking across pages
                story.append(KeepTogether(elements))
                story.append(Spacer(1, 6))
                q_number += 1

        # ── Bonus Challenge questions ──
        bonus_questions = [q for q in questions if q.get("is_bonus") or q.get("_is_bonus")]
        if bonus_questions:
            story.append(Spacer(1, 8))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=1.0,
                    color=_ACCENT,
                    spaceBefore=4,
                    spaceAfter=8,
                )
            )
            _bonus_title = _HINDI_LABELS["bonus_challenge"] if self._hindi else "Bonus Challenge"
            _bonus_desc = _HINDI_LABELS["bonus_desc"] if self._hindi else "Optional — stretch your thinking!"
            story.append(Paragraph(f"*  {_bonus_title}", self.styles["TierHeader"]))
            story.append(Paragraph(_bonus_desc, self.styles["TierDesc"]))
            for question in bonus_questions:
                elements = self._build_bonus_question(question)
                story.append(KeepTogether(elements))
                story.append(Spacer(1, 6))

    def _build_header_fields(self, story: list, worksheet: dict, questions: list) -> None:
        """Build Name / Date / Score fields as a table row."""
        num_q = len(questions)
        page_width = A4[0] - 4.0 * cm  # usable width with 2cm margins

        _name = _HINDI_LABELS["name"] if self._hindi else "Name:"
        _date = _HINDI_LABELS["date"] if self._hindi else "Date:"
        _score = _HINDI_LABELS["score"] if self._hindi else "Score:"
        row_data = [
            [
                Paragraph(f"{_name} ____________________________", self.styles["HeaderField"]),
                Paragraph(f"{_date} ______________", self.styles["HeaderField"]),
                Paragraph(f"{_score} _____ / {num_q}", self.styles["HeaderField"]),
            ]
        ]

        col_w1 = page_width * 0.50
        col_w2 = page_width * 0.28
        col_w3 = page_width * 0.22

        header_table = Table(row_data, colWidths=[col_w1, col_w2, col_w3])
        header_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
                ]
            )
        )
        story.append(header_table)

    def _build_learning_objectives(self, story: list, objectives: list[str]) -> None:
        """Render a learning objective box at the top of the worksheet."""
        page_width = A4[0] - 4.0 * cm

        # Build content: title + bullet items
        obj_elements = []
        obj_elements.append(Paragraph(self._goal_title, self.styles["ObjectiveTitle"]))
        for obj in objectives:
            obj_elements.append(
                Paragraph(f"<bullet>&#10003;</bullet> {_sanitize_text(obj)}", self.styles["ObjectiveItem"])
            )

        # Wrap in a single-cell table for the bordered box
        obj_table = Table(
            [[obj_elements]],
            colWidths=[page_width - 1.0 * cm],
        )
        obj_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _OBJECTIVE_BG),
                    ("BOX", (0, 0), (-1, -1), 0.5, _OBJECTIVE_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(obj_table)

    def _build_todays_focus(self, story: list, worksheet: dict) -> None:
        """Render a light-green Today's Focus box with skill focus, success indicator, and common mistake."""
        skill_focus = worksheet.get("skill_focus", "")
        common_mistake = worksheet.get("common_mistake", "")
        objectives = worksheet.get("learning_objectives", [])

        if not skill_focus and not common_mistake:
            return  # Nothing to show

        page_width = A4[0] - 4.0 * cm
        focus_elements = []

        _hl = _HINDI_LABELS if self._hindi else None
        focus_title = _hl["todays_focus"] if _hl else "Today's Focus"
        focus_elements.append(Paragraph(f"<b>{focus_title}</b>", self.styles["ObjectiveTitle"]))

        if skill_focus:
            _sf_label = _hl["skill_focus"] if _hl else "Skill Focus"
            focus_elements.append(
                Paragraph(
                    f"<bullet>&bull;</bullet> <b>{_sf_label}:</b> {_sanitize_text(skill_focus)}",
                    self.styles["ObjectiveItem"],
                )
            )

        if objectives:
            _ss_label = _hl["spot_success"] if _hl else "How to Spot Success"
            focus_elements.append(
                Paragraph(
                    f"<bullet>&bull;</bullet> <b>{_ss_label}:</b> Your child can {_sanitize_text(objectives[0]).lower()}",
                    self.styles["ObjectiveItem"],
                )
            )

        if common_mistake:
            _cm_label = _hl["common_mistake_label"] if _hl else "Common Mistake"
            focus_elements.append(
                Paragraph(
                    f"<bullet>&bull;</bullet> <b>{_cm_label}:</b> {_sanitize_text(common_mistake)}",
                    self.styles["ObjectiveItem"],
                )
            )

        focus_table = Table(
            [[focus_elements]],
            colWidths=[page_width - 1.0 * cm],
        )
        focus_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _FOCUS_BG),
                    ("BOX", (0, 0), (-1, -1), 0.5, _FOCUS_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(focus_table)
        story.append(Spacer(1, 6))

    def _build_single_question(self, question: dict, number: int, tier_key: str = "all", subject: str = "") -> list:
        """Build elements for a single question. Returns list of flowables."""
        import re as _re

        elements = []
        # Prefer the render format field; fall back to legacy type field
        q_type = question.get("format", question.get("type", "short_answer"))
        q_text = _sanitize_text(question.get("text", ""))

        # Star badge based on tier
        star_badge = ""
        if tier_key == "foundation":
            star_badge = " *"
        elif tier_key == "application":
            star_badge = " **"
        elif tier_key == "stretch":
            star_badge = " ***"

        # Difficulty label (muted, small)
        difficulty = question.get("difficulty", "")
        diff_label = ""
        if difficulty:
            diff_label = f"  <font size='6.5' color='#{_MUTED.hexval()[2:]}'>[{difficulty.capitalize()}]</font>"

        # Question text with number + star badge + difficulty label
        # For vertical_sum, suppress the question text header and render the sum directly
        if q_type != "vertical_sum":
            elements.append(
                Paragraph(
                    f"<b><font color='#{_PRIMARY.hexval()[2:]}'>{number}.</font></b>"
                    f"<font size='7' color='#{_ACCENT.hexval()[2:]}'>{star_badge}</font>"
                    f"{diff_label}  {q_text}",
                    self.styles["QuestionText"],
                )
            )

        # ── Cartoon images (EVS/Science) — horizontal row, max 2 ─────────────
        raw_images = question.get("images", []) or []
        if raw_images:
            import os

            from reportlab.platypus import Image as RLImage

            img_cells = []
            for img in raw_images[:2]:
                img_path = img.get("path", "")
                local_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "data", "images", img_path.removeprefix("/images/")
                )
                if os.path.exists(local_path):
                    try:
                        flat_path = _flatten_image_alpha(local_path)
                        img_cells.append(RLImage(flat_path, width=1.8 * cm, height=1.8 * cm, kind="proportional"))
                    except Exception as e:
                        logger.warning("Failed to embed image %s in PDF: %s", img_path, e)

            if img_cells:
                elements.append(Spacer(1, 3))
                if len(img_cells) == 1:
                    elements.append(img_cells[0])
                else:
                    col_width = 2.2 * cm
                    img_table = Table(
                        [img_cells],
                        colWidths=[col_width] * len(img_cells),
                    )
                    img_table.setStyle(
                        TableStyle(
                            [
                                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                            ]
                        )
                    )
                    elements.append(img_table)
                elements.append(Spacer(1, 3))

        # ── Answer area by render format ──────────────────────────────────────

        if q_type in ("mcq_3", "mcq_4", "multiple_choice") and question.get("options"):
            # Options list with A/B/C/D labels
            for j, option in enumerate(question["options"]):
                letter = chr(65 + j)
                elements.append(
                    Paragraph(
                        f"<font color='#{_PRIMARY.hexval()[2:]}'>{letter})</font>  {_sanitize_text(str(option))}",
                        self.styles["OptionText"],
                    )
                )
            elements.append(Spacer(1, 3))

        elif q_type in ("mcq_3", "mcq_4"):
            # MCQ requested but options not in question dict — render a blank choice area
            num_opts = 4 if q_type == "mcq_4" else 3
            for j in range(num_opts):
                letter = chr(65 + j)
                elements.append(
                    Paragraph(
                        f"<font color='#{_PRIMARY.hexval()[2:]}'>{letter})</font>  ______________________________",
                        self.styles["OptionText"],
                    )
                )
            elements.append(Spacer(1, 3))

        elif q_type == "vertical_sum":
            # ── Stacked column arithmetic layout ─────────────────────────────
            # Parse "47 + 35" or "84 - 29" or "6 x 7" from question_text
            _vs_match = _re.search(
                r"(\d+)\s*([+\-\u00d7\u00f7x])\s*(\d+)",
                q_text,
            )
            _px = _PRIMARY.hexval()[2:]
            _ac = _ACCENT.hexval()[2:]
            if _vs_match:
                _a = _vs_match.group(1)
                _op = _vs_match.group(2)
                _b = _vs_match.group(3)
            else:
                # Fallback: show the raw question text and ruled lines
                elements.append(
                    Paragraph(
                        f"<b><font color='#{_px}'>{number}.</font></b>"
                        f"<font size='7' color='#{_ac}'>{star_badge}</font>  {q_text}",
                        self.styles["QuestionText"],
                    )
                )
                elements.append(Spacer(1, 6))
                for _ in range(2):
                    elements.append(
                        HRFlowable(
                            width="40%",
                            thickness=0.3,
                            color=_RULE,
                            spaceBefore=10,
                            spaceAfter=0,
                            hAlign="LEFT",
                        )
                    )
                elements.append(Spacer(1, 4))
                return elements

            # Build question header with number badge
            elements.append(
                Paragraph(
                    f"<b><font color='#{_px}'>{number}.</font></b><font size='7' color='#{_ac}'>{star_badge}</font>",
                    self.styles["QuestionNumber"],
                )
            )

            # Stacked sum using a narrow right-aligned Table
            from reportlab.lib.enums import TA_RIGHT as _TA_RIGHT
            from reportlab.lib.styles import ParagraphStyle as _PS

            _vs_style = _PS(
                "VSNum",
                fontName=FONT_BOLD,
                fontSize=14,
                leading=18,
                alignment=_TA_RIGHT,
            )
            _col_w = 3.5 * cm
            _vs_table = Table(
                [
                    [Paragraph(f"  {_a}", _vs_style)],
                    [Paragraph(f"{_op} {_b}", _vs_style)],
                ],
                colWidths=[_col_w],
            )
            _vs_table.setStyle(
                TableStyle(
                    [
                        ("LINEBELOW", (0, 1), (-1, 1), 1.2, colors.black),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ]
                )
            )
            elements.append(_vs_table)
            # Answer blank below the rule
            elements.append(
                HRFlowable(
                    width=f"{_col_w}",
                    thickness=0.3,
                    color=_RULE,
                    spaceBefore=8,
                    spaceAfter=0,
                    hAlign="LEFT",
                )
            )
            elements.append(Spacer(1, 6))

        elif q_type == "true_false":
            _px = _PRIMARY.hexval()[2:]
            _true = _HINDI_LABELS["true"] if self._hindi else "True"
            _false = _HINDI_LABELS["false"] if self._hindi else "False"
            elements.append(Paragraph(f"<font color='#{_px}'>A)</font>  {_true}", self.styles["OptionText"]))
            elements.append(Paragraph(f"<font color='#{_px}'>B)</font>  {_false}", self.styles["OptionText"]))
            elements.append(Spacer(1, 3))

        elif q_type == "fill_blank":
            # Single answer line with box-style underline
            elements.append(Spacer(1, 4))
            _ans = _HINDI_LABELS["answer_label"] if self._hindi else "Ans:"
            elements.append(Paragraph(f"{_ans} ________________________________________", self.styles["OptionText"]))
            elements.append(Spacer(1, 6))

        else:
            # Determine answer line count based on question complexity
            role = question.get("role", "")
            q_actual_type = question.get("type", "")

            if role in ("thinking", "error_detection") or q_actual_type in ("word_problem", "error_detection"):
                num_lines = 4  # More space for reasoning/explanation
            elif q_actual_type == "short_answer" and role == "application":
                num_lines = 2  # Medium answer
            else:
                num_lines = 2  # Default: short factual answer

            elements.append(Spacer(1, 6))
            for _ in range(num_lines):
                elements.append(
                    HRFlowable(
                        width="85%",
                        thickness=0.3,
                        color=_RULE,
                        spaceBefore=7,
                        spaceAfter=0,
                        hAlign="LEFT",
                    )
                )
            elements.append(Spacer(1, 4))

        # Hint — only if show_hints is enabled
        if self._show_hints:
            hint = question.get("hint") or question.get("explanation")
            if hint:
                hint_text = _sanitize_text(hint)
                _hint_label = _HINDI_LABELS["hint"] if self._hindi else "Hint:"
                elements.append(Paragraph(f"<i>{_hint_label} {hint_text}</i>", self.styles["HintText"]))

        # ── Working area (maths subjects, medium/hard difficulty) ─────────
        if subject.lower() in ("maths", "mathematics", "math"):
            difficulty = question.get("difficulty", "")
            role = question.get("role", "")
            # Skip easy recognition Qs — they don't need working space
            if difficulty.lower() in ("medium", "hard") or role in ("thinking", "error_detection"):
                elements.append(Spacer(1, 6))
                elements.append(
                    Paragraph(
                        f"<i>{_HINDI_LABELS['show_working'] if self._hindi else 'Show your working:'}</i>",
                        self.styles["HintText"],
                    )
                )
                elements.append(Spacer(1, 4))
                elements.append(
                    HRFlowable(
                        width="70%",
                        thickness=0.3,
                        color=_MUTED,
                        dash=(2, 3),
                        spaceBefore=2,
                        spaceAfter=2,
                    )
                )
                elements.append(Spacer(1, 14))

        return elements

    def _build_bonus_question(self, question: dict) -> list:
        """Build elements for a bonus challenge question with a framed box."""
        elements = []
        q_text = _sanitize_text(question.get("text", ""))

        # Question text paragraph
        q_para = Paragraph(
            f"<b><font color='#{_ACCENT.hexval()[2:]}'>BONUS:</font></b>  {q_text}", self.styles["QuestionText"]
        )

        # Three answer lines
        answer_lines = [Spacer(1, 6)]
        for _ in range(3):
            answer_lines.append(
                HRFlowable(
                    width="85%",
                    thickness=0.3,
                    color=_RULE,
                    spaceBefore=10,
                    spaceAfter=0,
                    hAlign="LEFT",
                )
            )
        answer_lines.append(Spacer(1, 4))

        # Wrap in a Table with a dashed-style amber border
        page_width = A4[0] - 4.0 * cm
        inner = [q_para] + answer_lines
        box_table = Table([[inner]], colWidths=[page_width])
        box_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.2, _ACCENT),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.Color(1.0, 0.97, 0.88)),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(box_table)
        return elements

    # ──────────────────────────────────────────
    # Answer key section
    # ──────────────────────────────────────────
    def _build_answer_key(self, story: list, worksheet: dict, questions: list) -> None:
        """Build a clean answer key section."""
        # Prominent divider before the answer key
        story.append(Spacer(1, 10))
        story.append(
            HRFlowable(
                width="100%",
                thickness=2.0,
                color=_PRIMARY,
                spaceBefore=6,
                spaceAfter=8,
            )
        )

        title = _sanitize_text(worksheet.get("title", "Practice Worksheet"))
        _ak_label = _HINDI_LABELS["answer_key"] if self._hindi else "Answer Key"
        story.append(Paragraph(f"{title} - {_ak_label}", self.styles["AnswerKeyTitle"]))

        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=_PRIMARY,
                spaceBefore=2,
                spaceAfter=14,
            )
        )

        # Difficulty breakdown (Trust P3)
        _foundation_roles = {"recognition", "representation"}
        _application_roles = {"application"}
        _stretch_roles = {"error_detection", "thinking"}
        f_count = sum(1 for q in questions if q.get("role") in _foundation_roles)
        a_count = sum(1 for q in questions if q.get("role") in _application_roles)
        s_count = sum(1 for q in questions if q.get("role") in _stretch_roles)
        if f_count + a_count + s_count > 0:
            _hl = _HINDI_LABELS if self._hindi else None
            parts = []
            if f_count:
                parts.append(f"\u2605 {_hl['foundation'] if _hl else 'Foundation'}: {f_count}")
            if a_count:
                parts.append(f"\u2605\u2605 {_hl['application'] if _hl else 'Application'}: {a_count}")
            if s_count:
                parts.append(f"\u2605\u2605\u2605 {_hl['stretch'] if _hl else 'Stretch'}: {s_count}")
            _diff_label = _hl["difficulty"] if _hl else "Difficulty:"
            story.append(
                Paragraph(
                    f"<font size='8' color='#{_MUTED.hexval()[2:]}'>{_diff_label} {' &nbsp;|&nbsp; '.join(parts)}</font>",
                    self.styles["AnswerText"],
                )
            )
            story.append(Spacer(1, 8))

        # Format diversity (Trust P4)
        _fmt_labels_en = {
            "mcq": "MCQ",
            "fill_blank": "Fill in the Blank",
            "true_false": "True/False",
            "short_answer": "Short Answer",
            "word_problem": "Word Problem",
            "error_spot": "Error Spot",
            "column_setup": "Column Sum",
            "missing_number": "Missing Number",
            "place_value": "Place Value",
            "thinking": "Thinking",
            "match_columns": "Match Columns",
        }
        _active_fmt = _FMT_LABELS_HINDI if self._hindi else _fmt_labels_en
        fmt_counts: dict[str, int] = {}
        for q in questions:
            t = q.get("type", "short_answer")
            fmt_counts[t] = fmt_counts.get(t, 0) + 1
        if len(fmt_counts) > 1:
            fmt_parts = [f"{_active_fmt.get(k, k.replace('_', ' '))}: {v}" for k, v in fmt_counts.items()]
            _fmt_heading = _HINDI_LABELS["formats"] if self._hindi else "Formats:"
            story.append(
                Paragraph(
                    f"<font size='8' color='#{_MUTED.hexval()[2:]}'>{_fmt_heading} {' &nbsp;|&nbsp; '.join(fmt_parts)}</font>",
                    self.styles["AnswerText"],
                )
            )
            story.append(Spacer(1, 8))

        # Answer grid — 3 columns
        answer_data = []
        row = []
        for i, question in enumerate(questions, 1):
            answer = question.get("correct_answer", "N/A")
            if isinstance(answer, list):
                answer = ", ".join(str(a) for a in answer)
            skill_tag = question.get("skill_tag", "")
            tag_suffix = (
                f"  <font size='7' color='#{_MUTED.hexval()[2:]}'>[{skill_tag.replace('_', ' ')}]</font>"
                if skill_tag
                else ""
            )
            verified = question.get("verified", True)
            v_icon = "\u2713" if verified else "!"
            v_color = "228B22" if verified else "D97706"
            v_prefix = f"<font size='8' color='#{v_color}'>{v_icon}</font> "
            row.append(
                Paragraph(
                    f"{v_prefix}<b>Q{i}:</b> {_sanitize_text(str(answer))}{tag_suffix}", self.styles["AnswerText"]
                )
            )
            if len(row) == 3:
                answer_data.append(row)
                row = []
        if row:
            while len(row) < 3:
                row.append("")
            answer_data.append(row)

        if answer_data:
            page_width = A4[0] - 4.0 * cm
            col_w = page_width / 3
            answer_table = Table(answer_data, colWidths=[col_w] * 3)
            answer_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.4, _RULE),
                        # Alternate row shading
                        *[("BACKGROUND", (0, r), (-1, r), _LIGHT_BG) for r in range(0, len(answer_data), 2)],
                    ]
                )
            )
            story.append(answer_table)

        # Explanations
        has_explanations = any(q.get("explanation") for q in questions)
        if has_explanations:
            story.append(Spacer(1, 18))
            _expl = _HINDI_LABELS["explanations"] if self._hindi else "Explanations"
            story.append(Paragraph(f"<b>{_expl}</b>", self.styles["AnswerKeyTitle"]))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.3,
                    color=_RULE,
                    spaceBefore=2,
                    spaceAfter=10,
                )
            )

            for i, question in enumerate(questions, 1):
                explanation = question.get("explanation")
                if explanation:
                    story.append(
                        Paragraph(f"<b>Q{i}:</b> {_sanitize_text(explanation)}", self.styles["ExplanationText"])
                    )
                    story.append(Spacer(1, 4))

        # ── Common Mistake callout (Trust P0) ──
        common_mistake = worksheet.get("common_mistake", "")
        if common_mistake:
            story.append(Spacer(1, 12))
            page_w = A4[0] - 4.0 * cm
            cm_table = Table(
                [
                    [
                        Paragraph(
                            f"<b>{_HINDI_LABELS['watch_for'] if self._hindi else 'Watch For:'}</b> {_sanitize_text(common_mistake)}",
                            self.styles["ParentTip"],
                        )
                    ]
                ],
                colWidths=[page_w],
            )
            cm_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DC2626")),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ]
                )
            )
            story.append(cm_table)

        # ── Skills Tested (Trust P0) ──
        skill_coverage = worksheet.get("skill_coverage")
        if skill_coverage:
            story.append(Spacer(1, 12))
            story.append(Paragraph("<b>Skills Tested</b>", self.styles["AnswerKeyTitle"]))
            story.append(HRFlowable(width="100%", thickness=0.3, color=_RULE, spaceBefore=2, spaceAfter=6))
            skill_text = "  |  ".join(f"{_sanitize_text(skill)} ({count})" for skill, count in skill_coverage.items())
            story.append(Paragraph(skill_text, self.styles["AnswerText"]))

        # ── Verification footer ──
        story.append(Spacer(1, 24))
        story.append(HRFlowable(width="100%", thickness=0.3, color=_RULE, spaceBefore=4, spaceAfter=6))
        quality_tier = worksheet.get("_quality_tier", "high")
        if self._hindi:
            _hl = _HINDI_LABELS
            if quality_tier == "high":
                badge_text = f"\u2713 {_hl['answer_verified_high']}"
            elif quality_tier == "medium":
                badge_text = f"\u2713 {_hl['answer_verified_medium']}"
            else:
                badge_text = _hl["answer_best_effort"]
        else:
            if quality_tier == "high":
                badge_text = "\u2713 All answers verified by deterministic solver  |  Quality: High"
            elif quality_tier == "medium":
                badge_text = "\u2713 Answers verified where possible  |  Quality: Standard"
            else:
                badge_text = "Best-effort answers \u2014 please verify"
        story.append(Paragraph(badge_text, self.styles["VerificationFooter"]))


def get_pdf_service() -> PDFService:
    return PDFService()

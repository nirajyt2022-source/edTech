"""PDF generation service for creating premium downloadable worksheets.

Gold-G8: Redesigned to match Pearson/Oxford primary workbook quality.
- Tiered difficulty sections (Foundation / Application / Stretch)
- Name / Date / Score header fields
- Generous margins, clean typography, adequate answer space
- Professional footer with page number + branding
"""

from __future__ import annotations

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

    # ── Visual rendering methods ───────────────────────────────────────────
    def _build_visual(self, visual_type: str, visual_data: dict, page_width: float) -> list:
        """Render a visual element and return ReportLab flowables."""
        if not visual_data:
            return []

        try:
            if visual_type == "object_group":
                return self._draw_object_group(visual_data, page_width)
            elif visual_type == "pie_fraction":
                return self._draw_pie_fraction(visual_data)
            elif visual_type == "clock":
                return self._draw_clock(visual_data)
            elif visual_type == "number_line":
                return self._draw_number_line(visual_data, page_width)
            elif visual_type == "picture_word_match":
                return self._draw_picture_word_match(visual_data)
            elif visual_type == "labeled_diagram":
                return self._draw_labeled_diagram(visual_data)
            elif visual_type == "match_columns":
                return self._draw_match_columns(visual_data)
            elif visual_type == "ten_frame":
                return self._draw_ten_frame(visual_data)
            elif visual_type == "shapes":
                return self._draw_shapes(visual_data)
            elif visual_type == "pattern_tiles":
                return self._draw_pattern(visual_data)
            elif visual_type == "pictograph":
                return self._draw_pictograph(visual_data)
            elif visual_type == "array_visual":
                return self._draw_array(visual_data)
            elif visual_type == "base_ten_regrouping":
                return self._draw_base_ten(visual_data)
            elif visual_type == "fraction_bar":
                return self._draw_fraction_bar(visual_data)
            elif visual_type == "money_coins":
                return self._draw_money(visual_data)
            elif visual_type == "scenario_picture":
                return self._draw_scenario(visual_data)
            elif visual_type == "sequence_pictures":
                return self._draw_sequence(visual_data)
            elif visual_type == "bar_chart":
                return self._draw_bar_chart(visual_data)
            elif visual_type == "food_plate":
                return self._draw_food_plate(visual_data)
            elif visual_type == "percentage_bar":
                return self._draw_percentage_bar(visual_data)
        except Exception as e:
            logger.warning("Failed to render visual %s in PDF: %s", visual_type, e)
        return []

    def _draw_object_group(self, data: dict, page_width: float) -> list:
        """Draw emoji groups for picture addition/subtraction as colored circles."""
        from reportlab.graphics.shapes import Circle, Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        groups = data.get("groups", [])
        operation = data.get("operation", "+")

        total_objects = sum(g.get("count", 0) for g in groups)
        obj_size = 14 if total_objects <= 12 else 10
        spacing = obj_size + 4

        draw_width = min(page_width - 2 * cm, 400)
        draw_height = 50

        d = Drawing(draw_width, draw_height)

        group_colors = [
            HexColor("#EF4444"),
            HexColor("#3B82F6"),
            HexColor("#F59E0B"),
            HexColor("#10B981"),
        ]

        x_offset = 20

        for gi, group in enumerate(groups):
            count = group.get("count", 0)
            color = group_colors[gi % len(group_colors)]

            if gi > 0:
                d.add(
                    String(
                        x_offset + 5,
                        draw_height / 2 - 6,
                        operation,
                        fontSize=16,
                        fontName=FONT_BOLD,
                        fillColor=HexColor("#F97316"),
                    )
                )
                x_offset += 25

            for i in range(min(count, 20)):
                row = i // 8
                col = i % 8
                cx = x_offset + col * spacing + obj_size / 2
                cy = draw_height - 10 - row * spacing - obj_size / 2
                d.add(Circle(cx, cy, obj_size / 2, fillColor=color, strokeColor=None))

            cols_used = min(count, 8)
            x_offset += cols_used * spacing + 10

        if operation != "count":
            d.add(
                String(
                    x_offset + 5,
                    draw_height / 2 - 6,
                    "=",
                    fontSize=16,
                    fontName=FONT_BOLD,
                    fillColor=HexColor("#6366F1"),
                )
            )
            x_offset += 25
            d.add(
                Rect(
                    x_offset,
                    draw_height / 2 - 12,
                    30,
                    24,
                    fillColor=None,
                    strokeColor=HexColor("#A5B4FC"),
                    strokeWidth=1.5,
                    strokeDashArray=[4, 2],
                )
            )

        return [d, Spacer(1, 4)]

    def _draw_pie_fraction(self, data: dict) -> list:
        """Draw a pie chart fraction visual."""
        from reportlab.graphics.shapes import Drawing, Line, String, Wedge
        from reportlab.lib.colors import HexColor

        n = data.get("numerator", 1)
        d_val = data.get("denominator", 4)

        drawing = Drawing(200, 100)
        cx, cy, r = 50, 50, 40

        angle_per = 360 / max(d_val, 1)
        for i in range(d_val):
            start = 90 - (i + 1) * angle_per
            fill = HexColor("#6366F1") if i < n else HexColor("#EEF2FF")
            drawing.add(
                Wedge(
                    cx, cy, r, start, start + angle_per, fillColor=fill, strokeColor=HexColor("#A5B4FC"), strokeWidth=1
                )
            )

        drawing.add(String(130, 55, str(n), fontSize=20, fontName=FONT_BOLD, fillColor=HexColor("#4F46E5")))
        drawing.add(Line(120, 48, 160, 48, strokeColor=HexColor("#4F46E5"), strokeWidth=1.5))
        drawing.add(String(130, 30, str(d_val), fontSize=20, fontName=FONT_BOLD, fillColor=HexColor("#4F46E5")))

        return [drawing, Spacer(1, 4)]

    def _draw_clock(self, data: dict) -> list:
        """Draw a clock face."""
        import math as _math

        from reportlab.graphics.shapes import Circle, Drawing, Line, String
        from reportlab.lib.colors import HexColor

        hour = data.get("hour", 3)
        minute = data.get("minute", 0)

        drawing = Drawing(120, 120)
        cx, cy, r = 60, 60, 48

        drawing.add(Circle(cx, cy, r + 4, fillColor=HexColor("#1E1B4B")))
        drawing.add(Circle(cx, cy, r, fillColor=HexColor("#FFFFFF")))

        for h in range(1, 13):
            angle = _math.radians(90 - h * 30)
            nx = cx + (r - 14) * _math.cos(angle)
            ny = cy + (r - 14) * _math.sin(angle)
            drawing.add(String(nx - 4, ny - 4, str(h), fontSize=9, fontName=FONT_BOLD, fillColor=HexColor("#1E1B4B")))

        h_angle = _math.radians(90 - (hour % 12 + minute / 60) * 30)
        drawing.add(
            Line(
                cx,
                cy,
                cx + 26 * _math.cos(h_angle),
                cy + 26 * _math.sin(h_angle),
                strokeColor=HexColor("#1E1B4B"),
                strokeWidth=3.5,
            )
        )

        m_angle = _math.radians(90 - minute * 6)
        drawing.add(
            Line(
                cx,
                cy,
                cx + 36 * _math.cos(m_angle),
                cy + 36 * _math.sin(m_angle),
                strokeColor=HexColor("#6366F1"),
                strokeWidth=2,
            )
        )

        drawing.add(Circle(cx, cy, 3.5, fillColor=HexColor("#F97316")))

        return [drawing, Spacer(1, 4)]

    def _draw_number_line(self, data: dict, page_width: float) -> list:
        """Draw a number line with optional hop arcs."""
        from reportlab.graphics.shapes import Circle, Drawing, Line, String
        from reportlab.lib.colors import HexColor

        start = data.get("start", 0)
        end = data.get("end", 20)
        step = data.get("step", 2)
        highlight = data.get("highlight")
        hops_from = data.get("hops_from", -1)
        hops_count = data.get("hops_count", 0)
        hops_dir = data.get("hops_direction", "forward")
        highlight_start = data.get("highlight_start", -1)

        has_hops = hops_count > 0 and hops_from >= 0
        draw_width = min(page_width - 2 * cm, 350)
        draw_height = 55 if has_hops else 40
        pad = 20
        line_y = 35 if has_hops else 20

        drawing = Drawing(draw_width, draw_height)
        drawing.add(Line(pad, line_y, draw_width - pad, line_y, strokeColor=HexColor("#1E1B4B"), strokeWidth=1.2))

        rng = max(end - start, 1)
        v = start
        while v <= end:
            x = pad + ((v - start) / rng) * (draw_width - 2 * pad)
            drawing.add(Line(x, line_y - 5, x, line_y + 5, strokeColor=HexColor("#1E1B4B"), strokeWidth=1))
            drawing.add(
                String(x - 4, line_y + 10, str(v), fontSize=7, fontName=FONT_REGULAR, fillColor=HexColor("#1E1B4B"))
            )
            v += step

        # Hop arcs
        if has_hops:
            from reportlab.graphics.shapes import Path

            for i in range(hops_count):
                from_n = (hops_from + i) if hops_dir == "forward" else (hops_from - i)
                to_n = (hops_from + i + 1) if hops_dir == "forward" else (hops_from - i - 1)
                if from_n < start or from_n > end or to_n < start or to_n > end:
                    continue
                x1 = pad + ((from_n - start) / rng) * (draw_width - 2 * pad)
                x2 = pad + ((to_n - start) / rng) * (draw_width - 2 * pad)
                mid_x = (x1 + x2) / 2
                arc_y = line_y - 18 - i * 1.5
                p = Path()
                p.moveTo(x1, line_y - 3)
                p.curveTo(mid_x, arc_y, mid_x, arc_y, x2, line_y - 3)
                p.strokeColor = HexColor("#F97316")
                p.strokeWidth = 1.5
                p.fillColor = None
                p.strokeDashArray = [4, 2]
                drawing.add(p)

        # Start marker
        if highlight_start >= 0 and start <= highlight_start <= end:
            sx = pad + ((highlight_start - start) / rng) * (draw_width - 2 * pad)
            drawing.add(
                Circle(sx, line_y, 5, fillColor=HexColor("#F59E0B"), strokeColor=HexColor("#D97706"), strokeWidth=1.5)
            )

        # End marker
        if highlight is not None and start <= highlight <= end:
            hx = pad + ((highlight - start) / rng) * (draw_width - 2 * pad)
            drawing.add(
                Circle(hx, line_y, 4, fillColor=HexColor("#6366F1"), strokeColor=HexColor("#1E1B4B"), strokeWidth=1.5)
            )

        return [drawing, Spacer(1, 4)]

    def _draw_picture_word_match(self, data: dict) -> list:
        """Draw a labeled picture box for word matching (emoji won't render in PDF fonts)."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        word = data.get("word", data.get("label", "?"))
        # Draw a colored card with the word label
        d = Drawing(120, 60)
        d.add(
            Rect(
                10,
                5,
                100,
                50,
                fillColor=HexColor("#EEF2FF"),
                strokeColor=HexColor("#6366F1"),
                strokeWidth=1.5,
                rx=6,
                ry=6,
            )
        )
        # Truncate long words
        display = str(word)[:12]
        d.add(
            String(60 - len(display) * 3.5, 24, display, fontSize=13, fontName=FONT_BOLD, fillColor=HexColor("#4F46E5"))
        )

        return [d, Spacer(1, 4)]

    def _draw_labeled_diagram(self, data: dict) -> list:
        """Draw a labeled diagram with one blank label."""
        labels = data.get("labels", [])
        blank_idx = data.get("blank_index", -1)

        rows = []
        for i, label in enumerate(labels):
            display = "___?" if i == blank_idx else _sanitize_text(label)
            rows.append([Paragraph(display, self.styles["QuestionText"])])

        if not rows:
            return []

        t = Table(rows, colWidths=[4 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return [t, Spacer(1, 4)]

    def _draw_match_columns(self, data: dict) -> list:
        """Draw a two-column match table."""
        left_items = data.get("left", [])
        right_items = data.get("right", [])

        rows = []
        max_len = max(len(left_items), len(right_items))
        for i in range(max_len):
            left_text = ""
            if i < len(left_items):
                item = left_items[i]
                left_text = f"{_sanitize_text(item.get('emoji', ''))} {_sanitize_text(item.get('label', ''))}"
            right_text = ""
            if i < len(right_items):
                item = right_items[i]
                right_text = f"{_sanitize_text(item.get('emoji', ''))} {_sanitize_text(item.get('label', ''))}"
            rows.append(
                [
                    Paragraph(left_text, self.styles["QuestionText"]),
                    Paragraph(
                        "________", ParagraphStyle("MatchLine", alignment=TA_CENTER, fontName=FONT_REGULAR, fontSize=8)
                    ),
                    Paragraph(right_text, self.styles["QuestionText"]),
                ]
            )

        if not rows:
            return []

        t = Table(rows, colWidths=[4 * cm, 2 * cm, 4 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("GRID", (0, 0), (0, -1), 0.5, _MUTED),
                    ("GRID", (2, 0), (2, -1), 0.5, _MUTED),
                ]
            )
        )
        return [t, Spacer(1, 4)]

    def _draw_ten_frame(self, data: dict) -> list:
        """Draw a 2×5 ten frame grid with filled dots."""
        from reportlab.graphics.shapes import Circle, Drawing, Rect
        from reportlab.lib.colors import HexColor

        filled = data.get("filled", 5)
        total = data.get("total", 10)
        color = HexColor(data.get("color", "#6366F1"))

        cell_size = 22
        gap = 3
        cols = 5
        rows = 2 if total == 10 else 4
        width = cols * (cell_size + gap) + 20
        height = rows * (cell_size + gap) + 10

        d = Drawing(width, height)

        for i in range(total):
            row = i // cols
            col = i % cols
            x = 10 + col * (cell_size + gap)
            y = height - 10 - (row + 1) * (cell_size + gap) + gap

            # Cell border
            fill_color = HexColor("#F8FAFC") if i >= filled else HexColor("#E8E5FF")
            stroke_color = color if i < filled else HexColor("#E2E8F0")
            d.add(
                Rect(
                    x,
                    y,
                    cell_size,
                    cell_size,
                    fillColor=fill_color,
                    strokeColor=stroke_color,
                    strokeWidth=1.5,
                    rx=3,
                    ry=3,
                )
            )

            # Filled dot
            if i < filled:
                d.add(Circle(x + cell_size / 2, y + cell_size / 2, 7, fillColor=color, strokeColor=None))

        return [d, Spacer(1, 4)]

    def _draw_shapes(self, data: dict) -> list:
        """Draw colored geometric shapes in a row."""
        from reportlab.graphics.shapes import Circle, Drawing, Polygon, Rect, String
        from reportlab.lib.colors import HexColor

        shapes = data.get("shapes", [])

        d = Drawing(300, 60)
        x_offset = 10

        for i, shape in enumerate(shapes):
            color = HexColor(shape.get("color", "#3B82F6"))
            light_color = (
                HexColor(shape.get("color", "#3B82F6") + "40") if len(shape.get("color", "#3B82F6")) == 7 else color
            )

            if shape["name"] == "circle":
                d.add(Circle(x_offset + 20, 30, 18, fillColor=light_color, strokeColor=color, strokeWidth=2))
            elif shape["name"] == "triangle":
                d.add(
                    Polygon(
                        points=[x_offset + 20, 48, x_offset + 38, 12, x_offset + 2, 12],
                        fillColor=light_color,
                        strokeColor=color,
                        strokeWidth=2,
                    )
                )
            elif shape["name"] == "square":
                d.add(Rect(x_offset + 2, 10, 36, 36, fillColor=light_color, strokeColor=color, strokeWidth=2))
            elif shape["name"] == "rectangle":
                d.add(Rect(x_offset, 14, 40, 28, fillColor=light_color, strokeColor=color, strokeWidth=2))
            elif shape["name"] == "pentagon":
                d.add(
                    Polygon(
                        points=[
                            x_offset + 20,
                            48,
                            x_offset + 38,
                            38,
                            x_offset + 35,
                            12,
                            x_offset + 5,
                            12,
                            x_offset + 2,
                            38,
                        ],
                        fillColor=light_color,
                        strokeColor=color,
                        strokeWidth=2,
                    )
                )
            elif shape["name"] == "hexagon":
                d.add(
                    Polygon(
                        points=[
                            x_offset + 10,
                            48,
                            x_offset + 30,
                            48,
                            x_offset + 40,
                            30,
                            x_offset + 30,
                            12,
                            x_offset + 10,
                            12,
                            x_offset,
                            30,
                        ],
                        fillColor=light_color,
                        strokeColor=color,
                        strokeWidth=2,
                    )
                )

            # Label
            d.add(String(x_offset + 16, 0, chr(65 + i), fontSize=9, fontName=FONT_BOLD, fillColor=HexColor("#64748B")))
            x_offset += 65

        return [d, Spacer(1, 4)]

    def _draw_pattern(self, data: dict) -> list:
        """Draw emoji pattern with a blank position."""
        tiles = data.get("tiles", [])
        blank_pos = data.get("blank_position", -1)

        parts = []
        for i, tile in enumerate(tiles):
            if i == blank_pos:
                parts.append('<font size="14" color="#F97316"><b> ? </b></font>')
            else:
                parts.append(f'<font size="14"> {_sanitize_text(tile)} </font>')

        text = " ".join(parts)
        p = Paragraph(text, self.styles["QuestionText"])
        return [p, Spacer(1, 4)]

    def _draw_pictograph(self, data: dict) -> list:
        """Draw pictograph rows as colored circles (emoji won't render in PDF fonts)."""
        from reportlab.graphics.shapes import Circle, Drawing, String
        from reportlab.lib.colors import HexColor

        rows = data.get("rows", [])
        if not rows:
            return []

        row_colors = [HexColor("#6366F1"), HexColor("#F59E0B"), HexColor("#10B981"), HexColor("#EF4444")]
        max_count = max((r.get("count", 0) for r in rows), default=1)
        dot_r = 6
        gap = 16
        label_w = 80
        row_h = 20
        width = label_w + max_count * gap + 20
        height = len(rows) * row_h + 10

        d = Drawing(width, height)
        for ri, row in enumerate(rows):
            label = row.get("label", "")[:12]
            count = row.get("count", 0)
            color = row_colors[ri % len(row_colors)]
            y = height - 8 - ri * row_h

            d.add(String(2, y - 4, label, fontSize=8, fontName=FONT_BOLD, fillColor=HexColor("#1E1B4B")))
            for ci in range(min(count, 20)):
                cx = label_w + ci * gap + dot_r
                d.add(Circle(cx, y, dot_r, fillColor=color, strokeColor=None))

        elements = []
        title = data.get("title", "")
        if title:
            elements.append(
                Paragraph(
                    f"<b><font size='8'>{_sanitize_text(title)}</font></b>",
                    ParagraphStyle("PictoTitle", alignment=TA_CENTER, fontName=FONT_BOLD, fontSize=8),
                )
            )
        elements.append(d)
        return elements + [Spacer(1, 4)]

    def _draw_array(self, data: dict) -> list:
        """Draw a rows × cols grid of colored circles for multiplication."""
        from reportlab.graphics.shapes import Circle, Drawing
        from reportlab.lib.colors import HexColor

        rows = min(data.get("rows", 3), 6)
        cols = min(data.get("cols", 4), 8)

        dot_r = 6
        gap = 18
        pad = 10
        width = cols * gap + 2 * pad
        height = rows * gap + 2 * pad

        d = Drawing(width, height)
        color = HexColor("#F59E0B")

        for r in range(rows):
            for c in range(cols):
                x = pad + c * gap + gap / 2
                y = height - pad - r * gap - gap / 2
                d.add(Circle(x, y, dot_r, fillColor=color, strokeColor=HexColor("#D97706"), strokeWidth=0.5))

        return [d, Spacer(1, 4)]

    def _draw_base_ten(self, data: dict) -> list:
        """Draw base-ten blocks (hundreds squares, tens bars, ones cubes)."""
        from reportlab.graphics.shapes import Drawing, Rect
        from reportlab.lib.colors import HexColor

        numbers = data.get("numbers", [0])
        num = numbers[0] if numbers else 0
        hundreds = num // 100
        tens = (num % 100) // 10
        ones = num % 10

        width = max(200, (hundreds * 28 + tens * 10 + ones * 10 + 60))
        height = 50
        d = Drawing(width, height)

        x = 10
        # Hundreds — large blue squares
        for i in range(min(hundreds, 5)):
            d.add(
                Rect(
                    x,
                    5,
                    24,
                    24,
                    fillColor=HexColor("#3B82F6"),
                    strokeColor=HexColor("#2563EB"),
                    strokeWidth=1,
                    rx=2,
                    ry=2,
                )
            )
            x += 28

        if hundreds:
            x += 10

        # Tens — green bars
        for i in range(min(tens, 9)):
            d.add(
                Rect(
                    x,
                    5,
                    6,
                    24,
                    fillColor=HexColor("#22C55E"),
                    strokeColor=HexColor("#16A34A"),
                    strokeWidth=0.5,
                    rx=1,
                    ry=1,
                )
            )
            x += 8

        if tens:
            x += 10

        # Ones — small orange cubes
        for i in range(min(ones, 9)):
            d.add(
                Rect(
                    x,
                    14,
                    6,
                    6,
                    fillColor=HexColor("#FB923C"),
                    strokeColor=HexColor("#EA580C"),
                    strokeWidth=0.5,
                    rx=1,
                    ry=1,
                )
            )
            x += 8

        return [d, Spacer(1, 4)]

    def _draw_fraction_bar(self, data: dict) -> list:
        """Draw horizontal fraction bars for comparison."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        n = data.get("numerator", 1)
        d = max(data.get("denominator", 4), 1)
        color = HexColor(data.get("color", "#6366F1"))
        total_parts = 12
        filled = round((n / d) * total_parts)

        draw_width = 300
        bar_height = 20
        d_obj = Drawing(draw_width, bar_height + 15)

        part_width = (draw_width - 60) / total_parts
        for i in range(total_parts):
            x = 5 + i * part_width
            fill = color if i < filled else HexColor("#F1F5F9")
            d_obj.add(
                Rect(x, 5, part_width - 1, bar_height, fillColor=fill, strokeColor=HexColor("#CBD5E1"), strokeWidth=0.5)
            )

        d_obj.add(String(draw_width - 45, 10, f"{n}/{d}", fontSize=12, fontName=FONT_BOLD, fillColor=color))

        elements = [d_obj]

        second = data.get("second")
        if second:
            n2, d2 = second["numerator"], max(second["denominator"], 1)
            filled2 = round((n2 / d2) * total_parts)
            d_obj2 = Drawing(draw_width, bar_height + 5)
            for i in range(total_parts):
                x = 5 + i * part_width
                fill = HexColor("#EF4444") if i < filled2 else HexColor("#F1F5F9")
                d_obj2.add(
                    Rect(
                        x,
                        5,
                        part_width - 1,
                        bar_height,
                        fillColor=fill,
                        strokeColor=HexColor("#CBD5E1"),
                        strokeWidth=0.5,
                    )
                )
            d_obj2.add(
                String(
                    draw_width - 45, 10, f"{n2}/{d2}", fontSize=12, fontName=FONT_BOLD, fillColor=HexColor("#EF4444")
                )
            )
            elements.append(d_obj2)

        return elements + [Spacer(1, 4)]

    def _draw_money(self, data: dict) -> list:
        """Draw Indian currency coins and notes."""
        items = data.get("items", [])
        if not items:
            return []
        parts = []
        for item in items:
            label = _sanitize_text(item.get("label", ""))
            parts.append(f"<font size='11'><b>{label}</b></font>")
        text = "  +  ".join(parts) + "  =  ₹?"
        p = Paragraph(text, self.styles["QuestionText"])
        return [p, Spacer(1, 4)]

    def _draw_scenario(self, data: dict) -> list:
        """Draw scenario as a labeled box (emoji won't render in PDF fonts)."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        desc = _sanitize_text(data.get("description", data.get("scene_description", "")))
        scene_label = data.get("scene_label", "")

        elements = []
        if desc:
            elements.append(
                Paragraph(
                    f"<i><font size='9' color='#9F1239'>{desc}</font></i>",
                    ParagraphStyle("SceneDesc", alignment=TA_CENTER, fontName=FONT_REGULAR, fontSize=9),
                )
            )
        if scene_label:
            d = Drawing(150, 40)
            d.add(
                Rect(
                    5,
                    5,
                    140,
                    30,
                    fillColor=HexColor("#FFF7ED"),
                    strokeColor=HexColor("#F97316"),
                    strokeWidth=1,
                    rx=4,
                    ry=4,
                )
            )
            d.add(String(12, 15, str(scene_label)[:20], fontSize=10, fontName=FONT_BOLD, fillColor=HexColor("#9A3412")))
            elements.append(d)
        return elements + [Spacer(1, 4)]

    def _draw_sequence(self, data: dict) -> list:
        """Draw sequence of steps as labeled boxes with arrows."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        steps = data.get("steps", [])
        labels = data.get("labels", steps)
        blank_idx = data.get("blank_index", -1)

        if not labels:
            return []

        box_w = 50
        gap = 12
        n = min(len(labels), 6)
        width = n * box_w + (n - 1) * gap + 20
        d = Drawing(width, 40)

        for i in range(n):
            x = 10 + i * (box_w + gap)
            if i == blank_idx:
                d.add(
                    Rect(
                        x,
                        8,
                        box_w,
                        28,
                        fillColor=HexColor("#FFF7ED"),
                        strokeColor=HexColor("#F97316"),
                        strokeWidth=1.5,
                        rx=4,
                        ry=4,
                        strokeDashArray=[4, 2],
                    )
                )
                d.add(
                    String(x + box_w / 2 - 4, 17, "?", fontSize=14, fontName=FONT_BOLD, fillColor=HexColor("#F97316"))
                )
            else:
                label = _sanitize_text(str(labels[i]))[:8]
                d.add(
                    Rect(
                        x,
                        8,
                        box_w,
                        28,
                        fillColor=HexColor("#EEF2FF"),
                        strokeColor=HexColor("#6366F1"),
                        strokeWidth=1,
                        rx=4,
                        ry=4,
                    )
                )
                d.add(String(x + 4, 17, label, fontSize=9, fontName=FONT_BOLD, fillColor=HexColor("#4F46E5")))
            # Arrow between boxes
            if i < n - 1:
                ax = x + box_w + 2
                d.add(String(ax, 17, "->", fontSize=9, fontName=FONT_REGULAR, fillColor=HexColor("#94A3B8")))

        return [d, Spacer(1, 4)]

    def _draw_bar_chart(self, data: dict) -> list:
        """Draw a simple bar chart."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        bars = data.get("bars", [])
        title = data.get("title", "")
        if not bars:
            return []

        max_val = max((b.get("value", 1) for b in bars), default=1)
        bar_width = 30
        gap = 20
        chart_height = 80
        width = len(bars) * (bar_width + gap) + 40
        height = chart_height + 30

        d = Drawing(width, height)

        for i, bar in enumerate(bars):
            val = bar.get("value", 0)
            color = HexColor(bar.get("color", "#3B82F6"))
            bar_h = max((val / max(max_val, 1)) * chart_height, 4)
            x = 20 + i * (bar_width + gap)
            y = height - 20 - bar_h

            d.add(Rect(x, y, bar_width, bar_h, fillColor=color, strokeColor=None))
            d.add(String(x + bar_width / 2 - 4, y - 10, str(val), fontSize=8, fontName=FONT_BOLD, fillColor=color))
            label = _sanitize_text(bar.get("label", ""))[:8]
            d.add(String(x + 2, 2, label, fontSize=6, fontName=FONT_REGULAR, fillColor=HexColor("#64748B")))

        elements = []
        if title:
            elements.append(
                Paragraph(
                    f"<b><font size='8'>{_sanitize_text(title)}</font></b>",
                    ParagraphStyle("ChartTitle", alignment=TA_CENTER, fontName=FONT_BOLD, fontSize=8),
                )
            )
        elements.append(d)
        return elements + [Spacer(1, 4)]

    def _draw_food_plate(self, data: dict) -> list:
        """Draw food plate groups as colored labeled boxes (emoji won't render in PDF fonts)."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        groups = data.get("groups", [])
        blank_idx = data.get("blank_index", -1)
        if not groups:
            return []

        plate_colors = [
            HexColor("#10B981"),
            HexColor("#F59E0B"),
            HexColor("#EF4444"),
            HexColor("#6366F1"),
            HexColor("#EC4899"),
        ]
        n = min(len(groups), 5)
        box_w = 60
        gap = 8
        width = n * (box_w + gap) + 20
        d = Drawing(width, 40)

        for i in range(n):
            x = 10 + i * (box_w + gap)
            if i == blank_idx:
                d.add(
                    Rect(
                        x,
                        8,
                        box_w,
                        28,
                        fillColor=HexColor("#FFF7ED"),
                        strokeColor=HexColor("#F97316"),
                        strokeWidth=1.5,
                        rx=4,
                        ry=4,
                        strokeDashArray=[4, 2],
                    )
                )
                d.add(
                    String(x + box_w / 2 - 4, 17, "?", fontSize=14, fontName=FONT_BOLD, fillColor=HexColor("#F97316"))
                )
            else:
                g = groups[i]
                name = _sanitize_text(g.get("name", ""))[:8]
                color = plate_colors[i % len(plate_colors)]
                d.add(
                    Rect(x, 8, box_w, 28, fillColor=HexColor("#F0FDF4"), strokeColor=color, strokeWidth=1.5, rx=4, ry=4)
                )
                d.add(String(x + 4, 17, name, fontSize=8, fontName=FONT_BOLD, fillColor=color))

        return [d, Spacer(1, 4)]

    def _draw_percentage_bar(self, data: dict) -> list:
        """Draw a percentage bar."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.lib.colors import HexColor

        percent = data.get("percent", 25)
        color = HexColor(data.get("color", "#6366F1"))

        draw_width = 300
        bar_height = 18
        d = Drawing(draw_width, bar_height + 20)

        # Background bar
        d.add(
            Rect(
                10,
                10,
                draw_width - 20,
                bar_height,
                fillColor=HexColor("#F1F5F9"),
                strokeColor=HexColor("#CBD5E1"),
                strokeWidth=0.5,
                rx=4,
                ry=4,
            )
        )

        # Filled portion
        filled_width = max((percent / 100) * (draw_width - 20), 2)
        d.add(Rect(10, 10, filled_width, bar_height, fillColor=color, strokeColor=None, rx=4, ry=4))

        # Percentage label
        if percent >= 20:
            d.add(
                String(
                    10 + filled_width / 2 - 8,
                    14,
                    f"{percent}%",
                    fontSize=10,
                    fontName=FONT_BOLD,
                    fillColor=HexColor("#FFFFFF"),
                )
            )

        # Tick marks
        for mark in [25, 50, 75]:
            x = 10 + (mark / 100) * (draw_width - 20)
            d.add(Rect(x, 10, 0.5, bar_height, fillColor=HexColor("#CBD5E1"), strokeColor=None))

        # Scale labels
        for mark, label in [(0, "0%"), (25, "25%"), (50, "50%"), (75, "75%"), (100, "100%")]:
            x = 10 + (mark / 100) * (draw_width - 20)
            d.add(String(x - 6, 0, label, fontSize=6, fontName=FONT_REGULAR, fillColor=HexColor("#94A3B8")))

        return [d, Spacer(1, 4)]

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

        # ── Visual rendering (SVG-based visuals) ─────────────────────────────
        visual_type = question.get("visual_type")
        visual_data = question.get("visual_data")
        if visual_type and visual_data:
            page_width = A4[0] - 4.0 * cm
            visual_elements = self._build_visual(visual_type, visual_data, page_width)
            elements.extend(visual_elements)

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

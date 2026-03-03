"""Thin loader for static NCERT chapter map (fallback when DB is empty)."""

import json
import logging
from pathlib import Path

logger = logging.getLogger("skolar.ncert_chapter_map")

_MAP: dict | None = None


def get_static_chapter(grade: str, subject: str, topic: str) -> str | None:
    """Look up NCERT chapter from static JSON map.

    Args:
        grade: e.g. "Class 3" or "3"
        subject: e.g. "Maths"
        topic: e.g. "Addition (carries)"

    Returns:
        Chapter string like "Chapter 2: Fun with Numbers" or None.
    """
    global _MAP
    if _MAP is None:
        p = Path(__file__).parent / "ncert_chapter_map.json"
        if p.exists():
            _MAP = json.loads(p.read_text(encoding="utf-8"))
        else:
            logger.warning("ncert_chapter_map.json not found at %s", p)
            _MAP = {}

    # Normalise grade: "3" → "Class 3", "Class 3" stays
    g = grade.strip()
    if g.isdigit():
        g = f"Class {g}"

    key = f"{g}|{subject}|{topic}"
    return _MAP.get(key)

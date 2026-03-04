"""
Curriculum Graph v1 — unified NCERT data lookup.

Unifies scattered NCERT data from 4 files into a structured graph:
  - ncert_alignment.json  → Chapter + Section entities
  - ncert_chapter_map.json → Book name fallback
  - learning_objectives.py → LearningOutcome entities
  - topic_profiles.py      → topic existence check

Public API:
  get_curriculum_node(grade, subject, topic) → CurriculumNode | None
  get_chapter_chain(grade, subject, topic) → str
  get_all_topics_for(grade, subject) → list[str]
  validate_topic_exists(grade, subject, topic) → bool
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity models (frozen for caching)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LearningOutcome:
    text: str
    bloom_level: str  # "remember" | "understand" | "apply" | "analyse"


@dataclass(frozen=True)
class Section:
    exercise_id: str
    title: str
    page_start: int
    page_end: int
    ncert_question_types: tuple[str, ...]
    learning_outcomes: tuple[LearningOutcome, ...]


@dataclass(frozen=True)
class Chapter:
    number: int
    name: str
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class Book:
    name: str  # "NCERT Math Textbook Class 3"
    grade: str  # "Class 3"
    subject: str  # "Maths"
    chapters: tuple[Chapter, ...]


@dataclass(frozen=True)
class CurriculumNode:
    """Full ancestry for a single topic lookup."""

    grade: str
    subject: str
    topic: str
    book_name: str
    chapter: Chapter
    primary_section: Optional[Section]
    learning_outcomes: tuple[str, ...]
    page_range: str


# ---------------------------------------------------------------------------
# Bloom level inference from objective text
# ---------------------------------------------------------------------------

_BLOOM_KEYWORDS = {
    "analyse": ("analyse", "analyze", "compare", "contrast", "classify", "categorize", "distinguish"),
    "apply": ("solve", "apply", "use", "calculate", "compute", "determine", "show", "demonstrate"),
    "understand": ("explain", "describe", "summarise", "summarize", "interpret", "understand", "discuss"),
    "remember": ("identify", "name", "list", "state", "recall", "recognise", "recognize", "define", "read", "write"),
}


def _infer_bloom(text: str) -> str:
    """Infer Bloom's level from objective text. Defaults to 'understand'."""
    text_lower = text.lower()
    for level in ("analyse", "apply", "understand", "remember"):
        for keyword in _BLOOM_KEYWORDS[level]:
            if keyword in text_lower:
                return level
    return "understand"


# ---------------------------------------------------------------------------
# Graph builder (module singleton)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"

_GRAPH_CACHE: Optional[dict[str, CurriculumNode]] = None

# Subject → book name templates
_BOOK_NAMES: dict[str, str] = {
    "maths": "NCERT Math Textbook Class {grade}",
    "english": "Marigold Book {grade}",
    "hindi": "Rimjhim {grade}",
    "science": "NCERT Science Textbook Class {grade}",
    "evs": "NCERT EVS Textbook Class {grade}",
    "computer": "Computer Studies Class {grade}",
    "gk": "General Knowledge Class {grade}",
    "health": "Health & Physical Education Class {grade}",
    "moral science": "Moral Science Class {grade}",
}


def _load_json(filename: str) -> dict:
    """Load a JSON file from the data directory. Returns {} on failure."""
    path = _DATA_DIR / filename
    if not path.exists():
        logger.warning("[curriculum_graph] %s not found", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[curriculum_graph] Failed to parse %s: %s", path, exc)
        return {}


def _load_learning_objectives() -> dict[str, list[str]]:
    """Load LEARNING_OBJECTIVES dict from the data module."""
    try:
        from app.data.learning_objectives import LEARNING_OBJECTIVES

        return dict(LEARNING_OBJECTIVES)
    except Exception as exc:
        logger.warning("[curriculum_graph] Failed to load learning_objectives: %s", exc)
        return {}


def _resolve_topic_in_objectives(topic: str, objectives: dict[str, list[str]]) -> list[str]:
    """Find learning objectives for a topic, trying exact then fuzzy match."""
    # Exact match
    if topic in objectives:
        return objectives[topic]

    # Strip class suffix like "(Class 1)" for matching
    topic_lower = topic.lower()
    for key, values in objectives.items():
        if key.lower() == topic_lower:
            return values

    # Fuzzy: topic is substring of key or vice versa
    for key, values in objectives.items():
        if topic_lower in key.lower() or key.lower() in topic_lower:
            return values

    return []


def _build_graph() -> dict[str, CurriculumNode]:
    """Build the curriculum graph from data files. Called once."""
    alignment = _load_json("ncert_alignment.json")
    chapter_map = _load_json("ncert_chapter_map.json")
    objectives = _load_learning_objectives()

    graph: dict[str, CurriculumNode] = {}

    # Process ncert_alignment.json entries (primary source)
    for key, entry in alignment.items():
        parts = key.split("|")
        if len(parts) != 3:
            continue
        grade, subject, topic = parts[0].strip(), parts[1].strip(), parts[2].strip()

        # Build sections from exercises
        sections: list[Section] = []
        for ex in entry.get("exercises", []):
            # Get learning objectives for this topic and create LearningOutcome entities
            raw_objectives = _resolve_topic_in_objectives(topic, objectives)
            los = tuple(LearningOutcome(text=obj, bloom_level=_infer_bloom(obj)) for obj in raw_objectives)

            section = Section(
                exercise_id=ex.get("exercise_id", ""),
                title=ex.get("title", ""),
                page_start=ex.get("page_start", 0),
                page_end=ex.get("page_end", 0),
                ncert_question_types=tuple(ex.get("ncert_question_types", [])),
                learning_outcomes=los,
            )
            sections.append(section)

        chapter = Chapter(
            number=entry.get("chapter_number", 0),
            name=entry.get("chapter_name", topic),
            sections=tuple(sections),
        )

        # Determine primary section
        primary_ex_id = entry.get("primary_exercise", "")
        primary_section = None
        for s in sections:
            if s.exercise_id == primary_ex_id:
                primary_section = s
                break
        if not primary_section and sections:
            primary_section = sections[0]

        # Book name
        grade_num = ""
        for part in grade.split():
            if part.isdigit():
                grade_num = part
                break
        book_template = _BOOK_NAMES.get(subject.lower(), f"{subject} Textbook Class {{grade}}")
        book_name_str = book_template.format(grade=grade_num)

        # Chapter map fallback for richer book name
        map_key = f"{grade}|{subject}|{topic}"
        if map_key in chapter_map:
            book_name_str = chapter_map[map_key].split(":")[0].strip() if ":" in chapter_map[map_key] else book_name_str

        # Learning outcomes as plain strings
        raw_los = _resolve_topic_in_objectives(topic, objectives)

        node = CurriculumNode(
            grade=grade,
            subject=subject,
            topic=topic,
            book_name=book_name_str,
            chapter=chapter,
            primary_section=primary_section,
            learning_outcomes=tuple(raw_los),
            page_range=entry.get("page_range", ""),
        )
        graph[key] = node

    # Also add entries from chapter_map that aren't in alignment (fallback coverage)
    for key, chapter_str in chapter_map.items():
        if key in graph:
            continue
        parts = key.split("|")
        if len(parts) != 3:
            continue
        grade, subject, topic = parts[0].strip(), parts[1].strip(), parts[2].strip()

        # Parse chapter info from string like "Chapter 3: Addition"
        ch_num = 0
        ch_name = chapter_str
        if "Chapter" in chapter_str:
            import re

            m = re.search(r"Chapter\s+(\d+)", chapter_str)
            if m:
                ch_num = int(m.group(1))
            # Name is after the colon or dash
            for sep in (":", "—", "–", "-"):
                if sep in chapter_str:
                    ch_name = chapter_str.split(sep, 1)[1].strip()
                    break

        chapter = Chapter(number=ch_num, name=ch_name, sections=())

        grade_num = ""
        for part in grade.split():
            if part.isdigit():
                grade_num = part
                break
        book_template = _BOOK_NAMES.get(subject.lower(), f"{subject} Textbook Class {{grade}}")
        book_name_str = book_template.format(grade=grade_num)

        raw_los = _resolve_topic_in_objectives(topic, objectives)

        node = CurriculumNode(
            grade=grade,
            subject=subject,
            topic=topic,
            book_name=book_name_str,
            chapter=chapter,
            primary_section=None,
            learning_outcomes=tuple(raw_los),
            page_range="",
        )
        graph[key] = node

    logger.info("[curriculum_graph] Built graph with %d nodes", len(graph))
    return graph


def _get_graph() -> dict[str, CurriculumNode]:
    """Return the cached graph, building it on first access."""
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = _build_graph()
    return _GRAPH_CACHE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_curriculum_node(grade: str, subject: str, topic: str) -> Optional[CurriculumNode]:
    """
    Look up a curriculum node by grade, subject, and topic.

    Tries exact key first, then fuzzy matching on topic name.

    Args:
        grade: e.g. "Class 3"
        subject: e.g. "Maths"
        topic: e.g. "Addition (carries)"

    Returns:
        CurriculumNode or None if not found.
    """
    graph = _get_graph()

    # Exact match
    key = f"{grade}|{subject}|{topic}"
    if key in graph:
        return graph[key]

    # Fuzzy: case-insensitive match
    key_lower = key.lower()
    for k, node in graph.items():
        if k.lower() == key_lower:
            return node

    # Fuzzy: topic substring match within same grade+subject
    grade_lower = grade.lower()
    subject_lower = subject.lower()
    topic_lower = topic.lower()
    for k, node in graph.items():
        if node.grade.lower() == grade_lower and node.subject.lower() == subject_lower:
            if topic_lower in node.topic.lower() or node.topic.lower() in topic_lower:
                return node

    return None


def get_chapter_chain(grade: str, subject: str, topic: str) -> str:
    """
    Return a "Book > Chapter > Section" breadcrumb string.

    Returns empty string if topic not found.
    """
    node = get_curriculum_node(grade, subject, topic)
    if node is None:
        return ""

    parts = [node.book_name, f"Chapter {node.chapter.number}: {node.chapter.name}"]
    if node.primary_section:
        parts.append(f"Ex {node.primary_section.exercise_id}: {node.primary_section.title}")
    return " > ".join(parts)


def get_all_topics_for(grade: str, subject: str) -> list[str]:
    """Return all topics available for a given grade and subject."""
    graph = _get_graph()
    grade_lower = grade.lower()
    subject_lower = subject.lower()
    return sorted(
        node.topic
        for node in graph.values()
        if node.grade.lower() == grade_lower and node.subject.lower() == subject_lower
    )


def validate_topic_exists(grade: str, subject: str, topic: str) -> bool:
    """Fast existence check for a topic in the curriculum graph."""
    return get_curriculum_node(grade, subject, topic) is not None

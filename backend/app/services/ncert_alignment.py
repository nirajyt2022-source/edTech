"""NCERT Alignment Service — deterministic, zero LLM calls.

Enriches each question with NCERT alignment metadata:
chapter number, exercise ID, learning objective, question type, page reference.

Follows singleton-loader pattern from ncert_chapter_map.py.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.data.ncert_question_type_map import (
    FORMAT_TO_NCERT_TYPE,
    NCERT_QUESTION_TYPES,
    ROLE_TO_NCERT_TYPE,
)

logger = logging.getLogger("skolar.ncert_alignment")

_EXERCISE_ID_RE = re.compile(r"^\d+\.\d+$")


class NcertAlignmentService:
    """Static NCERT alignment enrichment for worksheet questions."""

    _data: dict | None = None

    @classmethod
    def _load(cls) -> dict:
        """Load alignment data from JSON (singleton, loaded once)."""
        if cls._data is not None:
            return cls._data

        p = Path(__file__).resolve().parent.parent / "data" / "ncert_alignment.json"
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            cls._data = cls._validate_data(raw)
        else:
            logger.warning("ncert_alignment.json not found at %s", p)
            cls._data = {}

        logger.info("[ncert_alignment] Loaded %d topic entries", len(cls._data))
        return cls._data

    @classmethod
    def _validate_data(cls, raw: dict) -> dict:
        """Validate alignment data at load time. Warn on issues, never crash."""
        cleaned: dict = {}
        for key, entry in raw.items():
            issues: list[str] = []

            # V1: chapter_number must be positive int
            ch_num = entry.get("chapter_number")
            if not isinstance(ch_num, int) or ch_num < 1:
                issues.append(f"invalid chapter_number: {ch_num}")

            exercises = entry.get("exercises", [])
            seen_ids: set[str] = set()

            for ex in exercises:
                ex_id = ex.get("exercise_id", "")

                # V2: exercise_id format
                if not _EXERCISE_ID_RE.match(str(ex_id)):
                    issues.append(f"invalid exercise_id format: {ex_id}")

                # V6: duplicate exercise_ids
                if ex_id in seen_ids:
                    issues.append(f"duplicate exercise_id: {ex_id}")
                seen_ids.add(ex_id)

                # V3: ncert_question_types in taxonomy
                for qt in ex.get("ncert_question_types", []):
                    if qt not in NCERT_QUESTION_TYPES:
                        issues.append(f"unknown ncert_question_type: {qt}")

                # V4: page_start <= page_end
                ps, pe = ex.get("page_start", 0), ex.get("page_end", 0)
                if ps > pe:
                    issues.append(f"page_start ({ps}) > page_end ({pe})")

            # V5: primary_exercise must reference an existing exercise_id
            primary = entry.get("primary_exercise")
            if primary and primary not in seen_ids:
                issues.append(f"primary_exercise '{primary}' not in exercises")

            if issues:
                logger.warning("[ncert_alignment] Validation issues for '%s': %s", key, "; ".join(issues))

            cleaned[key] = entry

        return cleaned

    @classmethod
    def align_worksheet(
        cls,
        questions: list[dict],
        grade: str,
        subject: str,
        topic: str,
        learning_objectives: list[str] | None = None,
    ) -> list[dict]:
        """Add ncert_alignment dict to each question. Fail-open: returns questions unchanged on error."""
        data = cls._load()

        # Normalise grade: "3" → "Class 3"
        g = grade.strip()
        if g.isdigit():
            g = f"Class {g}"

        key = f"{g}|{subject}|{topic}"
        topic_entry = data.get(key)

        if topic_entry is None:
            logger.debug("[ncert_alignment] No entry for '%s', skipping", key)
            return questions

        lo = learning_objectives or []

        for q in questions:
            q["ncert_alignment"] = cls._align_question(q, topic_entry, lo)

        return questions

    @classmethod
    def _align_question(cls, question: dict, topic_entry: dict, learning_objectives: list[str]) -> dict:
        """Resolve alignment for a single question."""
        # 1. Resolve NCERT question type
        fmt = question.get("format", "short_answer")
        role = question.get("role", "")

        ncert_type = FORMAT_TO_NCERT_TYPE.get(fmt, "short_answer")

        # Refine via role if format yields generic "short_answer"
        if ncert_type == "short_answer" and role in ROLE_TO_NCERT_TYPE:
            ncert_type = ROLE_TO_NCERT_TYPE[role]

        # 2. Match to exercise whose ncert_question_types contains the resolved type
        exercises = topic_entry.get("exercises", [])
        matched_exercise = None

        for ex in exercises:
            if ncert_type in ex.get("ncert_question_types", []):
                matched_exercise = ex
                break

        # Fallback to primary_exercise
        if matched_exercise is None:
            primary_id = topic_entry.get("primary_exercise")
            for ex in exercises:
                if ex.get("exercise_id") == primary_id:
                    matched_exercise = ex
                    break

        # Last resort: first exercise
        if matched_exercise is None and exercises:
            matched_exercise = exercises[0]

        # 3. Pick learning objective by role index
        role_index_map = {
            "recognition": 0,
            "application": 1,
            "representation": 1,
            "error_detection": 2,
            "thinking": 2,
        }
        lo_index = role_index_map.get(role, 0)
        learning_objective = learning_objectives[lo_index] if lo_index < len(learning_objectives) else None

        # 4. Build alignment dict
        exercise_id = matched_exercise.get("exercise_id") if matched_exercise else None

        return {
            "chapter_number": topic_entry.get("chapter_number"),
            "exercise_id": exercise_id,
            "learning_objective": learning_objective,
            "ncert_question_type": ncert_type,
            "page_ref": topic_entry.get("page_range"),
        }

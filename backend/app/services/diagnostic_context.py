"""
Diagnostic Context Builder — determines generation mode based on error patterns.

Rules:
  1. 2+ systematic errors on topic → remediation (target weak skills, force easy)
  2. All skills mastered → reinforcement (skip mastered, push harder)
  3. Otherwise → normal

All logic is deterministic. No LLM.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticContext:
    mode: str  # "normal" | "remediation" | "reinforcement"
    target_skill_tags: list[str] = field(default_factory=list)
    avoid_skill_tags: list[str] = field(default_factory=list)
    misconceptions_to_target: list[str] = field(default_factory=list)
    difficulty_override: Optional[str] = None
    rationale: str = ""


_DEFAULT_CONTEXT = DiagnosticContext(mode="normal", rationale="No diagnostic data available")


def build_diagnostic_context(
    child_id: Optional[str],
    topic_slug: str,
    subject: str,
    grade: int,
) -> DiagnosticContext:
    """
    Build a DiagnosticContext from the child's error patterns and mastery state.

    Returns a normal-mode context if:
      - No child_id provided
      - Diagnostic DB is disabled
      - Any error occurs (fail-open)
    """
    if not child_id:
        return DiagnosticContext(mode="normal", rationale="No child_id — anonymous generation")

    if os.getenv("ENABLE_DIAGNOSTIC_DB", "0") != "1":
        return DiagnosticContext(mode="normal", rationale="Diagnostic DB disabled")

    try:
        from app.services.error_pattern_detector import get_error_pattern_detector
        from app.services.learning_graph import get_learning_graph_service

        detector = get_error_pattern_detector()
        lg = get_learning_graph_service()

        # Get error patterns for this child
        patterns = detector.detect_patterns(child_id, lookback_days=30)
        systematic = [p for p in patterns if p.is_systematic]

        # Get mastery state for this topic
        mastery_row = None
        try:
            sb = lg._get_sb()
            mastery_row = lg._get_topic_mastery_row(sb, child_id, topic_slug)
        except Exception as exc:
            logger.debug("[diagnostic_context] mastery row lookup failed: %s", exc)

        mastery_level = (mastery_row or {}).get("mastery_level", "unknown")

        # Rule 1: 2+ systematic errors → remediation
        if len(systematic) >= 2:
            target_skills = []
            misconceptions = []
            for p in systematic:
                misconceptions.append(p.misconception_id)
                target_skills.extend(p.affected_skill_tags)
            # Deduplicate while preserving order
            seen_skills: set[str] = set()
            unique_skills = []
            for s in target_skills:
                if s not in seen_skills:
                    seen_skills.add(s)
                    unique_skills.append(s)

            return DiagnosticContext(
                mode="remediation",
                target_skill_tags=unique_skills[:5],
                misconceptions_to_target=misconceptions[:5],
                difficulty_override="easy",
                rationale=f"{len(systematic)} systematic errors detected — targeting weak skills",
            )

        # Rule 2: mastered → reinforcement
        if mastery_level == "mastered":
            # Find skills that are NOT in the systematic errors
            avoid = [p.affected_skill_tags[0] for p in systematic if p.affected_skill_tags]
            return DiagnosticContext(
                mode="reinforcement",
                avoid_skill_tags=avoid,
                difficulty_override="hard",
                rationale="Topic mastered — reinforcement mode with harder questions",
            )

        # Rule 3: normal
        rationale_parts = []
        if systematic:
            rationale_parts.append(f"1 systematic error ({systematic[0].misconception_display})")
        if mastery_level != "unknown":
            rationale_parts.append(f"mastery={mastery_level}")

        return DiagnosticContext(
            mode="normal",
            rationale="; ".join(rationale_parts) if rationale_parts else "Normal generation",
        )

    except Exception as exc:
        logger.error("[diagnostic_context] build failed (fail-open): %s", exc, exc_info=True)
        return DiagnosticContext(mode="normal", rationale=f"Error: {exc}")

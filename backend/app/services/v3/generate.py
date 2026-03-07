"""V3 worksheet generation — main entry point.

Orchestrates: slot_builder → gemini_filler → assembler → light_validator.
Same signature as generate_worksheet() in worksheet_generator.py for easy swap-in.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from .assembler import assemble_worksheet
from .gemini_filler import fill_slots
from .light_validator import validate_worksheet
from .slot_builder import build_slots

logger = logging.getLogger(__name__)


def _get_child_adaptive_config(child_id: str, topic: str, subject: str) -> dict | None:
    """Fetch child's mastery for this topic and return adaptive config."""
    from app.services.mastery_store import get_mastery_store

    store = get_mastery_store()
    all_mastery = store.list_student(child_id)

    if not all_mastery:
        return None

    # Find mastery entries matching this topic's skill tags
    topic_slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    topic_keywords = set(topic_slug.split("_")) - {"class", "the", "and", "of", "in"}

    relevant = []
    for m in all_mastery:
        tag_words = set(m.skill_tag.lower().split("_"))
        overlap = topic_keywords & tag_words
        if len(overlap) >= 1:
            relevant.append(m)

    if not relevant:
        return None

    # Aggregate mastery
    total_attempts = sum(m.total_attempts for m in relevant)
    correct_attempts = sum(m.correct_attempts for m in relevant)
    accuracy = (correct_attempts / total_attempts * 100) if total_attempts > 0 else 0
    avg_streak = sum(m.streak for m in relevant) / len(relevant)

    # Majority vote for mastery level
    mastery_counts: dict[str, int] = {}
    for m in relevant:
        mastery_counts[m.mastery_level] = mastery_counts.get(m.mastery_level, 0) + 1
    overall_level = max(mastery_counts, key=mastery_counts.get) if mastery_counts else "unknown"

    # Weak formats: skill_tags with low accuracy
    weak_tags = [
        m.skill_tag for m in relevant if m.total_attempts >= 3 and (m.correct_attempts / m.total_attempts) < 0.6
    ]

    return {
        "mastery_level": overall_level,
        "accuracy": round(accuracy, 1),
        "total_attempts": total_attempts,
        "avg_streak": round(avg_streak, 1),
        "weak_skill_tags": weak_tags,
        "relevant_entries": len(relevant),
    }


def _fetch_curriculum_context(grade_level: str, subject: str, topic: str) -> str | None:
    """Fetch curriculum context synchronously (wraps async get_curriculum_context)."""
    try:
        from app.services.curriculum import get_curriculum_context

        return asyncio.run(get_curriculum_context(grade_level, subject, topic))
    except RuntimeError:
        # Already inside an event loop — use nest_asyncio or skip
        try:
            import nest_asyncio

            nest_asyncio.apply()
            from app.services.curriculum import get_curriculum_context

            return asyncio.run(get_curriculum_context(grade_level, subject, topic))
        except Exception as ne:
            logger.debug("[v3] nest_asyncio fallback failed: %s", ne)
    except Exception as e:
        logger.warning("[v3] curriculum fetch failed: %s", e)
    return None


def generate_worksheet_v3(
    client,
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int = 10,
    language: str = "English",
    problem_style: str = "standard",
    custom_instructions: str | None = None,
    child_id: str | None = None,
) -> tuple[dict, int, list[str]]:
    """V3 worksheet generation. Returns (worksheet_dict, elapsed_ms, warnings).

    This function has the SAME return signature as the current generate_worksheet()
    in worksheet_generator.py, making it easy to swap in.
    """
    t0 = time.perf_counter()
    warnings: list[str] = []

    # Step 0.5: Fetch adaptive difficulty if child_id is provided
    adaptive_config = None
    if child_id:
        try:
            adaptive_config = _get_child_adaptive_config(child_id, topic, subject)
            if adaptive_config:
                warnings.append(f"[v3] adaptive difficulty applied: mastery={adaptive_config['mastery_level']}")
                logger.info(
                    "[v3] Adaptive config: mastery=%s accuracy=%.1f%% attempts=%d",
                    adaptive_config["mastery_level"],
                    adaptive_config["accuracy"],
                    adaptive_config["total_attempts"],
                )
        except Exception as e:
            logger.warning("[v3] adaptive difficulty fetch failed (non-blocking): %s", e)
            adaptive_config = None

    # Step 1: Build slots (pure Python, instant)
    logger.info(
        "[v3] Building slots: %s / %s / %s / %s / %dQ",
        grade_level,
        subject,
        topic,
        difficulty,
        num_questions,
    )
    slot_output = build_slots(
        board=board,
        grade_level=grade_level,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        num_questions=num_questions,
        problem_style=problem_style,
        language=language,
        adaptive_config=adaptive_config,
    )
    slot_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("[v3] Slot building took %dms", slot_ms)

    # Step 1.5: Fetch curriculum context (NCERT RAG)
    curriculum_ctx = _fetch_curriculum_context(grade_level, subject, topic)
    if curriculum_ctx:
        warnings.append("[v3] curriculum context injected")
        logger.info("[v3] Curriculum context loaded for %s / %s", subject, topic)
    else:
        logger.info("[v3] No curriculum context for %s / %s", subject, topic)

    # Step 2: Fill with Gemini
    t_fill = time.perf_counter()
    filled = fill_slots(client, slot_output.slots, language, curriculum_context=curriculum_ctx)
    fill_ms = int((time.perf_counter() - t_fill) * 1000)
    logger.info("[v3] Gemini fill took %dms for %d slots", fill_ms, len(filled))

    # Step 3: Assemble
    worksheet = assemble_worksheet(slot_output, filled)

    # Ensure metadata is present for template rendering
    worksheet["grade"] = grade_level
    worksheet["subject"] = subject
    worksheet["topic"] = topic
    worksheet["difficulty"] = difficulty
    worksheet["board"] = board

    # Step 3.5: AI Review (catches topic drift, wrong answers, repetition)
    try:
        from .gemini_filler import review_worksheet

        t_review = time.perf_counter()
        worksheet = review_worksheet(client, worksheet)
        review_ms = int((time.perf_counter() - t_review) * 1000)
        warnings.append(f"[v3] AI review completed in {review_ms}ms")
        logger.info("[v3] AI review took %dms", review_ms)
    except Exception as review_err:
        logger.warning("[v3] AI review failed (non-blocking): %s", review_err)

    # Step 4: Light validation
    passed, issues, failed_slots = validate_worksheet(worksheet, slot_output.slots)
    warnings.extend(issues)

    # Step 5: Retry failed slots (max 1 retry)
    if not passed and failed_slots:
        logger.info("[v3] Retrying %d failed slots: %s", len(failed_slots), failed_slots)
        retry_slots = [s for s in slot_output.slots if s.slot_number in failed_slots]
        if retry_slots:
            retry_filled = fill_slots(client, retry_slots, language, curriculum_context=curriculum_ctx)
            # Merge retry results into worksheet
            retry_by_slot = {}
            for item in retry_filled:
                retry_by_slot[item.get("slot", 0)] = item

            for slot_num, fill_data in retry_by_slot.items():
                idx = slot_num - 1
                if 0 <= idx < len(worksheet["questions"]):
                    q = worksheet["questions"][idx]
                    if fill_data.get("text") and len(fill_data["text"]) >= 5:
                        q["text"] = fill_data["text"]
                        if fill_data.get("hint"):
                            q["hint"] = fill_data["hint"]
                        if fill_data.get("explanation"):
                            q["explanation"] = fill_data["explanation"]
                        if fill_data.get("options"):
                            q["options"] = fill_data["options"]
                        warnings.append(f"Q{slot_num}: retried and replaced")

    # Add custom_instructions note
    if custom_instructions:
        warnings.append(f"[v3] custom_instructions not yet supported: {custom_instructions[:50]}")

    # === Runtime quality gate ===
    from app.services.v3.quality_gate import check_worksheet

    gate_result = check_worksheet(
        worksheet=worksheet,
        slots=slot_output.slots,
        topic=topic,
        subject=subject,
        grade_level=grade_level,
    )

    if gate_result.issues:
        warnings.extend([f"[quality_gate] {issue}" for issue in gate_result.issues])
        logger.info("[v3] quality gate: %s (%d issues)", gate_result.severity, len(gate_result.issues))

    if not gate_result.passed:
        # Critical failure — try once more with resolved topic name
        logger.warning("[v3] quality gate BLOCKED — attempting retry with resolved topic")
        try:
            from app.data.topic_lookup import resolve_topic

            grade_match = re.search(r"\d+", str(grade_level))
            grade = int(grade_match.group()) if grade_match else None
            resolved = resolve_topic(topic, grade)

            if resolved and resolved != topic:
                logger.info("[v3] retrying with resolved topic: %s → %s", topic, resolved)
                slot_output = build_slots(
                    board=board,
                    grade_level=grade_level,
                    subject=subject,
                    topic=resolved,
                    difficulty=difficulty,
                    num_questions=num_questions,
                    problem_style=problem_style,
                    language=language,
                    adaptive_config=adaptive_config,
                )
                filled = fill_slots(client, slot_output.slots, language, curriculum_context=curriculum_ctx)
                worksheet = assemble_worksheet(slot_output, filled)

                gate_result = check_worksheet(
                    worksheet=worksheet,
                    slots=slot_output.slots,
                    topic=resolved,
                    subject=subject,
                    grade_level=grade_level,
                )

                if gate_result.passed:
                    warnings.append("[quality_gate] Retry with resolved topic name succeeded")
                else:
                    warnings.extend([f"[quality_gate:retry] {i}" for i in gate_result.issues])
        except Exception as e:
            logger.warning("[v3] quality gate retry failed: %s", e)

    from app.core.config import get_settings

    strict_p1 = get_settings().trust_strict_p1
    if not gate_result.passed or (strict_p1 and gate_result.severity == "warning"):
        raise ValueError(
            f"V3 quality gate rejected worksheet: severity={gate_result.severity}, issues={gate_result.issues[:3]}"
        )

    worksheet["_quality_gate"] = {
        "passed": gate_result.passed,
        "severity": gate_result.severity,
        "issues_count": len(gate_result.issues),
    }

    # Step 6: Enrich visuals + render HTML template (no Gemini call — deterministic)
    t_render = time.perf_counter()
    try:
        from .visual_strategy import enrich_visuals
        from .worksheet_template import render_worksheet_html

        worksheet = enrich_visuals(worksheet)
        rendered_html = render_worksheet_html(worksheet)
        if rendered_html:
            worksheet["rendered_html"] = rendered_html
            render_ms = int((time.perf_counter() - t_render) * 1000)
            logger.info("[v3] Template rendering took %dms", render_ms)
            warnings.append(f"[v3] HTML rendered in {render_ms}ms")
    except Exception as render_err:
        logger.warning("[v3] Template rendering failed (non-blocking): %s", render_err)
        # Non-blocking: worksheet still works without rendered_html

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("[v3] Total generation: %dms, %d warnings", elapsed_ms, len(warnings))

    return worksheet, elapsed_ms, warnings

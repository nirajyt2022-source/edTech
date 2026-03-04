"""V3 worksheet generation — main entry point.

Orchestrates: slot_builder → gemini_filler → assembler → light_validator.
Same signature as generate_worksheet() in worksheet_generator.py for easy swap-in.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .assembler import assemble_worksheet
from .gemini_filler import fill_slots
from .light_validator import validate_worksheet
from .slot_builder import build_slots

logger = logging.getLogger(__name__)


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
) -> tuple[dict, int, list[str]]:
    """V3 worksheet generation. Returns (worksheet_dict, elapsed_ms, warnings).

    This function has the SAME return signature as the current generate_worksheet()
    in worksheet_generator.py, making it easy to swap in.
    """
    t0 = time.perf_counter()
    warnings: list[str] = []

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

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("[v3] Total generation: %dms, %d warnings", elapsed_ms, len(warnings))

    return worksheet, elapsed_ms, warnings

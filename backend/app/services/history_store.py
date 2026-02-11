"""
Persistent history store for worksheet generation.

Tracks last N=30 worksheets to avoid repeating contexts, error patterns,
thinking styles, number pairs, and question templates across generations.

Storage: local JSON file at backend/.practicecraft_history.json
"""

import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger("practicecraft.history_store")

HISTORY_FILE = Path(__file__).parent.parent.parent / ".practicecraft_history.json"
MAX_HISTORY = 30


def load_history() -> list[dict]:
    """Load worksheet history from disk. Returns list of worksheet records."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE) as f:
            data = json.load(f)
        return data.get("worksheets", [])[-MAX_HISTORY:]
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load history: %s", exc)
        return []


def save_history(worksheets: list[dict]) -> None:
    """Save worksheet history to disk (keeps last MAX_HISTORY)."""
    data = {"worksheets": worksheets[-MAX_HISTORY:]}
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        logger.warning("Failed to save history: %s", exc)


def get_avoid_state() -> dict:
    """Aggregate avoid items from last N worksheets."""
    history = load_history()
    avoid: dict[str, list[str]] = {
        "used_contexts": [],
        "used_error_ids": [],
        "used_thinking_styles": [],
        "used_number_pairs": [],
        "used_question_hashes": [],
    }
    for ws in history:
        avoid["used_contexts"].extend(ws.get("used_contexts", []))
        avoid["used_error_ids"].extend(ws.get("used_error_ids", []))
        avoid["used_thinking_styles"].extend(ws.get("used_thinking_styles", []))
        avoid["used_number_pairs"].extend(ws.get("used_number_pairs", []))
        avoid["used_question_hashes"].extend(ws.get("used_question_hashes", []))
    return avoid


def hash_question(text: str) -> str:
    """Hash question text for dedup (exact match)."""
    normalized = text.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def hash_question_template(text: str) -> str:
    """Hash question text with numbers replaced (structural dedup)."""
    normalized = re.sub(r"\d+", "N", text.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def update_history(worksheet_record: dict) -> None:
    """Append a worksheet record to history and save."""
    history = load_history()
    history.append(worksheet_record)
    save_history(history)


def build_worksheet_record(
    grade: str,
    topic: str,
    questions: list[dict],
    used_contexts: list[str],
    used_error_ids: list[str],
    used_thinking_styles: list[str],
) -> dict:
    """Build a history record from generated worksheet data."""
    number_pairs: list[str] = []
    question_hashes: list[str] = []

    for q in questions:
        text = q.get("question_text", "")
        question_hashes.append(hash_question(text))

        nums = re.findall(r"\d{2,}", text)
        if len(nums) >= 2:
            number_pairs.append(f"{nums[0]}+{nums[1]}")

    return {
        "grade": grade,
        "topic": topic,
        "used_contexts": used_contexts,
        "used_error_ids": used_error_ids,
        "used_thinking_styles": used_thinking_styles,
        "used_number_pairs": number_pairs,
        "used_question_hashes": question_hashes,
    }

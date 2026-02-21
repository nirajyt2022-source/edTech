"""quality_gate.py — post-assembly worksheet quality checks.

Runs after all questions are assembled and before the PDF is created.
Operates in log-only mode: failures are recorded but never block generation.

Field conventions understood:
  question text  → q["question"]  | q["question_text"]  | q["text"]
  question number→ q["display_number"] | q["number"]
  answer         → q["correct_answer"] | q["answer"]
  hint           → q["hint"]
  fallback flag  → q["is_fallback"]  (bool — set when LLM failed all attempts)
"""
import re
from typing import List, Tuple

FORBIDDEN_CLASS_1_2 = [
    "explain why", "explain how", "what mistake", "what error",
    "how many hours", "seconds in", "justify your", "give reason",
    "prove that", "compare and contrast"
]


def jaccard(a: str, b: str) -> float:
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def extract_times(text: str) -> frozenset:
    return frozenset(re.findall(r'\d{1,2}:\d{2}(?:\s*[AP]M)?', text, re.I))


def _q_text(q: dict) -> str:
    """Return question text from any of the known field names."""
    return q.get("question") or q.get("question_text") or q.get("text") or ""


def _q_number(q: dict, fallback: int = 0) -> object:
    """Return display number from any of the known field names."""
    n = q.get("display_number") or q.get("number")
    if n is not None:
        return n
    # Try to parse from id field (e.g. "q3" → 3)
    raw_id = q.get("id", "")
    try:
        return int(str(raw_id).lower().replace("q", "").strip())
    except (ValueError, TypeError):
        return fallback or "?"


def run_quality_gate(worksheet: dict) -> Tuple[bool, List[str]]:
    """Run all quality checks on an assembled worksheet dict.

    Returns (passed: bool, failures: list[str]).
    Always returns both values — callers decide whether to block or log.
    """
    failures = []
    questions = worksheet.get("questions", [])
    answer_key = worksheet.get("answer_key", {})
    grade_str = worksheet.get("grade", "Class 3")
    try:
        grade_num = int(str(grade_str).split()[-1])
    except (ValueError, IndexError):
        grade_num = 3
    requested = worksheet.get("requested_count", len(questions))

    # ── Check 1: Question count ────────────────────────────────────────────
    if len(questions) < requested:
        failures.append(f"COUNT: got {len(questions)}, expected {requested}")

    # ── Check 2: Answer key alignment ─────────────────────────────────────
    for i, q in enumerate(questions, 1):
        n = _q_number(q, i)
        keyed = answer_key.get(f"Q{n}")
        actual = q.get("correct_answer") or q.get("answer")
        if keyed and actual and str(keyed).strip() != str(actual).strip():
            failures.append(
                f"KEY_MISMATCH: Q{n} key='{keyed}' actual='{actual}'"
            )

    # ── Check 3: Duplicate questions ──────────────────────────────────────
    for i, q1 in enumerate(questions):
        for j, q2 in enumerate(questions[i + 1:], i + 1):
            t1 = _q_text(q1)
            t2 = _q_text(q2)
            sim = jaccard(t1, t2)
            if sim > 0.60:
                n1 = _q_number(q1, i + 1)
                n2 = _q_number(q2, j + 1)
                failures.append(
                    f"DUPLICATE: Q{n1} and Q{n2} ({int(sim * 100)}% overlap)"
                )
            times1, times2 = extract_times(t1), extract_times(t2)
            if len(times1) >= 2 and times1 == times2:
                n1 = _q_number(q1, i + 1)
                n2 = _q_number(q2, j + 1)
                failures.append(
                    f"DUPLICATE_TIMES: Q{n1} and Q{n2} share identical times"
                )

    # ── Check 4: Grade appropriateness for Class 1-2 ──────────────────────
    if grade_num <= 2:
        for i, q in enumerate(questions, 1):
            text = _q_text(q).lower()
            for phrase in FORBIDDEN_CLASS_1_2:
                if phrase in text:
                    n = _q_number(q, i)
                    failures.append(
                        f"GRADE_VIOLATION: Q{n} contains '{phrase}'"
                    )

    # ── Check 5: Hints must not reveal answers ────────────────────────────
    for i, q in enumerate(questions, 1):
        hint = q.get("hint") or ""
        answer = str(q.get("correct_answer") or q.get("answer") or "")
        if hint and answer and len(answer) > 2 and answer.lower() in hint.lower():
            n = _q_number(q, i)
            failures.append(
                f"HINT_LEAK: Q{n} hint contains answer '{answer}'"
            )

    # ── Check 6: Stub questions (LLM failed all attempts) ─────────────────
    for i, q in enumerate(questions, 1):
        if q.get("is_fallback"):
            n = _q_number(q, i)
            failures.append(
                f"FALLBACK: Q{n} is a stub — LLM failed all 3 attempts"
            )

    return len(failures) == 0, failures

"""quality_gate.py — post-assembly worksheet quality checks.

Runs after all questions are assembled and before the PDF is created.
Operates in log-only mode: failures are recorded but never block generation.

Field conventions understood:
  question text  → q["question"]  | q["question_text"]  | q["text"]
  question number→ q["display_number"] | q["number"]
  answer         → q["correct_answer"] | q["answer"]
  hint           → q["hint"]
  explanation    → q["explanation"]
  fallback flag  → q["is_fallback"]  (bool — set when LLM failed all attempts)
  options        → q["options"]      (list[str] | None — for MCQ questions)
  format         → q["format"]       (render format: mcq_3|mcq_4|fill_blank|…)
"""
import re
from typing import List, Tuple

FORBIDDEN_CLASS_1_2 = [
    "explain why", "explain how", "what mistake", "what error",
    "how many hours", "seconds in", "justify your", "give reason",
    "prove that", "compare and contrast"
]

# Letters accepted as MCQ correct-answer proxies
_MCQ_LETTERS = {"A", "B", "C", "D"}
# Index each letter maps to in the options list
_LETTER_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}

# Matches "o'clock" with standard apostrophe (U+0027), smart quote (U+2019),
# or a space — all common LLM spelling variants.
_OCLOCK_RE = re.compile(r"o['\u2019\s]?clock", re.IGNORECASE)


def _is_mcq_letter(answer: str) -> bool:
    """Return True for bare single MCQ choice letters (A/B/C/D, case-insensitive).
    These are expected to repeat and are excluded from flood/consecutive checks.
    """
    return len(answer.strip()) == 1 and answer.strip().upper() in _MCQ_LETTERS


def jaccard(a: str, b: str) -> float:
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def extract_times(text: str) -> frozenset:
    return frozenset(re.findall(r'\d{1,2}:\d{2}(?:\s*[AP]M)?', text, re.I))


def _content_words(text: str) -> frozenset:
    """Return content words longer than 4 characters (avoids common 4-letter
    question words like 'what', 'many', 'does', 'have').

    Tokenises by whitespace so Devanagari compound characters joined by the
    virama (U+094D) are measured as whole words, not split into single
    consonants.  Works for Latin, Devanagari, and other scripts.
    """
    result = set()
    for token in text.split():
        # Strip leading/trailing non-word chars (punctuation, brackets, etc.)
        word = re.sub(r'^[^\w]+|[^\w]+$', '', token, flags=re.UNICODE)
        if len(word) > 4:
            result.add(word.lower())
    return frozenset(result)


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
    # Jaccard threshold lowered to 0.50 (was 0.60) to catch closer paraphrases.
    # CONCEPT_DUPLICATE fires when both questions share a content word (len > 4)
    # regardless of phrasing similarity — catches same concept retested.
    for i, q1 in enumerate(questions):
        for j, q2 in enumerate(questions[i + 1:], i + 1):
            t1 = _q_text(q1)
            t2 = _q_text(q2)
            sim = jaccard(t1, t2)
            if sim > 0.50:
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
            shared = _content_words(t1) & _content_words(t2)
            if shared:
                n1 = _q_number(q1, i + 1)
                n2 = _q_number(q2, j + 1)
                sample = sorted(shared)[0]  # deterministic: pick alphabetically first
                failures.append(
                    f"CONCEPT_DUPLICATE: Q{n1} and Q{n2} share keyword '{sample}'"
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

    # ── Check 7: MCQ integrity ─────────────────────────────────────────────
    # Four sub-checks covering both sync directions:
    #   a) MCQ format but options is null/empty
    #   b) options must not contain duplicates
    #   c) if correct_answer is a letter (A/B/C/D) the matching option must exist
    #   d) Safety net: options present but format is NOT an MCQ type
    #      (catches cases the auto-correct in slot_engine didn't reach)
    for i, q in enumerate(questions, 1):
        fmt = (q.get("format") or "").lower()
        n = _q_number(q, i)
        opts = q.get("options") or []
        is_mcq_fmt = fmt in ("mcq_3", "mcq_4", "multiple_choice")

        # d) options present but format is not MCQ
        if opts and not is_mcq_fmt:
            failures.append(
                f"OPTIONS_FORMAT_MISMATCH: Q{n} has {len(opts)} option(s) "
                f"but format='{fmt}'"
            )

        if not is_mcq_fmt:
            continue  # remaining checks only apply to MCQ formats

        # a) MCQ format but no options
        if not opts:
            failures.append(
                f"MCQ_BROKEN: Q{n} format={fmt} but options is null/empty"
            )
            continue  # no options → skip sub-checks b and c
        # b) duplicate options
        seen: list = []
        for opt in opts:
            if opt in seen:
                failures.append(
                    f"MCQ_BROKEN: Q{n} has duplicate option '{opt}'"
                )
                break
            seen.append(opt)
        # c) letter answer must map to an existing option
        ans = (q.get("correct_answer") or "").strip().upper()
        if ans in _MCQ_LETTERS:
            idx = _LETTER_INDEX[ans]
            if idx >= len(opts):
                failures.append(
                    f"MCQ_BROKEN: Q{n} correct_answer='{ans}' but only "
                    f"{len(opts)} option(s) exist"
                )

    # ── Check 8: Empty question text ──────────────────────────────────────
    # Catches questions where LLM returned empty text but is_fallback was not
    # set (e.g. regen path missed the flag).
    for i, q in enumerate(questions, 1):
        text = _q_text(q)
        if not text or not text.strip():
            n = _q_number(q, i)
            failures.append(
                f"EMPTY_QUESTION: Q{n} has no question text"
            )

    # ── Check 9: Explanation must not give away the answer ────────────────
    for i, q in enumerate(questions, 1):
        explanation = q.get("explanation") or ""
        answer = str(q.get("correct_answer") or q.get("answer") or "")
        if explanation and answer and len(answer) > 2 and answer.lower() in explanation.lower():
            n = _q_number(q, i)
            failures.append(
                f"EXPLANATION_LEAK: Q{n} explanation contains answer '{answer}'"
            )

    # ── Check 10: Consecutive same answers ────────────────────────────────────
    # Three or more questions in a row with the same answer signals a tenses-
    # style error (LLM locked onto one answer for a whole slot group).
    # Single-letter MCQ choices (A/B/C/D) are exempt — they repeat by design.
    _cur_run: list = []   # [(q_number, answer)]
    _all_runs: list = []
    for i, q in enumerate(questions, 1):
        ans = str(q.get("correct_answer") or q.get("answer") or "").strip()
        n = _q_number(q, i)
        if not ans or _is_mcq_letter(ans):
            if _cur_run:
                _all_runs.append(_cur_run)
                _cur_run = []
            continue
        if _cur_run and _cur_run[-1][1].lower() == ans.lower():
            _cur_run.append((n, ans))
        else:
            if _cur_run:
                _all_runs.append(_cur_run)
            _cur_run = [(n, ans)]
    if _cur_run:
        _all_runs.append(_cur_run)

    for run in _all_runs:
        if len(run) >= 3:
            n_start, ans_display = run[0]
            n_end = run[-1][0]
            failures.append(
                f"CONSECUTIVE_ANSWERS: Q{n_start}–Q{n_end} all answer "
                f"'{ans_display}' ({len(run)} in a row)"
            )

    # ── Check 11: Answer flood ─────────────────────────────────────────────────
    # Same meaningful answer appearing 3+ times anywhere in the worksheet.
    # Single-letter MCQ choices (A/B/C/D) are exempt — they repeat by design.
    _ans_map: dict = {}   # answer_lower → [(q_number, original_answer)]
    for i, q in enumerate(questions, 1):
        ans = str(q.get("correct_answer") or q.get("answer") or "").strip()
        n = _q_number(q, i)
        if not ans or _is_mcq_letter(ans):
            continue
        key = ans.lower()
        if key not in _ans_map:
            _ans_map[key] = []
        _ans_map[key].append((n, ans))

    for key, occurrences in _ans_map.items():
        if len(occurrences) >= 3:
            nums = ", ".join(f"Q{n}" for n, _ in occurrences)
            ans_display = occurrences[0][1]
            failures.append(
                f"ANSWER_FLOOD: '{ans_display}' appears {len(occurrences)}x ({nums})"
            )

    # ── Check 12: O'clock wording contradiction ────────────────────────────────
    # "o'clock" is only valid when the answer is an exact hour (contains ":00").
    # If the LLM writes "o'clock" for a non-hour time like 10:35, it contradicts
    # the Python-computed answer that will be stamped over it.
    for i, q in enumerate(questions, 1):
        text = _q_text(q)
        answer = str(q.get("correct_answer") or q.get("answer") or "")
        if answer and _OCLOCK_RE.search(text) and ":00" not in answer:
            n = _q_number(q, i)
            failures.append(
                f"OCLOCK_MISMATCH: Q{n} says o'clock but answer is '{answer}' (not a whole hour)"
            )

    return len(failures) == 0, failures

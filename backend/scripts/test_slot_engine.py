#!/usr/bin/env python3
"""
Regression test for slot-based worksheet generation engine.

Part 1: Deterministic tests (no LLM, always runs)
Part 2: LLM pipeline tests (requires OPENAI_API_KEY env var)

Usage:
  cd backend
  python scripts/test_slot_engine.py           # deterministic only
  OPENAI_API_KEY=sk-... python scripts/test_slot_engine.py   # full test
"""

import os
import sys

# Allow running from backend/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    get_slot_plan,
    get_question_difficulty,
    validate_question,
    validate_worksheet_slots,
    validate_difficulty_sanity,
    SLOT_PLANS,
    SLOT_ORDER,
    VALID_FORMATS,
    _FORBIDDEN_VISUAL_PHRASES,
    run_slot_pipeline,
)


# ════════════════════════════════════════════════
# Part 1: Deterministic Tests (no LLM)
# ════════════════════════════════════════════════

def test_slot_plans():
    """Verify deterministic slot plans for supported q_counts."""
    print("=" * 60)
    print("1. SLOT PLAN TESTS")
    print("=" * 60)

    all_pass = True
    for q_count in [5, 10, 15, 20]:
        plan = get_slot_plan(q_count)
        counts = Counter(plan)
        expected = SLOT_PLANS[q_count]

        match = all(counts.get(s, 0) == expected.get(s, 0) for s in SLOT_ORDER)
        total_match = len(plan) == q_count
        status = "PASS" if (match and total_match) else "FAIL"
        if status == "FAIL":
            all_pass = False

        print(f"\n  q_count={q_count}: {status}")
        print(f"    Expected: {expected}")
        print(f"    Actual:   {dict(counts)}")
        print(f"    Length:   {len(plan)} (expected {q_count})")

    # Test non-standard counts (proportional fallback)
    for q_count in [3, 7, 12, 25]:
        plan = get_slot_plan(q_count)
        counts = Counter(plan)
        has_ed = counts.get("error_detection", 0) >= 1
        has_th = counts.get("thinking", 0) >= 1
        status = "PASS" if (has_ed and has_th and len(plan) == q_count) else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"\n  q_count={q_count} (proportional): {status}")
        print(f"    Counts: {dict(counts)}, len={len(plan)}")
        print(f"    error_detection >= 1: {has_ed}, thinking >= 1: {has_th}")

    return all_pass


def test_difficulty_mapping():
    """Verify per-question difficulty assignment."""
    print("\n" + "=" * 60)
    print("2. DIFFICULTY MAPPING TESTS")
    print("=" * 60)

    cases = [
        ("recognition", "easy", "easy"),
        ("recognition", "hard", "easy"),
        ("application", "easy", "easy"),
        ("application", "hard", "hard"),
        ("representation", "medium", "medium"),
        ("error_detection", "easy", "medium"),
        ("error_detection", "hard", "hard"),
        ("thinking", "easy", "medium"),
        ("thinking", "medium", "medium"),
        ("thinking", "hard", "hard"),
    ]

    all_pass = True
    for slot, ws_diff, expected in cases:
        actual = get_question_difficulty(slot, ws_diff)
        status = "PASS" if actual == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status}: {slot} + ws={ws_diff} -> {actual} (expected {expected})")

    return all_pass


def test_validators():
    """Test question-level and worksheet-level validators."""
    print("\n" + "=" * 60)
    print("3. VALIDATOR TESTS")
    print("=" * 60)

    all_pass = True

    # Good recognition question
    q1 = {"format": "column_setup", "question_text": "Write 502 - 178 in column form.", "pictorial_elements": [], "answer": "502 - 178"}
    issues = validate_question(q1, "recognition")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid recognition: {status}")
    if issues:
        all_pass = False

    # Bad format for recognition
    q2 = {"format": "word_problem", "question_text": "Aarav has 50 mangoes.", "pictorial_elements": [], "answer": "50"}
    issues = validate_question(q2, "recognition")
    status = "PASS" if issues else "FAIL: should reject"
    print(f"  Wrong format for recognition: {status}")
    if not issues:
        all_pass = False

    # Forbidden visual phrase
    q3 = {"format": "direct_compute", "question_text": "Look at the array and calculate 3 x 4.", "pictorial_elements": [], "answer": "12"}
    issues = validate_question(q3, "application")
    has_visual_issue = any("visual" in i or "array" in i for i in issues)
    status = "PASS" if has_visual_issue else "FAIL: should flag visual phrase"
    print(f"  Forbidden visual phrase: {status}")
    if not has_visual_issue:
        all_pass = False

    # Error detection without error language
    q4 = {"format": "error_spot", "question_text": "Calculate 502 - 178.", "pictorial_elements": [], "answer": "324"}
    issues = validate_question(q4, "error_detection")
    has_error_issue = any("error_detection" in i or "wrong" in i for i in issues)
    status = "PASS" if has_error_issue else "FAIL: should flag missing error language"
    print(f"  Error detection without mistake: {status}")
    if not has_error_issue:
        all_pass = False

    # Good error detection
    q5 = {"format": "error_spot", "question_text": "A student says 502 - 178 = 334. Find the mistake.", "pictorial_elements": [], "answer": "324"}
    issues = validate_question(q5, "error_detection")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid error detection: {status}")
    if issues:
        all_pass = False

    # Thinking without reasoning language
    q6 = {"format": "estimation", "question_text": "Add 345 + 278.", "pictorial_elements": [], "answer": "623"}
    issues = validate_question(q6, "thinking")
    has_thinking_issue = any("reasoning" in i for i in issues)
    status = "PASS" if has_thinking_issue else "FAIL: should flag pure computation"
    print(f"  Thinking without reasoning: {status}")
    if not has_thinking_issue:
        all_pass = False

    # Difficulty sanity
    issues = validate_difficulty_sanity("3-digit subtraction with borrowing across zero", "easy")
    status = "PASS" if issues else "FAIL: should flag easy + borrow across zero"
    print(f"  Difficulty sanity (borrow across zero + easy): {status}")
    if not issues:
        all_pass = False

    # Non-empty pictorial elements
    q7 = {"format": "column_setup", "question_text": "Write 502 - 178 in column form.", "pictorial_elements": [{"type": "array"}], "answer": "502 - 178"}
    issues = validate_question(q7, "recognition")
    has_pic_issue = any("pictorial" in i for i in issues)
    status = "PASS" if has_pic_issue else "FAIL: should flag non-empty pictorial_elements"
    print(f"  Non-empty pictorial_elements: {status}")
    if not has_pic_issue:
        all_pass = False

    # Worksheet-level: slot distribution
    fake_qs = [{"slot_type": s, "question_text": f"Q about {s}", "format": "x"} for s in get_slot_plan(5)]
    ws_issues = validate_worksheet_slots(fake_qs, 5)
    # Should pass on distribution (5 is a supported count)
    dist_issues = [i for i in ws_issues if "expected" in i and "got" in i]
    status = "PASS" if not dist_issues else f"FAIL: {dist_issues}"
    print(f"  Worksheet slot distribution (q=5): {status}")
    if dist_issues:
        all_pass = False

    return all_pass


# ════════════════════════════════════════════════
# Part 2: LLM Pipeline Tests (requires OPENAI_API_KEY)
# ════════════════════════════════════════════════

def test_llm_pipeline():
    """Full end-to-end test with LLM generation."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n" + "=" * 60)
        print("LLM PIPELINE TESTS — SKIPPED (OPENAI_API_KEY not set)")
        print("=" * 60)
        return

    from openai import OpenAI
    llm_client = OpenAI(api_key=api_key)

    print("\n" + "=" * 60)
    print("4. LLM PIPELINE TESTS")
    print("=" * 60)

    for q_count in [5, 10, 15, 20]:
        print(f"\n{'─' * 50}")
        print(f"Generating q_count={q_count}...")
        print(f"{'─' * 50}")

        meta, questions = run_slot_pipeline(
            client=llm_client,
            grade="Class 3",
            subject="Maths",
            topic="3-digit addition and subtraction",
            q_count=q_count,
            difficulty="medium",
            region="India",
        )

        print(f"  Micro-skill: {meta.get('micro_skill')}")
        print(f"  Skill focus: {meta.get('skill_focus')}")
        print(f"  Common mistakes: {meta.get('common_mistakes')}")
        print(f"  Parent tip: {meta.get('parent_tip')}")

        # Slot distribution
        actual = Counter(q.get("slot_type") for q in questions)
        expected = SLOT_PLANS.get(q_count, {})
        print(f"\n  Slot distribution (expected -> actual):")
        for slot in SLOT_ORDER:
            exp = expected.get(slot, "?")
            act = actual.get(slot, 0)
            match = "OK" if exp == act else "MISMATCH"
            print(f"    {slot}: {exp} -> {act}  {match}")

        # Formats per slot
        print(f"\n  Formats per slot:")
        for slot in SLOT_ORDER:
            slot_qs = [q for q in questions if q.get("slot_type") == slot]
            formats = [q.get("format", "?") for q in slot_qs]
            valid = VALID_FORMATS.get(slot, set())
            bad = [f for f in formats if f not in valid]
            status = "OK" if not bad else f"BAD: {bad}"
            print(f"    {slot}: {formats}  {status}")

        # Forbidden phrases
        forbidden_found = []
        for q in questions:
            text = q.get("question_text", "")
            if _FORBIDDEN_VISUAL_PHRASES.search(text):
                forbidden_found.append(f"q{q.get('id')}")
        print(f"\n  Forbidden phrases: {'none found' if not forbidden_found else forbidden_found}")

        # Sample questions (2 per slot_type)
        print(f"\n  Sample questions:")
        shown: dict[str, int] = {}
        for q in questions:
            slot = q.get("slot_type", "?")
            shown.setdefault(slot, 0)
            if shown[slot] < 2:
                text_preview = q.get("question_text", "")[:90]
                print(f"    [{slot}/{q.get('format')}] {text_preview}")
                print(f"      Answer: {q.get('answer', '?')}")
                shown[slot] += 1
        print()


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

if __name__ == "__main__":
    print("PracticeCraft Slot Engine — Regression Tests\n")

    p1 = test_slot_plans()
    p2 = test_difficulty_mapping()
    p3 = test_validators()

    print("\n" + "=" * 60)
    print("DETERMINISTIC SUMMARY")
    print("=" * 60)
    print(f"  Slot plans:     {'PASS' if p1 else 'FAIL'}")
    print(f"  Difficulty map: {'PASS' if p2 else 'FAIL'}")
    print(f"  Validators:     {'PASS' if p3 else 'FAIL'}")

    test_llm_pipeline()

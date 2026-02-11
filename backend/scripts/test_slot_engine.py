#!/usr/bin/env python3
"""
Regression test for slot-based worksheet generation engine v5.0.

Part 1: Deterministic tests (no LLM, always runs)
Part 2: LLM pipeline tests (requires OPENAI_API_KEY env var)
Part 3: Diversity test — 12 worksheets, asserts variation bank rotation

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
    validate_hard_difficulty_carry,
    SLOT_PLANS,
    SLOT_ORDER,
    VALID_FORMATS,
    _FORBIDDEN_VISUAL_PHRASES,
    CONTEXT_BANK,
    ERROR_PATTERN_BANK,
    THINKING_STYLE_BANK,
    NAME_BANKS,
    _make_seed,
    _pick_from_bank,
    _pick_name,
    _build_slot_instruction,
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

    # Bad format for recognition (simple_identify removed in v5)
    q2 = {"format": "simple_identify", "question_text": "Is 456 greater than 465?", "pictorial_elements": [], "answer": "No"}
    issues = validate_question(q2, "recognition")
    status = "PASS" if issues else "FAIL: should reject simple_identify"
    print(f"  Removed format simple_identify: {status}")
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

    # Error detection without numbers (new validator)
    q4b = {"format": "error_spot", "question_text": "A student made a mistake. Find the error.", "pictorial_elements": [], "answer": "324"}
    issues = validate_question(q4b, "error_detection")
    has_num_issue = any("wrong sum" in i or "original numbers" in i for i in issues)
    status = "PASS" if has_num_issue else "FAIL: should flag missing numbers"
    print(f"  Error detection without numbers: {status}")
    if not has_num_issue:
        all_pass = False

    # Good error detection
    q5 = {"format": "error_spot", "question_text": "A student says 502 - 178 = 334. Find the mistake.", "pictorial_elements": [], "answer": "324"}
    issues = validate_question(q5, "error_detection")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid error detection: {status}")
    if issues:
        all_pass = False

    # Thinking without reasoning language
    q6 = {"format": "thinking", "question_text": "Add 345 + 278.", "pictorial_elements": [], "answer": "623"}
    issues = validate_question(q6, "thinking")
    has_thinking_issue = any("reasoning" in i for i in issues)
    status = "PASS" if has_thinking_issue else "FAIL: should flag pure computation"
    print(f"  Thinking without reasoning: {status}")
    if not has_thinking_issue:
        all_pass = False

    # Good thinking question (new format "thinking")
    q6b = {"format": "thinking", "question_text": "Without calculating, which is greater: 345 + 278 or 400 + 200? Explain why.", "pictorial_elements": [], "answer": "345 + 278 = 623, which is greater"}
    issues = validate_question(q6b, "thinking")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid thinking: {status}")
    if issues:
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

    # Hard difficulty carry validator
    hard_qs = [
        {"slot_type": "application", "question_text": "Calculate 289 + 345.", "answer": "634"},
        {"slot_type": "application", "question_text": "Calculate 100 + 200.", "answer": "300"},
    ]
    carry_issues = validate_hard_difficulty_carry(hard_qs, "hard")
    # 289 + 345: ones = 9+5=14 (carry), tens = 8+4=12 (carry) => should pass
    status = "PASS" if not carry_issues else f"FAIL: {carry_issues}"
    print(f"  Hard carry validator (has carry): {status}")
    if carry_issues:
        all_pass = False

    no_carry_qs = [
        {"slot_type": "application", "question_text": "Calculate 100 + 200.", "answer": "300"},
    ]
    carry_issues = validate_hard_difficulty_carry(no_carry_qs, "hard")
    status = "PASS" if carry_issues else "FAIL: should flag no carry"
    print(f"  Hard carry validator (no carry): {status}")
    if not carry_issues:
        all_pass = False

    # Context repetition check
    ctx_qs = [
        {"slot_type": "application", "question_text": "Priya has 50 mangoes."},
        {"slot_type": "application", "question_text": "Rohan bought 30 mangoes."},
        {"slot_type": "recognition", "question_text": "Write 502 in column form."},
    ]
    ws_issues = validate_worksheet_slots(ctx_qs, 3)
    ctx_issues = [i for i in ws_issues if "context" in i and "mangoes" in i]
    status = "PASS" if ctx_issues else "FAIL: should flag repeated mangoes context"
    print(f"  Context repetition (mangoes x2): {status}")
    if not ctx_issues:
        all_pass = False

    return all_pass


def test_variation_banks():
    """Test variation bank mechanics: seed, picking, slot instructions."""
    print("\n" + "=" * 60)
    print("4. VARIATION BANK TESTS")
    print("=" * 60)

    all_pass = True

    # Seed is deterministic for same inputs
    s1 = _make_seed("Class 3", "3-digit addition", 5)
    s2 = _make_seed("Class 3", "3-digit addition", 5)
    status = "PASS" if s1 == s2 else "FAIL"
    print(f"  Seed determinism: {status} (s1={s1}, s2={s2})")
    if s1 != s2:
        all_pass = False

    # Different inputs give different seeds
    s3 = _make_seed("Class 3", "3-digit subtraction", 5)
    status = "PASS" if s1 != s3 else "FAIL"
    print(f"  Seed varies with topic: {status} (s1={s1}, s3={s3})")
    if s1 == s3:
        all_pass = False

    # Different q_count gives different seed
    s4 = _make_seed("Class 3", "3-digit addition", 10)
    status = "PASS" if s1 != s4 else "FAIL"
    print(f"  Seed varies with q_count: {status} (s1={s1}, s4={s4})")
    if s1 == s4:
        all_pass = False

    # Bank picking rotates
    seed = 42
    picked = [_pick_from_bank(CONTEXT_BANK, seed, i) for i in range(5)]
    items = [p["item"] for p in picked]
    unique = len(set(items))
    status = "PASS" if unique == 5 else f"FAIL: only {unique} unique out of 5"
    print(f"  Context bank rotation (5 picks): {status} -> {items}")
    if unique != 5:
        all_pass = False

    # Name picking rotates
    names = [_pick_name("India", seed, i) for i in range(5)]
    unique_names = len(set(names))
    status = "PASS" if unique_names == 5 else f"FAIL: only {unique_names} unique"
    print(f"  Name bank rotation (5 picks): {status} -> {names}")
    if unique_names != 5:
        all_pass = False

    # CONTEXT_BANK has 18 items
    status = "PASS" if len(CONTEXT_BANK) == 18 else f"FAIL: {len(CONTEXT_BANK)}"
    print(f"  CONTEXT_BANK size: {status} ({len(CONTEXT_BANK)} items)")
    if len(CONTEXT_BANK) != 18:
        all_pass = False

    # ERROR_PATTERN_BANK has 8 items
    status = "PASS" if len(ERROR_PATTERN_BANK) == 8 else f"FAIL: {len(ERROR_PATTERN_BANK)}"
    print(f"  ERROR_PATTERN_BANK size: {status} ({len(ERROR_PATTERN_BANK)} items)")
    if len(ERROR_PATTERN_BANK) != 8:
        all_pass = False

    # THINKING_STYLE_BANK has 6 items
    status = "PASS" if len(THINKING_STYLE_BANK) == 6 else f"FAIL: {len(THINKING_STYLE_BANK)}"
    print(f"  THINKING_STYLE_BANK size: {status} ({len(THINKING_STYLE_BANK)} items)")
    if len(THINKING_STYLE_BANK) != 6:
        all_pass = False

    # Slot instruction for application includes context
    slot_counter: dict[str, int] = {}
    instr = _build_slot_instruction("application", 0, seed, "India", slot_counter)
    has_context = "scenario" in instr.lower() or any(ctx["item"] in instr for ctx in CONTEXT_BANK)
    status = "PASS" if has_context else "FAIL: no context in instruction"
    print(f"  Application slot instruction: {status}")
    print(f"    -> {instr[:120]}...")
    if not has_context:
        all_pass = False

    # Slot instruction for error_detection includes error pattern
    instr = _build_slot_instruction("error_detection", 0, seed, "India", slot_counter)
    has_pattern = "wrong" in instr.lower() or "mistake" in instr.lower() or "pattern" in instr.lower()
    status = "PASS" if has_pattern else "FAIL: no error pattern in instruction"
    print(f"  Error detection slot instruction: {status}")
    print(f"    -> {instr[:120]}...")
    if not has_pattern:
        all_pass = False

    # Slot instruction for thinking includes style
    instr = _build_slot_instruction("thinking", 0, seed, "India", slot_counter)
    has_style = any(s["style"] in instr for s in THINKING_STYLE_BANK)
    status = "PASS" if has_style else "FAIL: no thinking style in instruction"
    print(f"  Thinking slot instruction: {status}")
    print(f"    -> {instr[:120]}...")
    if not has_style:
        all_pass = False

    # Tightened formats: recognition no longer has simple_identify
    status = "PASS" if "simple_identify" not in VALID_FORMATS["recognition"] else "FAIL"
    print(f"  Recognition formats tightened: {status} ({VALID_FORMATS['recognition']})")
    if "simple_identify" in VALID_FORMATS["recognition"]:
        all_pass = False

    # Tightened formats: thinking is now {"thinking"} only
    status = "PASS" if VALID_FORMATS["thinking"] == {"thinking"} else "FAIL"
    print(f"  Thinking format tightened: {status} ({VALID_FORMATS['thinking']})")
    if VALID_FORMATS["thinking"] != {"thinking"}:
        all_pass = False

    # Tightened formats: error_detection is now {"error_spot"} only
    status = "PASS" if VALID_FORMATS["error_detection"] == {"error_spot"} else "FAIL"
    print(f"  Error detection format tightened: {status} ({VALID_FORMATS['error_detection']})")
    if VALID_FORMATS["error_detection"] != {"error_spot"}:
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
        print("LLM PIPELINE TESTS - SKIPPED (OPENAI_API_KEY not set)")
        print("=" * 60)
        return

    from openai import OpenAI
    llm_client = OpenAI(api_key=api_key)

    print("\n" + "=" * 60)
    print("5. LLM PIPELINE TESTS")
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
# Part 3: Diversity Test (12 worksheets, same topic)
# ════════════════════════════════════════════════

def test_diversity():
    """Generate 12 worksheets for same topic (q=5), assert diversity metrics."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n" + "=" * 60)
        print("DIVERSITY TESTS - SKIPPED (OPENAI_API_KEY not set)")
        print("=" * 60)
        return

    from openai import OpenAI
    llm_client = OpenAI(api_key=api_key)

    print("\n" + "=" * 60)
    print("6. DIVERSITY TEST (12 worksheets, q=5)")
    print("=" * 60)

    all_contexts: list[str] = []
    all_thinking_styles: list[str] = []
    all_error_tags: list[str] = []
    all_names: list[str] = []
    forbidden_count = 0

    for ws_idx in range(12):
        # Vary q_count slightly to get different seeds
        q_count = 5
        # Use different "topics" to simulate different worksheets
        topics = [
            "3-digit addition and subtraction",
            "3-digit addition with carrying",
            "3-digit subtraction with borrowing",
            "addition and subtraction word problems",
            "place value and 3-digit numbers",
            "estimating sums and differences",
            "3-digit addition without carrying",
            "subtraction with borrowing across zero",
            "mental math strategies for addition",
            "comparing 3-digit sums",
            "3-digit column addition",
            "regrouping in subtraction",
        ]
        topic = topics[ws_idx % len(topics)]

        print(f"\n  Worksheet {ws_idx + 1}: {topic}")
        meta, questions = run_slot_pipeline(
            client=llm_client,
            grade="Class 3",
            subject="Maths",
            topic=topic,
            q_count=q_count,
            difficulty="medium",
            region="India",
        )

        for q in questions:
            text = q.get("question_text", "").lower()
            slot = q.get("slot_type", "")

            # Track contexts from application
            if slot == "application":
                for ctx in CONTEXT_BANK:
                    if ctx["item"] in text:
                        all_contexts.append(ctx["item"])
                        break

                # Track names
                for name in NAME_BANKS["India"]:
                    if name.lower() in text:
                        all_names.append(name)
                        break

            # Track thinking styles
            if slot == "thinking":
                for style in THINKING_STYLE_BANK:
                    # Rough check: does the question match the style?
                    style_keywords = {
                        "estimate_nearest_100": ["estimate", "nearest hundred"],
                        "closer_to": ["closer to"],
                        "threshold_check": ["above", "below"],
                        "compare_with_rounding": ["round"],
                        "bounds_reasoning": ["bound", "between"],
                        "which_is_reasonable": ["reasonable", "which of"],
                    }
                    keywords = style_keywords.get(style["style"], [])
                    if any(kw in text for kw in keywords):
                        all_thinking_styles.append(style["style"])
                        break

            # Track error patterns
            if slot == "error_detection":
                for err in ERROR_PATTERN_BANK:
                    if str(err["wrong_sum"]) in text:
                        all_error_tags.append(err["pattern_tag"])
                        break

            # Track forbidden phrases
            if _FORBIDDEN_VISUAL_PHRASES.search(q.get("question_text", "")):
                forbidden_count += 1

        # Show brief summary per worksheet
        slots = [q.get("slot_type", "?") for q in questions]
        fmts = [q.get("format", "?") for q in questions]
        print(f"    Slots: {slots}")
        print(f"    Formats: {fmts}")

    # ── Diversity assertions ──
    print(f"\n{'─' * 50}")
    print("DIVERSITY RESULTS")
    print(f"{'─' * 50}")

    unique_contexts = len(set(all_contexts))
    print(f"  Unique contexts: {unique_contexts} ({set(all_contexts)})")
    ctx_pass = unique_contexts >= 4
    print(f"  Context diversity (>= 4 unique): {'PASS' if ctx_pass else 'FAIL'}")

    unique_thinking = len(set(all_thinking_styles))
    print(f"  Unique thinking styles: {unique_thinking} ({set(all_thinking_styles)})")
    thinking_pass = unique_thinking >= 4
    print(f"  Thinking diversity (>= 4 unique): {'PASS' if thinking_pass else 'FAIL'}")

    unique_errors = len(set(all_error_tags))
    print(f"  Unique error patterns: {unique_errors} ({set(all_error_tags)})")
    error_pass = unique_errors >= 3
    print(f"  Error diversity (>= 3 unique): {'PASS' if error_pass else 'FAIL'}")

    unique_names = len(set(all_names))
    print(f"  Unique names: {unique_names} ({set(all_names)})")
    name_pass = unique_names >= 4
    print(f"  Name diversity (>= 4 unique): {'PASS' if name_pass else 'FAIL'}")

    print(f"  Forbidden visual phrases: {forbidden_count}")
    forbidden_pass = forbidden_count == 0
    print(f"  No forbidden phrases: {'PASS' if forbidden_pass else 'FAIL'}")

    overall = ctx_pass and thinking_pass and error_pass and name_pass and forbidden_pass
    print(f"\n  DIVERSITY OVERALL: {'PASS' if overall else 'FAIL'}")


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

if __name__ == "__main__":
    print("PracticeCraft Slot Engine v5.0 - Regression Tests\n")

    p1 = test_slot_plans()
    p2 = test_difficulty_mapping()
    p3 = test_validators()
    p4 = test_variation_banks()

    print("\n" + "=" * 60)
    print("DETERMINISTIC SUMMARY")
    print("=" * 60)
    print(f"  Slot plans:       {'PASS' if p1 else 'FAIL'}")
    print(f"  Difficulty map:   {'PASS' if p2 else 'FAIL'}")
    print(f"  Validators:       {'PASS' if p3 else 'FAIL'}")
    print(f"  Variation banks:  {'PASS' if p4 else 'FAIL'}")

    test_llm_pipeline()
    test_diversity()

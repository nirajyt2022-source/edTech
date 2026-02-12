#!/usr/bin/env python3
"""
Regression test for slot-based worksheet generation engine v6.0.

Part 1: Deterministic tests (no LLM, always runs)
Part 2: LLM pipeline tests (requires OPENAI_API_KEY env var)
Part 3: 30-worksheet diversity test (requires OPENAI_API_KEY)

Usage:
  cd backend
  python scripts/test_slot_engine.py           # deterministic only
  OPENAI_API_KEY=sk-... python scripts/test_slot_engine.py   # full test
"""

import os
import random
import re
import sys
import tempfile

# Allow running from backend/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    get_slot_plan,
    get_question_difficulty,
    validate_question,
    validate_worksheet_slots,
    validate_difficulty_sanity,
    validate_error_uses_backend_numbers,
    validate_hard_difficulty_carry,
    hydrate_visuals,
    enforce_visuals_only,
    verify_visual_contract,
    compute_wrong,
    _build_slot_instruction,
    _make_seed,
    pick_context,
    pick_name,
    pick_error,
    pick_thinking_style,
    SLOT_PLANS,
    SLOT_ORDER,
    VALID_FORMATS,
    _FORBIDDEN_VISUAL_PHRASES,
    _ALL_ERRORS,
    CONTEXT_BANK,
    CARRY_PAIRS,
    ERROR_TAGS,
    THINKING_STYLE_BANK,
    NAME_BANKS,
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


def test_error_computation():
    """Test deterministic error computation for all tags and pairs."""
    print("\n" + "=" * 60)
    print("3. ERROR COMPUTATION TESTS")
    print("=" * 60)

    all_pass = True

    # Total patterns: 15 pairs x 5 tags = 75
    total = len(CARRY_PAIRS) * len(ERROR_TAGS)
    status = "PASS" if len(_ALL_ERRORS) == total else "FAIL"
    print(f"  Precomputed errors: {len(_ALL_ERRORS)} (expected {total}): {status}")
    if len(_ALL_ERRORS) != total:
        all_pass = False

    # Verify all wrong != correct
    wrong_eq_correct = 0
    out_of_range = 0
    for err in _ALL_ERRORS:
        if err["wrong"] == err["correct"]:
            wrong_eq_correct += 1
        if not (100 <= err["wrong"] <= 999):
            out_of_range += 1

    status = "PASS" if wrong_eq_correct == 0 else f"FAIL: {wrong_eq_correct} wrong==correct"
    print(f"  All wrong != correct: {status}")
    if wrong_eq_correct:
        all_pass = False

    status = "PASS" if out_of_range == 0 else f"FAIL: {out_of_range} out of 3-digit range"
    print(f"  All wrong in 3-digit range: {status}")
    if out_of_range:
        all_pass = False

    # Spot-check (345, 278)
    cases = [
        (345, 278, "lost_carry_ones", 613),
        (345, 278, "lost_carry_tens", 523),
        (345, 278, "double_carry", 633),
        (345, 278, "carry_to_wrong_col", 713),
        (345, 278, "no_carry_digitwise", 513),
    ]
    for a, b, tag, expected_wrong in cases:
        actual = compute_wrong(a, b, tag)
        correct = a + b
        status = "PASS" if actual == expected_wrong else f"FAIL: got {actual}"
        print(f"  {tag}({a}+{b}): wrong={actual}, correct={correct}: {status}")
        if actual != expected_wrong:
            all_pass = False

    # All 5 tags produce distinct wrong answers for same pair
    pair_wrongs = {}
    for a, b in CARRY_PAIRS[:3]:
        wrongs = set()
        for tag in ERROR_TAGS:
            wrongs.add(compute_wrong(a, b, tag))
        pair_wrongs[(a, b)] = len(wrongs)
        status = "PASS" if len(wrongs) == 5 else f"FAIL: only {len(wrongs)} distinct"
        print(f"  Distinct wrongs for ({a},{b}): {len(wrongs)}: {status}")
        if len(wrongs) != 5:
            all_pass = False

    return all_pass


def test_validators():
    """Test question-level and worksheet-level validators."""
    print("\n" + "=" * 60)
    print("4. VALIDATOR TESTS")
    print("=" * 60)

    all_pass = True

    # Good recognition
    q1 = {"format": "column_setup", "question_text": "Write 502 - 178 in column form.", "pictorial_elements": [], "answer": "502 - 178"}
    issues = validate_question(q1, "recognition")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid recognition: {status}")
    if issues:
        all_pass = False

    # application must be word_problem now
    q2 = {"format": "direct_compute", "question_text": "Calculate 345 + 278.", "pictorial_elements": [], "answer": "623"}
    issues = validate_question(q2, "application")
    has_fmt_issue = any("format" in i for i in issues)
    status = "PASS" if has_fmt_issue else "FAIL: should reject direct_compute for application"
    print(f"  Reject direct_compute for application: {status}")
    if not has_fmt_issue:
        all_pass = False

    # Good word_problem
    q2b = {"format": "word_problem", "question_text": "Aarav has 345 books and buys 278 more. How many does he have?", "pictorial_elements": [], "answer": "623"}
    issues = validate_question(q2b, "application")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid word_problem: {status}")
    if issues:
        all_pass = False

    # Forbidden visual
    q3 = {"format": "word_problem", "question_text": "Look at the array and calculate 3 x 4.", "pictorial_elements": [], "answer": "12"}
    issues = validate_question(q3, "application")
    has_visual = any("visual" in i or "array" in i for i in issues)
    status = "PASS" if has_visual else "FAIL: should flag visual phrase"
    print(f"  Forbidden visual phrase: {status}")
    if not has_visual:
        all_pass = False

    # Error detection without error language
    q4 = {"format": "error_spot", "question_text": "Calculate 502 - 178.", "pictorial_elements": [], "answer": "324"}
    issues = validate_question(q4, "error_detection")
    has_error_issue = any("error_detection" in i or "wrong" in i for i in issues)
    status = "PASS" if has_error_issue else "FAIL"
    print(f"  Error detection without mistake: {status}")
    if not has_error_issue:
        all_pass = False

    # Error detection without numbers
    q4b = {"format": "error_spot", "question_text": "A student made a mistake. Find the error.", "pictorial_elements": [], "answer": "324"}
    issues = validate_question(q4b, "error_detection")
    has_num_issue = any("wrong sum" in i or "original numbers" in i for i in issues)
    status = "PASS" if has_num_issue else "FAIL"
    print(f"  Error detection without numbers: {status}")
    if not has_num_issue:
        all_pass = False

    # Good error detection
    q5 = {"format": "error_spot", "question_text": "A student says 345 + 278 = 513. Find the mistake.", "pictorial_elements": [], "answer": "623"}
    issues = validate_question(q5, "error_detection")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid error detection: {status}")
    if issues:
        all_pass = False

    # Validate error uses backend numbers
    chosen = {"error": {"a": 345, "b": 278, "wrong": 513, "correct": 623}}
    err_issues = validate_error_uses_backend_numbers(q5, chosen)
    status = "PASS" if not err_issues else f"FAIL: {err_issues}"
    print(f"  Error uses backend numbers: {status}")
    if err_issues:
        all_pass = False

    # Error uses wrong backend numbers
    q5_wrong = {"format": "error_spot", "question_text": "A student says 456 + 367 = 713. Find the mistake.", "pictorial_elements": [], "answer": "823"}
    err_issues = validate_error_uses_backend_numbers(q5_wrong, chosen)
    status = "PASS" if err_issues else "FAIL: should flag wrong numbers"
    print(f"  Error with wrong backend numbers: {status}")
    if not err_issues:
        all_pass = False

    # Good thinking
    q6 = {"format": "thinking", "question_text": "Without calculating, which is greater: 345 + 278 or 400 + 200? Explain.", "pictorial_elements": [], "answer": "345 + 278 = 623"}
    issues = validate_question(q6, "thinking")
    status = "PASS" if not issues else f"FAIL: {issues}"
    print(f"  Valid thinking: {status}")
    if issues:
        all_pass = False

    # Thinking without reasoning
    q6b = {"format": "thinking", "question_text": "Add 345 + 278.", "pictorial_elements": [], "answer": "623"}
    issues = validate_question(q6b, "thinking")
    has_think_issue = any("reasoning" in i for i in issues)
    status = "PASS" if has_think_issue else "FAIL"
    print(f"  Thinking without reasoning: {status}")
    if not has_think_issue:
        all_pass = False

    # Difficulty sanity
    issues = validate_difficulty_sanity("3-digit subtraction with borrowing across zero", "easy")
    status = "PASS" if issues else "FAIL"
    print(f"  Difficulty sanity (borrow + easy): {status}")
    if not issues:
        all_pass = False

    # Hard carry validator
    hard_qs = [{"slot_type": "application", "question_text": "Calculate 289 + 345.", "answer": "634"}]
    carry_issues = validate_hard_difficulty_carry(hard_qs, "hard")
    status = "PASS" if not carry_issues else f"FAIL: {carry_issues}"
    print(f"  Hard carry (has carry): {status}")
    if carry_issues:
        all_pass = False

    no_carry_qs = [{"slot_type": "application", "question_text": "Calculate 100 + 200.", "answer": "300"}]
    carry_issues = validate_hard_difficulty_carry(no_carry_qs, "hard")
    status = "PASS" if carry_issues else "FAIL"
    print(f"  Hard carry (no carry): {status}")
    if not carry_issues:
        all_pass = False

    # Context repetition
    ctx_qs = [
        {"slot_type": "application", "question_text": "Priya has 50 coins."},
        {"slot_type": "application", "question_text": "Rohan bought 30 coins."},
    ]
    ws_issues = validate_worksheet_slots(ctx_qs, 2)
    ctx_issues = [i for i in ws_issues if "context" in i and "coins" in i]
    status = "PASS" if ctx_issues else "FAIL"
    print(f"  Context repetition (coins x2): {status}")
    if not ctx_issues:
        all_pass = False

    return all_pass


def test_variation_banks():
    """Test variation bank mechanics: seed, picking, slot instructions."""
    print("\n" + "=" * 60)
    print("5. VARIATION BANK TESTS")
    print("=" * 60)

    all_pass = True

    # Seed determinism
    s1 = _make_seed("Class 3", "3-digit addition", 5, 0)
    s2 = _make_seed("Class 3", "3-digit addition", 5, 0)
    status = "PASS" if s1 == s2 else "FAIL"
    print(f"  Seed determinism: {status}")
    if s1 != s2:
        all_pass = False

    # Seed varies with topic
    s3 = _make_seed("Class 3", "3-digit subtraction", 5, 0)
    status = "PASS" if s1 != s3 else "FAIL"
    print(f"  Seed varies with topic: {status}")
    if s1 == s3:
        all_pass = False

    # Seed varies with history_count (ensures uniqueness across requests)
    s4 = _make_seed("Class 3", "3-digit addition", 5, 1)
    status = "PASS" if s1 != s4 else "FAIL"
    print(f"  Seed varies with history_count: {status}")
    if s1 == s4:
        all_pass = False

    # Context picking avoids used items
    rng = random.Random(42)
    ctx1 = pick_context(rng, [])
    ctx2 = pick_context(rng, [ctx1["item"]])
    status = "PASS" if ctx1["item"] != ctx2["item"] else "FAIL"
    print(f"  Context avoidance: {status} ({ctx1['item']} != {ctx2['item']})")
    if ctx1["item"] == ctx2["item"]:
        all_pass = False

    # Error picking avoids used IDs
    rng = random.Random(42)
    err1 = pick_error(rng, [])
    err2 = pick_error(rng, [err1["id"]])
    status = "PASS" if err1["id"] != err2["id"] else "FAIL"
    print(f"  Error avoidance: {status} ({err1['id'][:30]} != {err2['id'][:30]})")
    if err1["id"] == err2["id"]:
        all_pass = False

    # Thinking style picking avoids used styles
    rng = random.Random(42)
    st1 = pick_thinking_style(rng, [])
    st2 = pick_thinking_style(rng, [st1["style"]])
    status = "PASS" if st1["style"] != st2["style"] else "FAIL"
    print(f"  Style avoidance: {status} ({st1['style']} != {st2['style']})")
    if st1["style"] == st2["style"]:
        all_pass = False

    # Pick 18 contexts (exhausts bank), then picks from full bank
    rng = random.Random(42)
    all_items = set()
    for i in range(18):
        ctx = pick_context(rng, list(all_items))
        all_items.add(ctx["item"])
    status = "PASS" if len(all_items) == 18 else f"FAIL: {len(all_items)}"
    print(f"  18 unique contexts from 18-item bank: {status}")
    if len(all_items) != 18:
        all_pass = False

    # 19th pick wraps around (no crash)
    ctx19 = pick_context(rng, list(all_items))
    status = "PASS" if ctx19["item"] in [c["item"] for c in CONTEXT_BANK] else "FAIL"
    print(f"  19th pick wraps: {status} (got {ctx19['item']})")

    # Bank sizes
    print(f"  CONTEXT_BANK: {len(CONTEXT_BANK)} items (expected 18): {'PASS' if len(CONTEXT_BANK) == 18 else 'FAIL'}")
    print(f"  _ALL_ERRORS: {len(_ALL_ERRORS)} patterns (expected 75): {'PASS' if len(_ALL_ERRORS) == 75 else 'FAIL'}")
    print(f"  THINKING_STYLE_BANK: {len(THINKING_STYLE_BANK)} styles (expected 6): {'PASS' if len(THINKING_STYLE_BANK) == 6 else 'FAIL'}")
    if len(CONTEXT_BANK) != 18 or len(_ALL_ERRORS) != 75 or len(THINKING_STYLE_BANK) != 6:
        all_pass = False

    # Tightened formats
    status = "PASS" if VALID_FORMATS["application"] == {"word_problem"} else "FAIL"
    print(f"  Application format tightened: {status} ({VALID_FORMATS['application']})")
    if VALID_FORMATS["application"] != {"word_problem"}:
        all_pass = False

    status = "PASS" if VALID_FORMATS["thinking"] == {"thinking"} else "FAIL"
    print(f"  Thinking format tightened: {status}")
    if VALID_FORMATS["thinking"] != {"thinking"}:
        all_pass = False

    status = "PASS" if VALID_FORMATS["error_detection"] == {"error_spot"} else "FAIL"
    print(f"  Error detection format tightened: {status}")
    if VALID_FORMATS["error_detection"] != {"error_spot"}:
        all_pass = False

    # Slot instructions contain expected content
    err = _ALL_ERRORS[0]
    variant_err = {"error": err}
    instr = _build_slot_instruction("error_detection", variant_err)
    status = "PASS" if str(err["wrong"]) in instr and str(err["a"]) in instr else "FAIL"
    print(f"  Error instruction includes numbers: {status}")
    if str(err["wrong"]) not in instr:
        all_pass = False

    variant_ctx = {"context": CONTEXT_BANK[0], "name": "Priya"}
    instr = _build_slot_instruction("application", variant_ctx)
    status = "PASS" if CONTEXT_BANK[0]["item"] in instr and "Priya" in instr else "FAIL"
    print(f"  Application instruction includes context+name: {status}")
    if CONTEXT_BANK[0]["item"] not in instr:
        all_pass = False

    variant_style = {"style": THINKING_STYLE_BANK[0]}
    instr = _build_slot_instruction("thinking", variant_style)
    status = "PASS" if THINKING_STYLE_BANK[0]["style"] in instr else "FAIL"
    print(f"  Thinking instruction includes style: {status}")
    if THINKING_STYLE_BANK[0]["style"] not in instr:
        all_pass = False

    return all_pass


def test_history_store():
    """Test history store functions."""
    print("\n" + "=" * 60)
    print("6. HISTORY STORE TESTS")
    print("=" * 60)

    all_pass = True

    # Use a temp file for testing
    import app.services.history_store as hs
    original_path = hs.HISTORY_FILE
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    hs.HISTORY_FILE = __import__("pathlib").Path(tmp_path)

    try:
        # Load empty history
        history = hs.load_history()
        status = "PASS" if history == [] else "FAIL"
        print(f"  Empty history: {status}")
        if history != []:
            all_pass = False

        # Save and load
        record = hs.build_worksheet_record(
            grade="Class 3", topic="addition",
            questions=[{"question_text": "Write 345 + 278 in column form.", "format": "column_setup"}],
            used_contexts=["books", "coins"],
            used_error_ids=["lost_carry_ones_345_278"],
            used_thinking_styles=["closer_to"],
        )
        hs.update_history(record)
        history = hs.load_history()
        status = "PASS" if len(history) == 1 else "FAIL"
        print(f"  Save+load 1 record: {status}")
        if len(history) != 1:
            all_pass = False

        # Avoid state aggregation
        avoid = hs.get_avoid_state()
        status = "PASS" if "books" in avoid["used_contexts"] and "coins" in avoid["used_contexts"] else "FAIL"
        print(f"  Avoid state contexts: {status}")
        if "books" not in avoid["used_contexts"]:
            all_pass = False

        status = "PASS" if "closer_to" in avoid["used_thinking_styles"] else "FAIL"
        print(f"  Avoid state styles: {status}")
        if "closer_to" not in avoid["used_thinking_styles"]:
            all_pass = False

        # Question hash
        h1 = hs.hash_question("Write 345 + 278 in column form.")
        h2 = hs.hash_question("write 345 + 278 in column form.")
        status = "PASS" if h1 == h2 else "FAIL"
        print(f"  Question hash case-insensitive: {status}")
        if h1 != h2:
            all_pass = False

        # Template hash
        h3 = hs.hash_question_template("A student says 345 + 278 = 513. Find the mistake.")
        h4 = hs.hash_question_template("A student says 456 + 367 = 713. Find the mistake.")
        status = "PASS" if h3 == h4 else "FAIL"
        print(f"  Template hash normalizes numbers: {status}")
        if h3 != h4:
            all_pass = False

        # MAX_HISTORY limit
        for _ in range(35):
            hs.update_history(record)
        history = hs.load_history()
        status = "PASS" if len(history) <= hs.MAX_HISTORY else f"FAIL: {len(history)}"
        print(f"  History capped at {hs.MAX_HISTORY}: {status}")
        if len(history) > hs.MAX_HISTORY:
            all_pass = False

    finally:
        hs.HISTORY_FILE = original_path
        os.unlink(tmp_path)

    return all_pass


def test_seeded_diversity_deterministic():
    """Simulate 30 worksheet generations and check diversity of picks (no LLM)."""
    print("\n" + "=" * 60)
    print("7. SEEDED DIVERSITY (deterministic simulation)")
    print("=" * 60)

    all_pass = True

    all_contexts: list[str] = []
    all_error_ids: list[str] = []
    all_error_tags: list[str] = []
    all_thinking_styles: list[str] = []

    # Simulate 30 worksheets
    cumulative_contexts: list[str] = []
    cumulative_error_ids: list[str] = []
    cumulative_styles: list[str] = []

    for ws_idx in range(30):
        seed = _make_seed("Class 3", "3-digit addition", 5, ws_idx)
        rng = random.Random(seed)

        # Pick 1 context (for 1 application slot in q=5)
        ctx = pick_context(rng, cumulative_contexts)
        all_contexts.append(ctx["item"])
        cumulative_contexts.append(ctx["item"])

        # Pick 1 error
        err = pick_error(rng, cumulative_error_ids)
        all_error_ids.append(err["id"])
        all_error_tags.append(err["tag"])
        cumulative_error_ids.append(err["id"])

        # Pick 1 thinking style
        style = pick_thinking_style(rng, cumulative_styles)
        all_thinking_styles.append(style["style"])
        cumulative_styles.append(style["style"])

    unique_contexts = len(set(all_contexts))
    print(f"  Unique contexts across 30 ws: {unique_contexts}")
    ctx_pass = unique_contexts >= 10
    print(f"    >= 10: {'PASS' if ctx_pass else 'FAIL'}")
    if not ctx_pass:
        all_pass = False

    unique_tags = len(set(all_error_tags))
    print(f"  Unique error tags across 30 ws: {unique_tags}")
    tag_pass = unique_tags >= 4
    print(f"    >= 4: {'PASS' if tag_pass else 'FAIL'}")
    if not tag_pass:
        all_pass = False

    unique_ids = len(set(all_error_ids))
    print(f"  Unique error IDs across 30 ws: {unique_ids}")

    # No single error_id more than 2 times
    id_counts = Counter(all_error_ids)
    max_id_count = max(id_counts.values()) if id_counts else 0
    id_repeat_pass = max_id_count <= 2
    print(f"  Max error_id repetition: {max_id_count}")
    print(f"    <= 2: {'PASS' if id_repeat_pass else 'FAIL'}")
    if not id_repeat_pass:
        all_pass = False

    unique_styles = len(set(all_thinking_styles))
    print(f"  Unique thinking styles across 30 ws: {unique_styles}")
    style_pass = unique_styles >= 4
    print(f"    >= 4: {'PASS' if style_pass else 'FAIL'}")
    if not style_pass:
        all_pass = False

    # Print distribution
    print(f"\n  Context distribution: {dict(Counter(all_contexts).most_common(5))} ...")
    print(f"  Error tag distribution: {dict(Counter(all_error_tags))}")
    print(f"  Thinking style distribution: {dict(Counter(all_thinking_styles))}")

    return all_pass


def test_visual_hydration():
    """Test visual hydration infers correct visual specs from question text."""
    print("\n" + "=" * 60)
    print("8. VISUAL HYDRATION TESTS")
    print("=" * 60)

    all_pass = True

    # Fixture: 5 questions with ALL visual fields missing (matches user-reported bug)
    questions = [
        {
            "id": 1, "slot_type": "recognition", "format": "column_setup",
            "question_text": "Write 462 + 359 in column form.",
            "pictorial_elements": [], "answer": "821", "difficulty": "easy",
        },
        {
            "id": 2, "slot_type": "application", "format": "word_problem",
            "question_text": "Aarav has 284 crayons. He finds 578 more crayons in the art supply cupboard. How many crayons does Aarav have in total now?",
            "pictorial_elements": [], "answer": "862", "difficulty": "hard",
        },
        {
            "id": 3, "slot_type": "representation", "format": "missing_number",
            "question_text": "___ + 247 = 578",
            "pictorial_elements": [], "answer": "331", "difficulty": "hard",
        },
        {
            "id": 4, "slot_type": "error_detection", "format": "error_spot",
            "question_text": "A student calculated 386 + 247 and found the sum to be 523. What mistake did the student make? What is the correct answer?",
            "pictorial_elements": [], "answer": "The student forgot to regroup. Correct answer is 633.", "difficulty": "hard",
        },
        {
            "id": 5, "slot_type": "thinking", "format": "thinking",
            "question_text": "Consider the addition of 578 and 367. Without calculating, is the answer closer to 900 or 1000? Explain your reasoning.",
            "pictorial_elements": [], "answer": "closer to 900", "difficulty": "hard",
        },
    ]

    hydrated = hydrate_visuals(questions)

    # ── q1: BASE_TEN_REGROUPING ──
    q1 = hydrated[0]
    checks_q1 = [
        ("q1.representation", q1.get("representation"), "PICTORIAL_MODEL"),
        ("q1.visual_spec.model_id", (q1.get("visual_spec") or {}).get("model_id"), "BASE_TEN_REGROUPING"),
        ("q1.visual_spec.numbers", (q1.get("visual_spec") or {}).get("numbers"), [462, 359]),
        ("q1.visual_spec.operation", (q1.get("visual_spec") or {}).get("operation"), "addition"),
        ("q1.visual_model_ref", q1.get("visual_model_ref"), "BASE_TEN_REGROUPING"),
    ]
    for label, actual, expected in checks_q1:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} = {expected}" + ("" if ok else f" (got {actual})"))
        if not ok:
            all_pass = False

    # ── q2: BASE_TEN_REGROUPING (word problem with "more" + "total") ──
    q2 = hydrated[1]
    checks_q2 = [
        ("q2.representation", q2.get("representation"), "PICTORIAL_MODEL"),
        ("q2.visual_spec.model_id", (q2.get("visual_spec") or {}).get("model_id"), "BASE_TEN_REGROUPING"),
        ("q2.visual_spec.numbers", (q2.get("visual_spec") or {}).get("numbers"), [284, 578]),
        ("q2.visual_spec.operation", (q2.get("visual_spec") or {}).get("operation"), "addition"),
    ]
    for label, actual, expected in checks_q2:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} = {expected}" + ("" if ok else f" (got {actual})"))
        if not ok:
            all_pass = False

    # ── q3: NUMBER_LINE (missing number "___ + 247 = 578") ──
    q3 = hydrated[2]
    # missing = 578 - 247 = 331; markers = [247, 331, 578]
    checks_q3 = [
        ("q3.representation", q3.get("representation"), "PICTORIAL_MODEL"),
        ("q3.visual_spec.model_id", (q3.get("visual_spec") or {}).get("model_id"), "NUMBER_LINE"),
        ("q3.visual_spec.markers", (q3.get("visual_spec") or {}).get("markers"), [247, 331, 578]),
    ]
    for label, actual, expected in checks_q3:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} = {expected}" + ("" if ok else f" (got {actual})"))
        if not ok:
            all_pass = False

    # ── q4: BASE_TEN_REGROUPING (error spot with "+") ──
    q4 = hydrated[3]
    checks_q4 = [
        ("q4.representation", q4.get("representation"), "PICTORIAL_MODEL"),
        ("q4.visual_spec.model_id", (q4.get("visual_spec") or {}).get("model_id"), "BASE_TEN_REGROUPING"),
        ("q4.visual_spec.numbers", (q4.get("visual_spec") or {}).get("numbers"), [386, 247]),
    ]
    for label, actual, expected in checks_q4:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} = {expected}" + ("" if ok else f" (got {actual})"))
        if not ok:
            all_pass = False

    # ── q5: NUMBER_LINE (closer to / estimation) ──
    q5 = hydrated[4]
    checks_q5 = [
        ("q5.representation", q5.get("representation"), "PICTORIAL_MODEL"),
        ("q5.visual_spec.model_id", (q5.get("visual_spec") or {}).get("model_id"), "NUMBER_LINE"),
        ("q5.visual_spec.start", (q5.get("visual_spec") or {}).get("start"), 800),
        ("q5.visual_spec.end", (q5.get("visual_spec") or {}).get("end"), 1100),
        ("q5.visual_spec.tick_interval", (q5.get("visual_spec") or {}).get("tick_interval"), 50),
        ("q5.visual_spec.markers", (q5.get("visual_spec") or {}).get("markers"), [900, 945, 1000]),
        ("q5.visual_model_ref", q5.get("visual_model_ref"), "NUMBER_LINE"),
    ]
    for label, actual, expected in checks_q5:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} = {expected}" + ("" if ok else f" (got {actual})"))
        if not ok:
            all_pass = False

    # ── Verification table ──
    table = verify_visual_contract(hydrated)
    print(f"\n  Verification table:\n{table}")

    return all_pass


def test_endpoint_visual_propagation():
    """Test that hydrated visuals survive the _slot_to_question serializer."""
    print("\n" + "=" * 60)
    print("9. ENDPOINT VISUAL PROPAGATION TEST")
    print("=" * 60)

    from app.api.worksheets import _slot_to_question, _map_visual_fields

    all_pass = True

    # Simulate raw slot-engine output (pre-hydration, as run_slot_pipeline returns)
    slot_questions = [
        {
            "id": 1, "slot_type": "recognition", "format": "column_setup",
            "question_text": "Write 456 + 279 in column form.",
            "pictorial_elements": [], "answer": "735", "difficulty": "easy",
        },
        {
            "id": 2, "slot_type": "application", "format": "word_problem",
            "question_text": "Priya has 310 stickers. She buys 250 more. How many total?",
            "pictorial_elements": [], "answer": "560", "difficulty": "medium",
        },
        {
            "id": 3, "slot_type": "thinking", "format": "thinking",
            "question_text": "Is 578 + 367 closer to 900 or 1000? Explain.",
            "pictorial_elements": [], "answer": "closer to 900", "difficulty": "hard",
        },
    ]

    # Safety-net hydration (same call the endpoint now makes)
    hydrate_visuals(slot_questions)

    # Map through the real serializer
    api_questions = [_slot_to_question(q, i) for i, q in enumerate(slot_questions)]

    # q1: must be base_ten_regrouping
    q1 = api_questions[0]
    checks = [
        ("q1.visual_type", q1.visual_type, "base_ten_regrouping"),
        ("q1.visual_data.numbers", (q1.visual_data or {}).get("numbers"), [456, 279]),
        ("q1.visual_data.operation", (q1.visual_data or {}).get("operation"), "addition"),
    ]
    for label, actual, expected in checks:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} == {expected!r}" + ("" if ok else f" (got {actual!r})"))
        if not ok:
            all_pass = False

    # q2: word problem with "more" + "total" → base_ten_regrouping
    q2 = api_questions[1]
    checks2 = [
        ("q2.visual_type", q2.visual_type, "base_ten_regrouping"),
        ("q2.visual_data.numbers", (q2.visual_data or {}).get("numbers"), [310, 250]),
        ("q2.visual_data.operation", (q2.visual_data or {}).get("operation"), "addition"),
    ]
    for label, actual, expected in checks2:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} == {expected!r}" + ("" if ok else f" (got {actual!r})"))
        if not ok:
            all_pass = False

    # q3: number_line
    q3 = api_questions[2]
    checks3 = [
        ("q3.visual_type", q3.visual_type, "number_line"),
        ("q3.visual_data.step", (q3.visual_data or {}).get("step"), 50),
        ("q3.visual_data.highlight", (q3.visual_data or {}).get("highlight"), 945),
    ]
    for label, actual, expected in checks3:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} == {expected!r}" + ("" if ok else f" (got {actual!r})"))
        if not ok:
            all_pass = False

    # Pydantic serialization roundtrip
    q1_dict = q1.model_dump()
    ok_ser = q1_dict["visual_type"] == "base_ten_regrouping" and q1_dict["visual_data"]["numbers"] == [456, 279]
    print(f"  {'PASS' if ok_ser else 'FAIL'}: model_dump preserves visual fields")
    if not ok_ser:
        all_pass = False

    return all_pass


def test_visuals_only_mode():
    """Test broadened visual hydration: 5-question fixture → >=4/5 pictorial."""
    print("\n" + "=" * 60)
    print("10. VISUAL COVERAGE (broad rules + endpoint mapper)")
    print("=" * 60)

    from app.api.worksheets import _slot_to_question

    all_pass = True

    questions = [
        {
            "id": 1, "slot_type": "recognition", "format": "column_setup",
            "question_text": "Write 456 + 279 in column form.",
            "pictorial_elements": [], "answer": "735", "difficulty": "easy",
        },
        {
            "id": 2, "slot_type": "application", "format": "word_problem",
            "question_text": "Aarav has 384 stickers. He got 279 more from his friend. How many stickers does he have in total?",
            "pictorial_elements": [], "answer": "663", "difficulty": "medium",
        },
        {
            "id": 3, "slot_type": "representation", "format": "missing_number",
            "question_text": "___ + 295 = 432",
            "pictorial_elements": [], "answer": "137", "difficulty": "medium",
        },
        {
            "id": 4, "slot_type": "error_detection", "format": "error_spot",
            "question_text": "A student says 386 + 247 = 523. Find the mistake and give the correct answer.",
            "pictorial_elements": [], "answer": "633", "difficulty": "medium",
        },
        {
            "id": 5, "slot_type": "thinking", "format": "thinking",
            "question_text": "Is 578 + 456 closer to 1000 or 1100? Explain your thinking.",
            "pictorial_elements": [], "answer": "closer to 1000", "difficulty": "hard",
        },
    ]

    hydrate_visuals(questions, visuals_only=True)
    enforce_visuals_only(questions)

    # Map through endpoint serializer (visual_type / visual_data)
    api_qs = [_slot_to_question(q, i) for i, q in enumerate(questions)]

    visual_count = sum(1 for q in api_qs if q.visual_type is not None)
    total = len(api_qs)

    print(f"  Visual coverage: {visual_count}/{total}")
    coverage_pass = visual_count >= 4
    print(f"  >= 4/5 pictorial: {'PASS' if coverage_pass else 'FAIL'}")
    if not coverage_pass:
        all_pass = False

    # Specific assertions
    checks = [
        ("q1.visual_type", api_qs[0].visual_type, "base_ten_regrouping"),
        ("q2.visual_type", api_qs[1].visual_type, "base_ten_regrouping"),
        ("q3.visual_type", api_qs[2].visual_type, "number_line"),
        ("q3.highlight", (api_qs[2].visual_data or {}).get("highlight"), 137),
        ("q4.visual_type", api_qs[3].visual_type, "base_ten_regrouping"),
        ("q5.visual_type", api_qs[4].visual_type, "number_line"),
        ("q5.highlight", (api_qs[4].visual_data or {}).get("highlight"), 1034),
    ]
    for label, actual, expected in checks:
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}: {label} = {expected!r}" + ("" if ok else f" (got {actual!r})"))
        if not ok:
            all_pass = False

    # Sample verification table
    print(f"\n  {'q':<4} {'visual_type':<24} {'highlight':<10} {'text':<50}")
    print(f"  {'─'*4} {'─'*24} {'─'*10} {'─'*50}")
    for i, q in enumerate(api_qs):
        hl = (q.visual_data or {}).get("highlight", "-")
        print(f"  q{i+1:<3} {str(q.visual_type):<24} {str(hl):<10} {(q.text or '')[:50]}")

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

    # Use temp history file for tests
    import app.services.history_store as hs
    original_path = hs.HISTORY_FILE
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    hs.HISTORY_FILE = __import__("pathlib").Path(tmp_path)

    try:
        from openai import OpenAI
        llm_client = OpenAI(api_key=api_key)

        print("\n" + "=" * 60)
        print("8. LLM PIPELINE TESTS")
        print("=" * 60)

        for q_count in [5, 10]:
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
            print(f"  Parent tip: {meta.get('parent_tip')}")

            actual = Counter(q.get("slot_type") for q in questions)
            expected = SLOT_PLANS.get(q_count, {})
            print(f"\n  Slot distribution:")
            for slot in SLOT_ORDER:
                exp = expected.get(slot, "?")
                act = actual.get(slot, 0)
                match = "OK" if exp == act else "MISMATCH"
                print(f"    {slot}: {exp} -> {act}  {match}")

            print(f"\n  Formats:")
            for slot in SLOT_ORDER:
                slot_qs = [q for q in questions if q.get("slot_type") == slot]
                formats = [q.get("format", "?") for q in slot_qs]
                valid = VALID_FORMATS.get(slot, set())
                bad = [f for f in formats if f not in valid]
                status = "OK" if not bad else f"BAD: {bad}"
                print(f"    {slot}: {formats}  {status}")

            print(f"\n  Sample questions:")
            shown: dict[str, int] = {}
            for q in questions:
                slot = q.get("slot_type", "?")
                shown.setdefault(slot, 0)
                if shown[slot] < 1:
                    text_preview = q.get("question_text", "")[:100]
                    print(f"    [{slot}/{q.get('format')}] {text_preview}")
                    print(f"      Answer: {q.get('answer', '?')}")
                    shown[slot] += 1
            print()
    finally:
        hs.HISTORY_FILE = original_path
        os.unlink(tmp_path)


# ════════════════════════════════════════════════
# Part 3: 30-Worksheet Diversity Test
# ════════════════════════════════════════════════

def test_30_worksheet_diversity():
    """Generate 30 worksheets for same inputs and assert diversity metrics."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n" + "=" * 60)
        print("30-WORKSHEET DIVERSITY - SKIPPED (OPENAI_API_KEY not set)")
        print("=" * 60)
        return

    # Use temp history file
    import app.services.history_store as hs
    original_path = hs.HISTORY_FILE
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    hs.HISTORY_FILE = __import__("pathlib").Path(tmp_path)

    try:
        from openai import OpenAI
        llm_client = OpenAI(api_key=api_key)

        print("\n" + "=" * 60)
        print("9. 30-WORKSHEET DIVERSITY TEST")
        print("=" * 60)

        all_contexts: list[str] = []
        all_thinking_styles: list[str] = []
        all_error_tags: list[str] = []
        all_error_ids: list[str] = []
        all_names: list[str] = []
        forbidden_count = 0

        for ws_idx in range(30):
            print(f"  Generating worksheet {ws_idx + 1}/30...", end=" ", flush=True)
            meta, questions = run_slot_pipeline(
                client=llm_client,
                grade="Class 3",
                subject="Maths",
                topic="3-digit addition with carrying",
                q_count=5,
                difficulty="medium",
                region="India",
            )

            for q in questions:
                text = q.get("question_text", "").lower()
                slot = q.get("slot_type", "")

                if slot == "application":
                    for ctx in CONTEXT_BANK:
                        if ctx["item"] in text:
                            all_contexts.append(ctx["item"])
                            break
                    for name in NAME_BANKS["India"]:
                        if name.lower() in text:
                            all_names.append(name)
                            break

                if slot == "thinking":
                    style_keywords = {
                        "closer_to": ["closer to", "closer"],
                        "threshold_check": ["more than", "less than", "above", "below"],
                        "bounds_range": ["between", "bound", "range"],
                        "round_nearest_10": ["nearest 10", "round to 10"],
                        "round_nearest_100": ["nearest 100", "nearest hundred", "round to 100"],
                        "reasonable_estimate": ["reasonable", "which of", "which estimate"],
                    }
                    for style_name, keywords in style_keywords.items():
                        if any(kw in text for kw in keywords):
                            all_thinking_styles.append(style_name)
                            break

                if slot == "error_detection":
                    for err in _ALL_ERRORS:
                        if str(err["wrong"]) in text and str(err["a"]) in text:
                            all_error_ids.append(err["id"])
                            all_error_tags.append(err["tag"])
                            break

                if _FORBIDDEN_VISUAL_PHRASES.search(q.get("question_text", "")):
                    forbidden_count += 1

            fmts = [q.get("format", "?") for q in questions]
            print(f"formats={fmts}")

        # ── Diversity assertions ──
        print(f"\n{'─' * 50}")
        print("DIVERSITY RESULTS (30 worksheets)")
        print(f"{'─' * 50}")

        unique_ctx = len(set(all_contexts))
        print(f"  Unique contexts: {unique_ctx} (from {len(all_contexts)} application qs)")
        print(f"    Distribution: {dict(Counter(all_contexts).most_common(10))}")
        ctx_pass = unique_ctx >= 10
        print(f"    >= 10: {'PASS' if ctx_pass else 'FAIL'}")

        unique_styles = len(set(all_thinking_styles))
        print(f"  Unique thinking styles: {unique_styles} (from {len(all_thinking_styles)} thinking qs)")
        print(f"    Distribution: {dict(Counter(all_thinking_styles))}")
        style_pass = unique_styles >= 4
        print(f"    >= 4: {'PASS' if style_pass else 'FAIL'}")

        unique_tags = len(set(all_error_tags))
        print(f"  Unique error tags: {unique_tags} (from {len(all_error_tags)} error qs)")
        print(f"    Distribution: {dict(Counter(all_error_tags))}")
        tag_pass = unique_tags >= 4
        print(f"    >= 4: {'PASS' if tag_pass else 'FAIL'}")

        # No error_id more than 2 times
        id_counts = Counter(all_error_ids)
        max_id = max(id_counts.values()) if id_counts else 0
        id_pass = max_id <= 2
        print(f"  Max error_id repetition: {max_id}")
        print(f"    <= 2: {'PASS' if id_pass else 'FAIL'}")

        unique_names = len(set(all_names))
        print(f"  Unique names: {unique_names}")
        name_pass = unique_names >= 4
        print(f"    >= 4: {'PASS' if name_pass else 'FAIL'}")

        print(f"  Forbidden visual phrases: {forbidden_count}")
        forbidden_pass = forbidden_count == 0
        print(f"    == 0: {'PASS' if forbidden_pass else 'FAIL'}")

        overall = ctx_pass and style_pass and tag_pass and id_pass and name_pass and forbidden_pass
        print(f"\n  30-WORKSHEET DIVERSITY OVERALL: {'PASS' if overall else 'FAIL'}")

    finally:
        hs.HISTORY_FILE = original_path
        os.unlink(tmp_path)


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

if __name__ == "__main__":
    print("PracticeCraft Slot Engine v6.0 - Regression Tests\n")

    p1 = test_slot_plans()
    p2 = test_difficulty_mapping()
    p3 = test_error_computation()
    p4 = test_validators()
    p5 = test_variation_banks()
    p6 = test_history_store()
    p7 = test_seeded_diversity_deterministic()
    p8 = test_visual_hydration()
    p9 = test_endpoint_visual_propagation()
    p10 = test_visuals_only_mode()

    print("\n" + "=" * 60)
    print("DETERMINISTIC SUMMARY")
    print("=" * 60)
    print(f"  Slot plans:            {'PASS' if p1 else 'FAIL'}")
    print(f"  Difficulty map:        {'PASS' if p2 else 'FAIL'}")
    print(f"  Error computation:     {'PASS' if p3 else 'FAIL'}")
    print(f"  Validators:            {'PASS' if p4 else 'FAIL'}")
    print(f"  Variation banks:       {'PASS' if p5 else 'FAIL'}")
    print(f"  History store:         {'PASS' if p6 else 'FAIL'}")
    print(f"  Seeded diversity:      {'PASS' if p7 else 'FAIL'}")
    print(f"  Visual hydration:      {'PASS' if p8 else 'FAIL'}")
    print(f"  Endpoint propagation:  {'PASS' if p9 else 'FAIL'}")
    print(f"  Visuals-only mode:     {'PASS' if p10 else 'FAIL'}")

    test_llm_pipeline()
    test_30_worksheet_diversity()

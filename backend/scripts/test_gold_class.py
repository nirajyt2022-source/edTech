#!/usr/bin/env python3
"""
Gold-class worksheet quality test — deterministic, no LLM, no external APIs.

Creates 6 test payloads with synthetic questions matching each plan,
runs them through the full deterministic pipeline (hydration, carry
enforcement, error enrichment), and prints clean quality summaries.

Usage:
  cd backend
  python scripts/test_gold_class.py
"""

import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    build_worksheet_plan,
    hydrate_visuals,
    enforce_visuals_only,
    enrich_error_spots,
    has_carry,
    has_borrow,
    make_carry_pair,
    CARRY_PAIRS,
    _ALL_ERRORS,
    CONTEXT_BANK,
    NAME_BANKS,
    THINKING_STYLE_BANK,
    TOPIC_PROFILES,
    get_topic_profile,
    violates_topic_purity,
    normalize_q_text,
)
from app.skills.registry import SKILL_REGISTRY


# ════════════════════════════════════════════════════════════
# Synthetic question generator (no LLM)
# ════════════════════════════════════════════════════════════

def _make_synthetic_questions(
    plan: list[dict],
    rng: random.Random,
    operation_bias: str = "addition",
) -> list[dict]:
    """Create synthetic questions matching plan directives.

    Uses deterministic numbers from make_carry_pair / CARRY_PAIRS.
    Text is crafted to trigger the correct hydration rules.
    """
    questions = []
    error_idx = 0
    ctx_idx = 0
    style_idx = 0

    for i, directive in enumerate(plan):
        slot_type = directive["slot_type"]
        fmt = directive.get("format_hint", "column_setup")
        ops = directive.get("allow_operations", ["addition", "subtraction"])
        carry_req = directive.get("carry_required", False)

        # Pick operation
        if len(ops) == 1:
            op = ops[0]
        else:
            op = operation_bias if operation_bias in ops else rng.choice(ops)

        # Generate numbers
        if carry_req:
            a, b = make_carry_pair(rng, op)
        elif op == "subtraction":
            a = rng.randint(200, 999)
            b = rng.randint(100, a - 1)
        else:
            a = rng.randint(100, 499)
            b = rng.randint(100, 499)

        sym = "+" if op == "addition" else "-"
        ans = a + b if op == "addition" else a - b

        q: dict = {
            "id": i + 1,
            "slot_type": slot_type,
            "skill_tag": directive.get("skill_tag", slot_type),
            "difficulty": "medium",
            "pictorial_elements": [],
        }

        if fmt == "column_setup":
            q["format"] = "column_setup"
            q["question_text"] = f"Write {a} {sym} {b} in column form."
            q["answer"] = f"{a} {sym} {b}"

        elif fmt == "word_problem":
            ctx = CONTEXT_BANK[ctx_idx % len(CONTEXT_BANK)]
            name = NAME_BANKS["India"][ctx_idx % len(NAME_BANKS["India"])]
            ctx_idx += 1
            q["format"] = "word_problem"
            if op == "addition":
                q["question_text"] = (
                    f"{name} has {a} {ctx['item']}. "
                    f"He got {b} more {ctx['item']}. "
                    f"How many {ctx['item']} does he have in total?"
                )
            else:
                q["question_text"] = (
                    f"{name} had {a} {ctx['item']}. "
                    f"He gave away {b} {ctx['item']}. "
                    f"How many {ctx['item']} are left?"
                )
            q["answer"] = str(ans)

        elif fmt == "missing_number":
            q["format"] = "missing_number"
            q["question_text"] = f"___ {sym} {b} = {ans}"
            q["answer"] = str(a)

        elif fmt == "error_spot":
            err = _ALL_ERRORS[error_idx % len(_ALL_ERRORS)]
            error_idx += 1
            q["format"] = "error_spot"
            q["question_text"] = (
                f"A student added {err['a']} + {err['b']} and got {err['wrong']}. "
                f"What mistake did the student make? The correct answer is {err['correct']}."
            )
            q["answer"] = str(err["correct"])
            q["student_wrong_answer"] = err["wrong"]

        elif fmt == "thinking":
            style = THINKING_STYLE_BANK[style_idx % len(THINKING_STYLE_BANK)]
            style_idx += 1
            q["format"] = "thinking"
            if style["style"] == "closer_to":
                lo = (ans // 100) * 100
                hi = lo + 100
                q["question_text"] = (
                    f"Without calculating, is {a} {sym} {b} closer to {lo} or {hi}? "
                    f"Explain your reasoning."
                )
                q["answer"] = f"closer to {lo if ans - lo < hi - ans else hi}"
            else:
                q["question_text"] = (
                    f"Estimate {a} {sym} {b} to the nearest hundred. "
                    f"Explain your reasoning."
                )
                q["answer"] = str(round(ans, -2))

        else:
            # Fallback: treat as column_setup
            q["format"] = fmt
            q["question_text"] = f"Write {a} {sym} {b} in column form."
            q["answer"] = f"{a} {sym} {b}"

        questions.append(q)

    return questions


# ════════════════════════════════════════════════════════════
# Analysis
# ════════════════════════════════════════════════════════════

def _analyze(questions: list[dict], label: str) -> bool:
    """Print quality analysis for a set of processed questions. Returns True if clean."""
    total = len(questions)

    # Count by skill_tag (format)
    fmt_counts = Counter(q.get("format", "unknown") for q in questions)

    # Visual coverage
    visual_count = sum(
        1 for q in questions
        if q.get("representation") == "PICTORIAL_MODEL"
    )
    visual_ratio = visual_count / total if total else 0

    # Carry check on BASE_TEN_REGROUPING visuals
    carry_total = 0
    carry_actual = 0
    for q in questions:
        spec = q.get("visual_spec")
        if not spec or spec.get("model_id") != "BASE_TEN_REGROUPING":
            continue
        nums = spec.get("numbers", [])
        if len(nums) < 2:
            continue
        carry_total += 1
        a, b = nums[0], nums[1]
        op = spec.get("operation", "addition")
        if op == "addition" and has_carry(a, b):
            carry_actual += 1
        elif op == "subtraction" and has_borrow(a, b):
            carry_actual += 1

    # Error spot enrichment
    error_total = sum(1 for q in questions if q.get("slot_type") == "error_detection")
    error_with_sa = sum(
        1 for q in questions
        if q.get("slot_type") == "error_detection"
        and (q.get("visual_spec") or {}).get("student_answer") is not None
    )

    # Skill tag completeness
    empty_skill_tags = sum(1 for q in questions if not q.get("skill_tag"))

    # Thinking estimation phrase check
    thinking_total = sum(1 for q in questions if q.get("slot_type") == "thinking")
    thinking_explicit = sum(
        1 for q in questions
        if q.get("slot_type") == "thinking"
        and re.search(
            r"nearest hundred|closer to|estimat",
            q.get("question_text", ""),
            re.IGNORECASE,
        )
    )

    # Print
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Total questions:       {total}")
    print(f"  Skill tag counts:")
    for fmt in sorted(fmt_counts):
        print(f"    {fmt:<20} {fmt_counts[fmt]}")
    print(f"  Visual type != null:   {visual_count}/{total}")
    print(f"  Visual ratio:          {visual_ratio:.0%}")
    carry_pct = f" ({carry_actual/carry_total:.0%})" if carry_total else ""
    print(f"  Carry/borrow verified: {carry_actual}/{carry_total}{carry_pct}")
    err_pct = f" ({error_with_sa/error_total:.0%})" if error_total else ""
    print(f"  Error spot w/ answer:  {error_with_sa}/{error_total}{err_pct}")
    print(f"  Empty skill_tags:      {empty_skill_tags}/{total}")
    t_pct = f" ({thinking_explicit/thinking_total:.0%})" if thinking_total else ""
    print(f"  Thinking w/ rounding:  {thinking_explicit}/{thinking_total}{t_pct}")

    # Verdict
    issues = []
    if total == 0:
        issues.append("no questions")
    if carry_total > 0 and carry_actual < carry_total:
        issues.append(f"carry gap {carry_actual}/{carry_total}")
    if error_total > 0 and error_with_sa < error_total:
        issues.append(f"missing student_answer {error_with_sa}/{error_total}")
    if empty_skill_tags > 0:
        issues.append(f"empty skill_tag on {empty_skill_tags} questions")
    if thinking_total > 0 and thinking_explicit < thinking_total:
        issues.append(f"thinking without rounding {thinking_explicit}/{thinking_total}")

    verdict = "PASS" if not issues else f"WARN: {', '.join(issues)}"
    print(f"  Verdict:               {verdict}")
    return len(issues) == 0


# ════════════════════════════════════════════════════════════
# Payload runner
# ════════════════════════════════════════════════════════════

def run_payload(
    label: str,
    q_count: int,
    mix_recipe: list[dict] | None = None,
    constraints: dict | None = None,
    visuals_only: bool = False,
    min_visual_ratio: float = 0.8,
    operation_bias: str = "addition",
    seed: int = 42,
) -> bool:
    """Build plan -> synthetic questions -> pipeline -> analyze."""
    rng = random.Random(seed)

    constraints = constraints or {}
    plan = build_worksheet_plan(q_count, mix_recipe=mix_recipe, constraints=constraints)
    questions = _make_synthetic_questions(plan, rng, operation_bias=operation_bias)

    # Run deterministic pipeline
    hydrate_visuals(questions, visuals_only=visuals_only)
    if visuals_only:
        enforce_visuals_only(questions, min_ratio=min_visual_ratio)
    if constraints.get("carry_required"):
        rng_carry = random.Random(seed + 1)
        for q in questions:
            contract = SKILL_REGISTRY.get(q.get("skill_tag"))
            if contract:
                if contract.validate(q):
                    contract.repair(q, rng_carry)
    enrich_error_spots(questions)

    return _analyze(questions, label)


# ════════════════════════════════════════════════════════════
# Fractions topic purity test (deterministic, no LLM)
# ════════════════════════════════════════════════════════════

def test_fractions_topic_purity() -> bool:
    """Test Fractions topic profile, plan building, and purity validation."""
    issues: list[str] = []
    topic = "Fractions (halves, quarters)"

    # 1. Profile exists
    profile = get_topic_profile(topic)
    if not profile:
        print("\n  FAIL: no profile for 'Fractions (halves, quarters)'")
        return False

    # 2. Plan builds with fractions recipe (10Q)
    plan = build_worksheet_plan(10, topic=topic)
    if len(plan) != 10:
        issues.append(f"plan length {len(plan)}, expected 10")

    # 3. All directives have topic-correct skill_tags
    allowed_tags = set(profile["allowed_skill_tags"])
    for d in plan:
        if not d.get("skill_tag"):
            issues.append("empty skill_tag in directive")
        elif d["skill_tag"] not in allowed_tags:
            issues.append(f"non-fractions skill_tag: {d['skill_tag']}")
        if d.get("carry_required"):
            issues.append("carry_required in fractions directive")
        if d.get("allow_operations"):
            issues.append(f"operations not empty: {d.get('allow_operations')}")

    # 4. Purity catches off-topic questions
    bad_qs = [
        {"question_text": "Write 345 + 278 in column form.", "skill_tag": "column_setup"},
        {"question_text": "Aarav has 100 rupees at the shop.", "skill_tag": "word_problem"},
        {"question_text": "Subtract 456 from 789.", "skill_tag": "word_problem"},
        {"question_text": "Add 123 and 456.", "skill_tag": "column_setup"},
    ]
    bad_caught = 0
    for bq in bad_qs:
        reasons = violates_topic_purity(bq, profile)
        if reasons:
            bad_caught += 1
        else:
            issues.append(f"off-topic not caught: {bq['question_text'][:30]}")

    # 5. Clean fractions questions pass
    good_qs = [
        {"question_text": "What is half of 12?", "skill_tag": "fraction_of_number_half"},
        {"question_text": "Shade one quarter of this circle.", "skill_tag": "fraction_of_shape_shaded"},
        {"question_text": "Priya ate 1/4 of a pizza. How much is left?",
         "skill_tag": "fraction_word_problem_half_quarter"},
        {"question_text": "Which shape shows 1/2 shaded?", "skill_tag": "fraction_identify_half"},
    ]
    good_passed = 0
    for gq in good_qs:
        reasons = violates_topic_purity(gq, profile)
        if not reasons:
            good_passed += 1
        else:
            issues.append(f"clean fraction flagged: {gq['skill_tag']} -> {reasons}")

    # 6. Duplicate detection via normalize
    n1 = normalize_q_text({"question_text": "What is half of 12?"})
    n2 = normalize_q_text({"question_text": "What is  half  of  12?"})
    if n1 != n2:
        issues.append("duplicate normalization failed")

    # 7. No base_ten_regrouping visuals in fractions plan
    # (Fractions questions shouldn't trigger hydration to BASE_TEN_REGROUPING)
    frac_qs = [
        {"id": i + 1, "slot_type": d["slot_type"], "skill_tag": d["skill_tag"],
         "difficulty": "medium", "pictorial_elements": [],
         "question_text": f"What is half of {(i + 1) * 4}?",
         "format": "place_value", "answer": str((i + 1) * 2)}
        for i, d in enumerate(plan)
    ]
    hydrate_visuals(frac_qs)
    btr_count = sum(
        1 for q in frac_qs
        if (q.get("visual_spec") or {}).get("model_id") == "BASE_TEN_REGROUPING"
    )
    if btr_count > 0:
        issues.append(f"{btr_count} fractions questions got BASE_TEN_REGROUPING visual")

    # 8. Heuristic: plan skill_tags mention half/quarter
    frac_tagged = [d for d in plan if "half" in d["skill_tag"] or "quarter" in d["skill_tag"]]

    # Print
    label = "7. FRACTIONS TOPIC PURITY"
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Plan directives:       {len(plan)}")
    print(f"  Fractions skill_tags:  {len(frac_tagged)}/{len(plan)}")
    print(f"  Off-topic caught:      {bad_caught}/{len(bad_qs)}")
    print(f"  Clean passed:          {good_passed}/{len(good_qs)}")
    print(f"  BTR visuals in frac:   {btr_count}")
    print(f"  Duplicate norm works:  {'yes' if n1 == n2 else 'no'}")

    verdict = "PASS" if not issues else f"WARN: {', '.join(issues)}"
    print(f"  Verdict:               {verdict}")
    return len(issues) == 0


# ════════════════════════════════════════════════════════════
# 7 Test Payloads
# ════════════════════════════════════════════════════════════

def main():
    print("PracticeCraft Gold-Class Worksheet Quality Test")
    print("=" * 60)
    print("Deterministic | No LLM | No external APIs\n")

    results = []

    # 1. Carry guaranteed addition (10Q)
    results.append(run_payload(
        "1. CARRY GUARANTEED ADDITION (10Q)",
        q_count=10,
        constraints={"carry_required": True, "allow_operations": ["addition"]},
        operation_bias="addition",
        seed=42,
    ))

    # 2. Borrowing subtraction (10Q)
    results.append(run_payload(
        "2. BORROWING SUBTRACTION (10Q)",
        q_count=10,
        constraints={"carry_required": True, "allow_operations": ["subtraction"]},
        operation_bias="subtraction",
        seed=99,
    ))

    # 3. Gold mix (20Q)
    results.append(run_payload(
        "3. GOLD MIX (20Q)",
        q_count=20,
        constraints={"carry_required": True},
        operation_bias="addition",
        seed=77,
    ))

    # 4. Visual stress (15Q)
    results.append(run_payload(
        "4. VISUAL STRESS (15Q)",
        q_count=15,
        visuals_only=True,
        min_visual_ratio=0.8,
        constraints={"carry_required": True},
        seed=55,
    ))

    # 5. Parent trust (10Q)
    results.append(run_payload(
        "5. PARENT TRUST (10Q)",
        q_count=10,
        constraints={"carry_required": True},
        seed=123,
    ))

    # 6. Error spot only (5Q)
    results.append(run_payload(
        "6. ERROR SPOT ONLY (5Q)",
        q_count=5,
        mix_recipe=[
            {"skill_tag": "error_spot", "count": 5, "require_student_answer": True},
        ],
        constraints={"carry_required": True},
        seed=200,
    ))

    # 7. Fractions topic purity
    results.append(test_fractions_topic_purity())

    # Final summary
    labels = [
        "Carry addition",
        "Borrowing subtraction",
        "Gold mix",
        "Visual stress",
        "Parent trust",
        "Error spot only",
        "Fractions purity",
    ]

    print(f"\n{'=' * 60}")
    print("  OVERALL SUMMARY")
    print(f"{'=' * 60}")
    for i, (lbl, passed) in enumerate(zip(labels, results)):
        print(f"  {i + 1}. {lbl:<25} {'PASS' if passed else 'WARN'}")

    total_pass = sum(results)
    print(f"\n  {total_pass}/{len(results)} payloads clean")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Deterministic test for Class 4 Maths topic profiles.

Validates 10 topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_class4_maths.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    TOPIC_PROFILES,
    _TOPIC_ALIASES,
    _TOPIC_CONSTRAINTS,
    _SKILL_TAG_TO_SLOT,
    LEARNING_OBJECTIVES,
    TOPIC_CONTEXT_BANK,
    SLOT_ORDER,
    get_topic_profile,
    build_worksheet_plan,
    get_valid_formats,
)

# ── Counters ──
PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  \u2713 {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  \u2717 {msg}")


# ── The 10 Class 4 Maths topics (canonical names) ──
CLASS4_TOPICS = [
    "Large numbers (up to 1,00,000)",
    "Addition and subtraction (5-digit)",
    "Multiplication (3-digit \u00d7 2-digit)",
    "Division (long division)",
    "Fractions (equivalent, comparison)",
    "Decimals (tenths, hundredths)",
    "Geometry (angles, lines)",
    "Perimeter and area",
    "Time (minutes, 24-hour clock)",
    "Money (bills, profit/loss)",
]

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Large numbers (up to 1,00,000)": [
        "class 4 large numbers", "c4 large numbers", "large numbers",
        "numbers up to 100000",
        "Large numbers (up to 1,00,000)",
    ],
    "Addition and subtraction (5-digit)": [
        "class 4 addition subtraction", "class 4 add/sub", "c4 add/sub",
        "5-digit addition",
        "Addition and subtraction (5-digit)",
    ],
    "Multiplication (3-digit \u00d7 2-digit)": [
        "class 4 multiplication", "c4 multiplication", "multi-digit multiplication",
        "Multiplication (3-digit \u00d7 2-digit)",
    ],
    "Division (long division)": [
        "class 4 division", "c4 division", "long division",
        "Division (long division)",
    ],
    "Fractions (equivalent, comparison)": [
        "class 4 fractions", "c4 fractions", "equivalent fractions",
        "Fractions (equivalent, comparison)",
    ],
    "Decimals (tenths, hundredths)": [
        "class 4 decimals", "c4 decimals", "decimals",
        "Decimals (tenths, hundredths)",
    ],
    "Geometry (angles, lines)": [
        "class 4 geometry", "c4 geometry", "angles and lines",
        "Geometry (angles, lines)",
    ],
    "Perimeter and area": [
        "class 4 perimeter", "c4 perimeter", "perimeter and area",
        "perimeter", "area",
        "Perimeter and area",
    ],
    "Time (minutes, 24-hour clock)": [
        "class 4 time", "c4 time", "24-hour clock",
        "Time (minutes, 24-hour clock)",
    ],
    "Money (bills, profit/loss)": [
        "class 4 money", "c4 money", "profit and loss", "profit/loss",
        "Money (bills, profit/loss)",
    ],
}

# ── Arithmetic canonical names ──
ARITHMETIC_CANONICALS = {
    "Addition and subtraction (5-digit)",
    "Multiplication (3-digit \u00d7 2-digit)",
    "Division (long division)",
}

# ── Non-arithmetic topics that should disallow arithmetic contamination ──
NON_ARITHMETIC_TOPICS = {
    "Large numbers (up to 1,00,000)",
    "Fractions (equivalent, comparison)",
    "Decimals (tenths, hundredths)",
    "Geometry (angles, lines)",
    "Perimeter and area",
    "Time (minutes, 24-hour clock)",
    "Money (bills, profit/loss)",
}


print("=" * 60)
print("=== Class 4 Maths \u2014 Deterministic Checks ===")
print("=" * 60)

for topic in CLASS4_TOPICS:
    print(f"\n{topic}:")

    # ── 1. Topic exists in TOPIC_PROFILES ──
    if topic in TOPIC_PROFILES:
        ok("In TOPIC_PROFILES")
        profile = TOPIC_PROFILES[topic]
    else:
        fail(f"NOT in TOPIC_PROFILES")
        # Skip remaining checks if profile missing
        for _ in range(8):
            fail("(skipped — profile missing)")
        continue

    # ── 2. Has all required keys ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        ok("Has required keys")
    else:
        fail(f"Missing keys: {missing_keys}")

    # ── 3. default_recipe sums to 10 ──
    recipe_total = sum(item["count"] for item in profile["default_recipe"])
    if recipe_total == 10:
        ok("Recipe sums to 10")
    else:
        fail(f"Recipe sums to {recipe_total}, expected 10")

    # ── 4. All skill tags in recipe are in allowed_skill_tags ──
    allowed = set(profile["allowed_skill_tags"])
    recipe_tags = {item["skill_tag"] for item in profile["default_recipe"]}
    orphans = recipe_tags - allowed
    if not orphans:
        ok("Skill tags consistent")
    else:
        fail(f"Recipe tags not in allowed_skill_tags: {orphans}")

    # ── 5. Aliases resolve via get_topic_profile() ──
    aliases = TOPIC_ALIASES.get(topic, [])
    all_resolved = True
    for alias in aliases:
        p = get_topic_profile(alias)
        if p is None:
            fail(f"Alias '{alias}' does not resolve")
            all_resolved = False
            break
        # Verify it resolves to the right profile
        resolved_canon = None
        for k, v in TOPIC_PROFILES.items():
            if v is p:
                resolved_canon = k
                break
        if resolved_canon != topic:
            fail(f"Alias '{alias}' resolves to '{resolved_canon}', expected '{topic}'")
            all_resolved = False
            break
    if all_resolved:
        ok(f"Aliases resolve ({len(aliases)} tested)")

    # ── 6. Has LEARNING_OBJECTIVES with 3 entries ──
    if topic in LEARNING_OBJECTIVES:
        obj_count = len(LEARNING_OBJECTIVES[topic])
        if obj_count == 3:
            ok(f"Has learning objectives (3)")
        else:
            fail(f"Has learning objectives but count={obj_count}, expected 3")
    else:
        fail(f"Missing entry in LEARNING_OBJECTIVES")

    # ── 7. Has TOPIC_CONTEXT_BANK with >= 5 contexts ──
    if topic in TOPIC_CONTEXT_BANK:
        ctx_count = len(TOPIC_CONTEXT_BANK[topic])
        if ctx_count >= 5:
            ok(f"Has context bank ({ctx_count})")
        else:
            fail(f"Has context bank but only {ctx_count} contexts, expected >= 5")
    else:
        fail(f"Missing entry in TOPIC_CONTEXT_BANK")

    # ── 8. Has entry in _TOPIC_CONSTRAINTS ──
    if topic in _TOPIC_CONSTRAINTS:
        ok("Has constraints")
    else:
        if topic in ARITHMETIC_CANONICALS:
            # Some arithmetic topics may lack explicit constraints
            fail(f"Missing entry in _TOPIC_CONSTRAINTS (arithmetic topic)")
        else:
            fail(f"Missing entry in _TOPIC_CONSTRAINTS")

    # ── 9. Slot plans for 5/10/15/20 produce valid slot types ──
    plan_ok = True
    allowed_slots = set(profile.get("allowed_slot_types", SLOT_ORDER))
    for q_count in [5, 10, 15, 20]:
        try:
            plan = build_worksheet_plan(q_count, topic=topic)
            if len(plan) != q_count:
                fail(f"Slot plan({q_count}) returned {len(plan)} slots, expected {q_count}")
                plan_ok = False
                break
            slot_types = {d["slot_type"] for d in plan}
            invalid = slot_types - set(SLOT_ORDER)
            if invalid:
                fail(f"Slot plan({q_count}) has invalid slot types: {invalid}")
                plan_ok = False
                break
        except Exception as e:
            fail(f"Slot plan({q_count}) raised: {e}")
            plan_ok = False
            break
    if plan_ok:
        ok("Slot plans valid (5/10/15/20)")

# ── Grade-specific constraint checks ──
print(f"\n{'=' * 60}")
print("Grade-specific keyword constraints:")
print("=" * 60)

# Multiplication should disallow add/subtract contamination
CROSS_CONTAM_MULT = {"carry", "borrow", "add", "subtract", "fraction", "decimal"}
# Division should disallow add/subtract contamination
CROSS_CONTAM_DIV = {"carry", "borrow", "add", "subtract", "fraction", "decimal"}

for topic in CLASS4_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]
    disallowed = set(profile.get("disallowed_keywords", []))
    disallowed_lower = {kw.lower() for kw in disallowed}

    if topic == "Multiplication (3-digit \u00d7 2-digit)":
        missing = CROSS_CONTAM_MULT - disallowed_lower
        if not missing:
            ok(f"{topic}: disallows carry/borrow/add/subtract/fraction/decimal")
        else:
            fail(f"{topic}: missing disallowed keywords: {missing}")

    if topic == "Division (long division)":
        missing = CROSS_CONTAM_DIV - disallowed_lower
        if not missing:
            ok(f"{topic}: disallows carry/borrow/add/subtract/fraction/decimal")
        else:
            fail(f"{topic}: missing disallowed keywords: {missing}")

    # Non-arithmetic topics should disallow some arithmetic keywords
    if topic in NON_ARITHMETIC_TOPICS:
        arith_keywords = {"carry", "borrow"}
        present = arith_keywords & disallowed_lower
        if present:
            ok(f"{topic}: disallows arithmetic keywords ({present})")
        else:
            fail(f"{topic}: no arithmetic keywords in disallowed_keywords")

    # Fractions should disallow decimal
    if topic == "Fractions (equivalent, comparison)":
        if "decimal" in disallowed_lower:
            ok(f"{topic}: disallows 'decimal'")
        else:
            fail(f"{topic}: 'decimal' not in disallowed_keywords")

    # Geometry should disallow fraction/decimal
    if topic == "Geometry (angles, lines)":
        geo_disallowed = {"fraction", "decimal"}
        missing = geo_disallowed - disallowed_lower
        if not missing:
            ok(f"{topic}: disallows fraction/decimal")
        else:
            fail(f"{topic}: missing disallowed keywords: {missing}")

# ── Summary ──
TOTAL = PASS + FAIL
print(f"\n{'=' * 60}")
print(f"=== SUMMARY: {PASS}/{TOTAL} checks passed ===")
print("=" * 60)

if FAIL > 0:
    print(f"\n{FAIL} CHECK(S) FAILED -- review above for details")
    sys.exit(1)
else:
    print("\nALL CHECKS PASSED")
    sys.exit(0)

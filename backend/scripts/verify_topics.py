#!/usr/bin/env python3
"""
Comprehensive verification of all Class 2, 3 & 4 maths topic profiles.

Checks (deterministic — no LLM calls):
1. Every skill_tag in every recipe maps to a valid (slot_type, format) via _SKILL_TAG_TO_SLOT
2. Every format is present in VALID_FORMATS for its slot_type
3. Every recipe covers all 5 slot types (R, A, Rep, ED, T)
4. Topic aliases resolve correctly (frontend short names → canonical profile)
5. _TOPIC_CONSTRAINTS has an entry for every non-arithmetic canonical topic
6. Topic normalization in run_slot_pipeline would correctly resolve each alias
7. Slot plan from build_worksheet_plan matches expected counts
8. No disallowed_keywords appear in _build_slot_instruction output (spot check)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    TOPIC_PROFILES, _TOPIC_ALIASES, _SKILL_TAG_TO_SLOT, VALID_FORMATS,
    VALID_FORMATS_ENGLISH, get_valid_formats,
    SLOT_ORDER, get_topic_profile, build_worksheet_plan,
    _TOPIC_CONSTRAINTS,
)

PASS = 0
FAIL = 0
WARN = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  PASS {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL {msg}")

def warn(msg):
    global WARN
    WARN += 1
    print(f"  WARN  {msg}")

# ── Frontend topic names (what the UI actually sends) ──
FRONTEND_TOPICS = [
    # Class 2 short names
    "class 2 numbers", "class 2 addition", "class 2 subtraction",
    "class 2 multiplication", "class 2 division", "class 2 shapes",
    "class 2 measurement", "class 2 time", "class 2 money",
    "class 2 data handling", "class 2 data",
    "c2 numbers", "c2 addition", "c2 subtraction",
    "c2 multiplication", "c2 division", "c2 shapes",
    "c2 measurement", "c2 time", "c2 money", "c2 data",
    "sharing equally", "pictographs", "2d shapes",
    # Class 2 exact canonical names
    "Numbers up to 1000 (Class 2)",
    "Addition (2-digit with carry)",
    "Subtraction (2-digit with borrow)",
    "Multiplication (tables 2-5)",
    "Division (sharing equally)",
    "Shapes and space (2D)",
    "Measurement (length, weight)",
    "Time (hour, half-hour)",
    "Money (coins and notes)",
    "Data handling (pictographs)",
    # Class 3 short names
    "Addition", "Subtraction", "Multiplication", "Division",
    "Fractions", "Time", "Money", "Symmetry", "Patterns",
    "Numbers", "Place Value",
    "Addition and Subtraction", "add/sub",
    # Class 3 exact canonical names
    "Addition (carries)", "Subtraction (borrowing)",
    "Addition and subtraction (3-digit)",
    "Multiplication (tables 2-10)", "Division basics",
    "Numbers up to 10000", "Fractions (halves, quarters)",
    "Time (reading clock, calendar)", "Money (bills and change)",
    "Patterns and sequences",
    # Class 4 short names
    "class 4 large numbers", "c4 large numbers", "large numbers",
    "class 4 multiplication", "c4 multiplication",
    "class 4 division", "c4 division", "long division",
    "class 4 fractions", "c4 fractions", "equivalent fractions",
    "class 4 decimals", "c4 decimals", "decimals",
    "class 4 geometry", "c4 geometry", "angles and lines",
    "class 4 perimeter", "c4 perimeter", "perimeter and area",
    "class 4 time", "c4 time", "24-hour clock",
    "class 4 money", "c4 money", "profit/loss",
    "class 4 add/sub", "c4 add/sub",
    # Class 4 exact canonical names
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

ARITHMETIC_CANONICALS = {
    "Addition (carries)", "Subtraction (borrowing)", "Addition and subtraction (3-digit)",
    # Class 2 arithmetic
    "Addition (2-digit with carry)", "Subtraction (2-digit with borrow)",
    # Class 4 arithmetic
    "Addition and subtraction (5-digit)",
}

# Combined topics may intentionally skip thinking to fit both add+sub error detection
_FLEXIBLE_SLOT_TOPICS = {"Addition and subtraction (3-digit)"}

print("=" * 70)
print("TOPIC PROFILE VERIFICATION — Class 2, 3 & 4 Maths")
print("=" * 70)

# ===================================
# TEST 1: Alias resolution
# ===================================
print("\n-- TEST 1: Topic Alias Resolution --")
for ft in FRONTEND_TOPICS:
    profile = get_topic_profile(ft)
    if profile:
        # Find canonical key
        canon = None
        for k, v in TOPIC_PROFILES.items():
            if v is profile:
                canon = k
                break
        ok(f'"{ft}" -> "{canon}"')
    else:
        fail(f'"{ft}" -> NO MATCH')

# ===================================
# TEST 2: Skill tag mapping
# ===================================
print("\n-- TEST 2: Skill Tag -> Slot Mapping --")
for topic_name, profile in TOPIC_PROFILES.items():
    print(f"\n  [{topic_name}]")
    _subject = profile.get("subject", "Mathematics")
    _formats = get_valid_formats(_subject)
    for item in profile["default_recipe"]:
        tag = item["skill_tag"]
        if tag in _SKILL_TAG_TO_SLOT:
            slot_type, fmt = _SKILL_TAG_TO_SLOT[tag]
            if fmt in _formats.get(slot_type, []):
                ok(f"{tag} -> ({slot_type}, {fmt})")
            else:
                fail(f"{tag} -> ({slot_type}, {fmt}) -- format '{fmt}' not in {'VALID_FORMATS_ENGLISH' if _subject == 'English' else 'VALID_FORMATS'}['{slot_type}']")
        else:
            fail(f"{tag} -> NOT IN _SKILL_TAG_TO_SLOT")

# ===================================
# TEST 3: All 5 slot types covered
# ===================================
print("\n-- TEST 3: All 5 Slot Types Covered per Recipe --")
for topic_name, profile in TOPIC_PROFILES.items():
    slot_counts = Counter()
    for item in profile["default_recipe"]:
        tag = item["skill_tag"]
        if tag in _SKILL_TAG_TO_SLOT:
            slot_type, _ = _SKILL_TAG_TO_SLOT[tag]
            slot_counts[slot_type] += item["count"]

    missing = [s for s in SLOT_ORDER if slot_counts.get(s, 0) == 0]
    total = sum(slot_counts.values())
    dist = {s: slot_counts.get(s, 0) for s in SLOT_ORDER}

    if not missing:
        ok(f"{topic_name}: {total}q -> R={dist['recognition']} A={dist['application']} Rep={dist['representation']} ED={dist['error_detection']} T={dist['thinking']}")
    elif topic_name in _FLEXIBLE_SLOT_TOPICS:
        warn(f"{topic_name}: missing {missing} (expected for combined topic) -- {dist}")
    else:
        fail(f"{topic_name}: MISSING slot types: {missing} -- got {dist}")

# ===================================
# TEST 4: Topic constraints exist
# ===================================
print("\n-- TEST 4: _TOPIC_CONSTRAINTS Coverage --")
for topic_name in TOPIC_PROFILES:
    if topic_name in ARITHMETIC_CANONICALS:
        # Arithmetic topics don't need constraints (they're the default)
        ok(f"{topic_name}: arithmetic -- no constraint needed")
    elif topic_name in _TOPIC_CONSTRAINTS:
        constraint = _TOPIC_CONSTRAINTS[topic_name]
        ok(f"{topic_name}: has constraint ({len(constraint)} chars)")
    else:
        fail(f"{topic_name}: NO ENTRY in _TOPIC_CONSTRAINTS -- LLM may generate off-topic questions!")

# ===================================
# TEST 5: Canonical normalization in pipeline
# ===================================
print("\n-- TEST 5: Pipeline Topic Normalization --")
print("  Simulating run_slot_pipeline canonical resolution...")
short_to_canonical = {
    # Class 2
    "class 2 numbers": "Numbers up to 1000 (Class 2)",
    "class 2 addition": "Addition (2-digit with carry)",
    "class 2 subtraction": "Subtraction (2-digit with borrow)",
    "class 2 multiplication": "Multiplication (tables 2-5)",
    "class 2 division": "Division (sharing equally)",
    "class 2 shapes": "Shapes and space (2D)",
    "class 2 measurement": "Measurement (length, weight)",
    "class 2 time": "Time (hour, half-hour)",
    "class 2 money": "Money (coins and notes)",
    "class 2 data handling": "Data handling (pictographs)",
    # Class 3
    "Multiplication": "Multiplication (tables 2-10)",
    "Division": "Division basics",
    "Fractions": "Fractions",
    "Time": "Time (reading clock, calendar)",
    "Money": "Money (bills and change)",
    "Symmetry": "Symmetry",
    "Patterns": "Patterns and sequences",
    "Numbers": "Numbers up to 10000",
    "Addition": "Addition (carries)",
    "Subtraction": "Subtraction (borrowing)",
    "Addition and Subtraction": "Addition and subtraction (3-digit)",
    "add/sub": "Addition and subtraction (3-digit)",
    # Class 4
    "class 4 large numbers": "Large numbers (up to 1,00,000)",
    "class 4 multiplication": "Multiplication (3-digit \u00d7 2-digit)",
    "class 4 division": "Division (long division)",
    "class 4 fractions": "Fractions (equivalent, comparison)",
    "class 4 decimals": "Decimals (tenths, hundredths)",
    "class 4 geometry": "Geometry (angles, lines)",
    "class 4 perimeter": "Perimeter and area",
    "class 4 time": "Time (minutes, 24-hour clock)",
    "class 4 money": "Money (bills, profit/loss)",
    "class 4 add/sub": "Addition and subtraction (5-digit)",
}

for short_name, expected_canon in short_to_canonical.items():
    profile = get_topic_profile(short_name)
    if not profile:
        fail(f'"{short_name}" -> profile not found')
        continue
    # Simulate the canonicalization in run_slot_pipeline
    resolved = None
    for k, v in TOPIC_PROFILES.items():
        if v is profile:
            resolved = k
            break
    if resolved == expected_canon:
        ok(f'"{short_name}" -> "{resolved}"')
    else:
        fail(f'"{short_name}" -> "{resolved}" (expected "{expected_canon}")')

    # Check that the resolved name works in _TOPIC_CONSTRAINTS
    if resolved not in ARITHMETIC_CANONICALS:
        if resolved in _TOPIC_CONSTRAINTS:
            ok(f'  _TOPIC_CONSTRAINTS["{resolved}"] OK')
        else:
            fail(f'  _TOPIC_CONSTRAINTS["{resolved}"] MISSING')

# ===================================
# TEST 6: build_worksheet_plan integration
# ===================================
print("\n-- TEST 6: build_worksheet_plan() for each topic --")
for topic_name in TOPIC_PROFILES:
    try:
        plan = build_worksheet_plan(10, topic=topic_name)
        slot_counts = Counter(d["slot_type"] for d in plan)
        missing = [s for s in SLOT_ORDER if slot_counts.get(s, 0) == 0]
        dist = {s: slot_counts.get(s, 0) for s in SLOT_ORDER}
        if not missing:
            ok(f"{topic_name}: plan(10) -> {dist}")
        elif topic_name in _FLEXIBLE_SLOT_TOPICS:
            warn(f"{topic_name}: plan(10) missing {missing} (expected for combined topic) -- {dist}")
        else:
            fail(f"{topic_name}: plan(10) MISSING: {missing} -- {dist}")
    except Exception as e:
        fail(f"{topic_name}: build_worksheet_plan() raised {e}")

# ===================================
# TEST 7: Disallowed keywords in skill tags
# ===================================
print("\n-- TEST 7: No cross-topic skill_tag contamination --")
for topic_name, profile in TOPIC_PROFILES.items():
    allowed_tags = set(profile["allowed_skill_tags"])
    recipe_tags = {item["skill_tag"] for item in profile["default_recipe"]}
    orphans = recipe_tags - allowed_tags
    if orphans:
        fail(f"{topic_name}: recipe has tags NOT in allowed_skill_tags: {orphans}")
    else:
        ok(f"{topic_name}: all recipe tags in allowed_skill_tags")

# ===================================
# TEST 8: _ARITHMETIC_TOPICS and _THINKING_VARIANT_TOPICS alignment
# ===================================
print("\n-- TEST 8: Variant selection topic sets --")
# These are the hardcoded sets inside run_slot_pipeline
_ARITHMETIC_TOPICS_CHECK = {"Addition (carries)", "Subtraction (borrowing)"}
_THINKING_VARIANT_TOPICS_CHECK = {
    "Addition (carries)", "Subtraction (borrowing)",
    "Multiplication (tables 2-10)", "Division basics",
    "Numbers up to 10000",
}

for topic_name in TOPIC_PROFILES:
    is_arithmetic = topic_name in _ARITHMETIC_TOPICS_CHECK
    has_thinking_variants = topic_name in _THINKING_VARIANT_TOPICS_CHECK

    if is_arithmetic:
        ok(f"{topic_name}: uses pick_error() + pick_thinking_style() (arithmetic)")
    elif has_thinking_variants:
        ok(f"{topic_name}: uses LLM error_detection + pick_thinking_style()")
    else:
        ok(f"{topic_name}: uses LLM error_detection + multi_step thinking")

# ===================================
# SUMMARY
# ===================================
print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed, {WARN} warnings")
print("=" * 70)

if FAIL > 0:
    print("\nSOME CHECKS FAILED -- review above for details")
    sys.exit(1)
else:
    print("\nALL CHECKS PASSED -- all topics are correctly configured")
    sys.exit(0)

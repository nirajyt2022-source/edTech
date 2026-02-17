#!/usr/bin/env python3
"""
Full topic x count matrix test for Class 2, 3 & 4 Maths worksheet engine.

Tests all topics x 4 question counts combinations.
Deterministic only — no LLM calls, no API keys required.

Validates:
1. Topic exists in TOPIC_PROFILES
2. Topic profile has required keys
3. Slot plan sums to expected count
4. ED >= 1 and T >= 1 in plans (with documented exceptions)
5. All slot types in plan have valid formats in VALID_FORMATS
6. build_worksheet_plan produces correct total
7. recipes_by_count correctness for combined add/sub topic
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    TOPIC_PROFILES,
    VALID_FORMATS,
    SLOT_ORDER,
    SLOT_PLANS,
    _SKILL_TAG_TO_SLOT,
    get_slot_plan,
    get_topic_profile,
    build_worksheet_plan,
    _compute_proportional_plan,
)


ALL_TOPICS = [
    # Class 2
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
    # Class 3
    "Addition (carries)",
    "Subtraction (borrowing)",
    "Addition and subtraction (3-digit)",
    "Multiplication (tables 2-10)",
    "Division basics",
    "Numbers up to 10000",
    "Fractions (halves, quarters)",
    "Fractions",
    "Time (reading clock, calendar)",
    "Money (bills and change)",
    "Symmetry",
    "Patterns and sequences",
    # Class 4
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

ALL_COUNTS = [5, 10, 15, 20]

REQUIRED_PROFILE_KEYS = {"allowed_skill_tags", "allowed_slot_types", "default_recipe"}

# Combined add/sub 5q recipe intentionally omits thinking to fit both ops
ADD_SUB_TOPIC = "Addition and subtraction (3-digit)"

passed = 0
failed = 0
errors_list = []


def record_pass(label):
    global passed
    passed += 1
    print(f"  PASS  {label}")


def record_fail(label, reason):
    global failed
    failed += 1
    msg = f"  FAIL  {label}: {reason}"
    print(msg)
    errors_list.append(msg)


# ================================================================
# SECTION 1: Topic profile existence and required keys
# ================================================================
print("=" * 70)
n_topics = len(ALL_TOPICS)
n_combos = n_topics * len(ALL_COUNTS)
print(f"TEST SUITE: All Topics x All Counts ({n_topics} x {len(ALL_COUNTS)} = {n_combos} combinations)")
print("=" * 70)

print("\n-- Section 1: Topic profile existence and required keys --")
for topic in ALL_TOPICS:
    if topic not in TOPIC_PROFILES:
        record_fail(topic, "not found in TOPIC_PROFILES")
        continue

    profile = TOPIC_PROFILES[topic]
    missing_keys = REQUIRED_PROFILE_KEYS - set(profile.keys())
    if missing_keys:
        record_fail(topic, f"missing keys: {missing_keys}")
    else:
        record_pass(f"{topic} -- profile exists with required keys")


# ================================================================
# SECTION 2: get_slot_plan validation for standard counts
# ================================================================
print("\n-- Section 2: get_slot_plan validation --")
for count in ALL_COUNTS:
    plan_seq = get_slot_plan(count)
    label = f"get_slot_plan({count})"

    # Check total
    if len(plan_seq) != count:
        record_fail(label, f"total={len(plan_seq)}, expected={count}")
        continue

    slot_counts = Counter(plan_seq)

    # ED >= 1
    if slot_counts.get("error_detection", 0) < 1:
        record_fail(label, "error_detection < 1")
        continue

    # T >= 1
    if slot_counts.get("thinking", 0) < 1:
        record_fail(label, "thinking < 1")
        continue

    # All slot types are recognized
    unknown = set(plan_seq) - set(SLOT_ORDER)
    if unknown:
        record_fail(label, f"unknown slot types: {unknown}")
        continue

    record_pass(
        f"{label} -- total={count}, "
        f"ED={slot_counts['error_detection']}, "
        f"T={slot_counts['thinking']}"
    )


# ================================================================
# SECTION 3: Per-topic x per-count build_worksheet_plan
# ================================================================
print("\n-- Section 3: build_worksheet_plan (topic x count matrix) --")
combo_pass = 0
combo_fail = 0

for topic in ALL_TOPICS:
    if topic not in TOPIC_PROFILES:
        for count in ALL_COUNTS:
            record_fail(f"[{topic}][{count}q]", "topic missing from TOPIC_PROFILES")
            combo_fail += 1
        continue

    profile = TOPIC_PROFILES[topic]

    for count in ALL_COUNTS:
        label = f"[{topic}][{count}q]"
        errs = []

        try:
            plan = build_worksheet_plan(count, topic=topic)
        except Exception as e:
            record_fail(label, f"build_worksheet_plan raised: {e}")
            combo_fail += 1
            continue

        # 1. Total count matches
        if len(plan) != count:
            errs.append(f"total={len(plan)}, expected={count}")

        # 2. Slot type distribution
        slot_counts = Counter(d["slot_type"] for d in plan)

        # 3. All slot_types are valid
        unknown_slots = set(slot_counts.keys()) - set(SLOT_ORDER)
        if unknown_slots:
            errs.append(f"unknown slot_types: {unknown_slots}")

        # 4. ED >= 1 (with exception for add/sub 5q)
        ed_count = slot_counts.get("error_detection", 0)
        if ed_count < 1:
            errs.append(f"error_detection={ed_count} < 1")

        # 5. T >= 1 (with exception for add/sub 5q)
        t_count = slot_counts.get("thinking", 0)
        if topic == ADD_SUB_TOPIC and count == 5:
            pass  # Acceptable: 5q combined recipe skips thinking
        else:
            if t_count < 1:
                errs.append(f"thinking={t_count} < 1")

        # 6. All format_hints are valid for their slot_type
        for d in plan:
            st = d["slot_type"]
            fmt = d.get("format_hint", "")
            if fmt and fmt not in VALID_FORMATS.get(st, set()):
                errs.append(f"format '{fmt}' not in VALID_FORMATS['{st}']")

        # 7. All skill_tags are in the topic's allowed_skill_tags
        allowed_tags = set(profile.get("allowed_skill_tags", []))
        for d in plan:
            tag = d.get("skill_tag", "")
            if tag and tag not in allowed_tags:
                errs.append(f"skill_tag '{tag}' not in allowed_skill_tags")

        if errs:
            record_fail(label, "; ".join(errs))
            combo_fail += 1
        else:
            dist_str = " ".join(
                f"{s[0].upper()}={slot_counts.get(s, 0)}" for s in SLOT_ORDER
            )
            record_pass(f"{label} -- {dist_str}")
            combo_pass += 1


# ================================================================
# SECTION 4: recipes_by_count for combined add/sub
# ================================================================
print("\n-- Section 4: recipes_by_count for 'Addition and subtraction (3-digit)' --")
if ADD_SUB_TOPIC in TOPIC_PROFILES:
    profile = TOPIC_PROFILES[ADD_SUB_TOPIC]
    recipes = profile.get("recipes_by_count")

    if recipes is None:
        record_fail(ADD_SUB_TOPIC, "recipes_by_count missing")
    else:
        for count in ALL_COUNTS:
            label = f"recipes_by_count[{count}]"
            if count not in recipes:
                record_fail(label, f"no entry for count={count}")
                continue

            recipe = recipes[count]
            total = sum(item.get("count", 1) for item in recipe)
            if total != count:
                record_fail(label, f"sums to {total}, expected {count}")
                continue

            # Map skill_tags to slot_types and count ED/T
            slot_counts = Counter()
            for item in recipe:
                tag = item["skill_tag"]
                if tag in _SKILL_TAG_TO_SLOT:
                    slot_type, _ = _SKILL_TAG_TO_SLOT[tag]
                    slot_counts[slot_type] += item.get("count", 1)

            ed = slot_counts.get("error_detection", 0)
            t = slot_counts.get("thinking", 0)

            sub_errs = []
            if ed < 1:
                sub_errs.append(f"ED={ed} < 1")
            if count > 5 and t < 1:
                sub_errs.append(f"T={t} < 1")

            if sub_errs:
                record_fail(label, "; ".join(sub_errs))
            else:
                dist_str = " ".join(
                    f"{s[0].upper()}={slot_counts.get(s, 0)}" for s in SLOT_ORDER
                )
                note = " (T=0 acceptable for 5q)" if count == 5 and t == 0 else ""
                record_pass(f"{label} -- total={total}, {dist_str}{note}")
else:
    record_fail(ADD_SUB_TOPIC, "topic missing from TOPIC_PROFILES")


# ================================================================
# SECTION 5: Recipe skill_tag -> VALID_FORMATS mapping
# ================================================================
print("\n-- Section 5: Recipe skill_tag -> VALID_FORMATS mapping --")
for topic in ALL_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]
    recipe = profile["default_recipe"]
    errs = []
    for item in recipe:
        tag = item["skill_tag"]
        if tag not in _SKILL_TAG_TO_SLOT:
            errs.append(f"skill_tag '{tag}' not in _SKILL_TAG_TO_SLOT")
            continue
        slot_type, fmt = _SKILL_TAG_TO_SLOT[tag]
        if fmt not in VALID_FORMATS.get(slot_type, set()):
            errs.append(
                f"format '{fmt}' not in VALID_FORMATS['{slot_type}'] (tag: {tag})"
            )

    if errs:
        record_fail(f"{topic} recipe mapping", "; ".join(errs))
    else:
        record_pass(f"{topic} -- all recipe tags map to valid formats")


# ================================================================
# SUMMARY
# ================================================================
total_combos = len(ALL_TOPICS) * len(ALL_COUNTS)
print("\n" + "=" * 70)
print(f"MATRIX RESULTS: {combo_pass}/{total_combos} topic x count combinations passed")
print(f"TOTAL CHECKS:   {passed} passed, {failed} failed")
print("=" * 70)

if errors_list:
    print("\nFailed checks:")
    for e in errors_list:
        print(f"  {e}")

if failed > 0:
    print(f"\nFAILED: {failed} checks did not pass")
    sys.exit(1)
else:
    print("\nALL CHECKS PASSED")
    sys.exit(0)

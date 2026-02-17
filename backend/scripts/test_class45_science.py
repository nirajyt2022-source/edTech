#!/usr/bin/env python3
"""
Deterministic test for Class 4 & 5 Science topic profiles.

Validates 14 new topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_class45_science.py
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


# ── The 14 Science topics (canonical names) ──
CLASS4_SCIENCE_TOPICS = [
    "Living Things (Class 4)",
    "Human Body (Class 4)",
    "States of Matter (Class 4)",
    "Force and Motion (Class 4)",
    "Simple Machines (Class 4)",
    "Photosynthesis (Class 4)",
    "Animal Adaptation (Class 4)",
]

CLASS5_SCIENCE_TOPICS = [
    "Circulatory System (Class 5)",
    "Respiratory and Nervous System (Class 5)",
    "Reproduction in Plants and Animals (Class 5)",
    "Physical and Chemical Changes (Class 5)",
    "Forms of Energy (Class 5)",
    "Solar System and Earth (Class 5)",
    "Ecosystem and Food Chains (Class 5)",
]

ALL_SCIENCE_TOPICS = CLASS4_SCIENCE_TOPICS + CLASS5_SCIENCE_TOPICS

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Living Things (Class 4)": [
        "class 4 living things",
        "c4 living things",
        "Living Things (Class 4)",
    ],
    "Human Body (Class 4)": [
        "class 4 human body",
        "c4 human body",
        "Human Body (Class 4)",
    ],
    "States of Matter (Class 4)": [
        "class 4 matter",
        "c4 matter",
        "States of Matter (Class 4)",
    ],
    "Force and Motion (Class 4)": [
        "class 4 force",
        "c4 force",
        "Force and Motion (Class 4)",
    ],
    "Simple Machines (Class 4)": [
        "class 4 machines",
        "c4 machines",
        "Simple Machines (Class 4)",
    ],
    "Photosynthesis (Class 4)": [
        "class 4 photosynthesis",
        "c4 photosynthesis",
        "Photosynthesis (Class 4)",
    ],
    "Animal Adaptation (Class 4)": [
        "class 4 adaptation",
        "c4 adaptation",
        "Animal Adaptation (Class 4)",
    ],
    "Circulatory System (Class 5)": [
        "class 5 circulatory",
        "c5 circulatory",
        "Circulatory System (Class 5)",
    ],
    "Respiratory and Nervous System (Class 5)": [
        "class 5 respiratory",
        "c5 respiratory",
        "Respiratory and Nervous System (Class 5)",
    ],
    "Reproduction in Plants and Animals (Class 5)": [
        "class 5 reproduction",
        "c5 reproduction",
        "Reproduction in Plants and Animals (Class 5)",
    ],
    "Physical and Chemical Changes (Class 5)": [
        "class 5 changes",
        "c5 changes",
        "Physical and Chemical Changes (Class 5)",
    ],
    "Forms of Energy (Class 5)": [
        "class 5 energy",
        "c5 energy",
        "Forms of Energy (Class 5)",
    ],
    "Solar System and Earth (Class 5)": [
        "class 5 solar system",
        "c5 solar system",
        "Solar System and Earth (Class 5)",
    ],
    "Ecosystem and Food Chains (Class 5)": [
        "class 5 ecosystem",
        "c5 ecosystem",
        "Ecosystem and Food Chains (Class 5)",
    ],
}

# ── Maths keywords that Science topics must disallow ──
MATHS_KEYWORDS = {"add", "subtract", "multiply", "divide"}


print("=" * 60)
print("=== Class 4 & 5 Science \u2014 Deterministic Checks ===")
print("=" * 60)

for topic in ALL_SCIENCE_TOPICS:
    print(f"\n{topic}:")

    # ── 1. Topic exists in TOPIC_PROFILES ──
    if topic in TOPIC_PROFILES:
        ok("In TOPIC_PROFILES")
        profile = TOPIC_PROFILES[topic]
    else:
        fail(f"NOT in TOPIC_PROFILES")
        # Skip remaining checks if profile missing
        for _ in range(8):
            fail("(skipped \u2014 profile missing)")
        continue

    # ── 2. Has all required keys + subject = "Science" ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        if profile.get("subject") == "Science":
            ok("Has required keys + subject='Science'")
        else:
            fail(f"subject='{profile.get('subject')}', expected 'Science'")
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
print("Grade-specific checks: subject='Science' + disallow maths keywords:")
print("=" * 60)

for topic in ALL_SCIENCE_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]

    # All Science topics must have subject = "Science"
    if profile.get("subject") == "Science":
        ok(f"{topic}: subject='Science'")
    else:
        fail(f"{topic}: subject='{profile.get('subject')}', expected 'Science'")

    # All Science topics must disallow maths keywords
    disallowed = set(profile.get("disallowed_keywords", []))
    disallowed_lower = {kw.lower() for kw in disallowed}
    missing = MATHS_KEYWORDS - disallowed_lower
    if not missing:
        ok(f"{topic}: disallows maths keywords (add/subtract/multiply/divide)")
    else:
        fail(f"{topic}: missing disallowed maths keywords: {missing}")

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

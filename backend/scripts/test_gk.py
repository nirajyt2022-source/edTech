#!/usr/bin/env python3
"""
Deterministic test for Class 3-5 General Knowledge topic profiles.

Validates 12 GK topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_gk.py
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


# ── The 12 GK topics (canonical names) ──
CLASS3_GK_TOPICS = [
    "Famous Landmarks (Class 3)",
    "National Symbols (Class 3)",
    "Solar System Basics (Class 3)",
    "Current Awareness (Class 3)",
]

CLASS4_GK_TOPICS = [
    "Continents and Oceans (Class 4)",
    "Famous Scientists (Class 4)",
    "Festivals of India (Class 4)",
    "Sports and Games (Class 4)",
]

CLASS5_GK_TOPICS = [
    "Indian Constitution (Class 5)",
    "World Heritage Sites (Class 5)",
    "Space Missions (Class 5)",
    "Environmental Awareness (Class 5)",
]

ALL_GK_TOPICS = (
    CLASS3_GK_TOPICS
    + CLASS4_GK_TOPICS
    + CLASS5_GK_TOPICS
)

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Famous Landmarks (Class 3)": [
        "class 3 landmarks",
        "landmarks",
        "Famous Landmarks (Class 3)",
    ],
    "National Symbols (Class 3)": [
        "class 3 national symbols",
        "indian symbols",
        "National Symbols (Class 3)",
    ],
    "Solar System Basics (Class 3)": [
        "class 3 solar system",
        "planets",
        "Solar System Basics (Class 3)",
    ],
    "Current Awareness (Class 3)": [
        "class 3 current awareness",
        "festivals and seasons",
        "Current Awareness (Class 3)",
    ],
    "Continents and Oceans (Class 4)": [
        "class 4 continents",
        "continents",
        "Continents and Oceans (Class 4)",
    ],
    "Famous Scientists (Class 4)": [
        "class 4 scientists",
        "scientists",
        "Famous Scientists (Class 4)",
    ],
    "Festivals of India (Class 4)": [
        "class 4 festivals",
        "indian festivals",
        "Festivals of India (Class 4)",
    ],
    "Sports and Games (Class 4)": [
        "class 4 sports",
        "sports",
        "Sports and Games (Class 4)",
    ],
    "Indian Constitution (Class 5)": [
        "class 5 constitution",
        "constitution",
        "Indian Constitution (Class 5)",
    ],
    "World Heritage Sites (Class 5)": [
        "class 5 heritage",
        "heritage sites",
        "World Heritage Sites (Class 5)",
    ],
    "Space Missions (Class 5)": [
        "class 5 space",
        "isro",
        "Space Missions (Class 5)",
    ],
    "Environmental Awareness (Class 5)": [
        "class 5 environment",
        "pollution",
        "Environmental Awareness (Class 5)",
    ],
}

# ── Maths keywords that GK topics must disallow ──
MATHS_KEYWORDS = {"add", "subtract", "multiply", "divide"}


print("=" * 60)
print("=== Class 3-5 General Knowledge \u2014 Deterministic Checks ===")
print("=" * 60)

for topic in ALL_GK_TOPICS:
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

    # ── 2. Has all required keys + subject = "GK" ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        if profile.get("subject") == "GK":
            ok("Has required keys + subject='GK'")
        else:
            fail(f"subject='{profile.get('subject')}', expected 'GK'")
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
print("Grade-specific checks: subject='GK' + disallow maths keywords:")
print("=" * 60)

for topic in ALL_GK_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]

    # All GK topics must have subject = "GK"
    if profile.get("subject") == "GK":
        ok(f"{topic}: subject='GK'")
    else:
        fail(f"{topic}: subject='{profile.get('subject')}', expected 'GK'")

    # All GK topics must disallow maths keywords
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

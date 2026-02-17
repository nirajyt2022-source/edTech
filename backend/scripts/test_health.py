#!/usr/bin/env python3
"""
Deterministic test for Class 1-5 Health & PE topic profiles.

Validates 15 Health & PE topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_health.py
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


# ── The 15 Health & PE topics (canonical names) ──
CLASS1_HEALTH_TOPICS = [
    "Personal Hygiene (Class 1)",
    "Good Posture (Class 1)",
    "Basic Physical Activities (Class 1)",
]

CLASS2_HEALTH_TOPICS = [
    "Healthy Eating Habits (Class 2)",
    "Outdoor Play (Class 2)",
    "Basic Stretching (Class 2)",
]

CLASS3_HEALTH_TOPICS = [
    "Balanced Diet (Class 3)",
    "Team Sports Rules (Class 3)",
    "Safety at Play (Class 3)",
]

CLASS4_HEALTH_TOPICS = [
    "First Aid Basics (Class 4)",
    "Yoga Introduction (Class 4)",
    "Importance of Sleep (Class 4)",
]

CLASS5_HEALTH_TOPICS = [
    "Fitness and Stamina (Class 5)",
    "Nutrition Labels Reading (Class 5)",
    "Mental Health Awareness (Class 5)",
]

ALL_HEALTH_TOPICS = (
    CLASS1_HEALTH_TOPICS
    + CLASS2_HEALTH_TOPICS
    + CLASS3_HEALTH_TOPICS
    + CLASS4_HEALTH_TOPICS
    + CLASS5_HEALTH_TOPICS
)

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Personal Hygiene (Class 1)": [
        "class 1 hygiene",
        "c1 hygiene",
        "Personal Hygiene (Class 1)",
    ],
    "Good Posture (Class 1)": [
        "class 1 posture",
        "c1 posture",
        "Good Posture (Class 1)",
    ],
    "Basic Physical Activities (Class 1)": [
        "class 1 physical activities",
        "c1 physical",
        "Basic Physical Activities (Class 1)",
    ],
    "Healthy Eating Habits (Class 2)": [
        "class 2 healthy eating",
        "c2 eating",
        "Healthy Eating Habits (Class 2)",
    ],
    "Outdoor Play (Class 2)": [
        "class 2 outdoor play",
        "c2 outdoor",
        "Outdoor Play (Class 2)",
    ],
    "Basic Stretching (Class 2)": [
        "class 2 stretching",
        "c2 stretching",
        "Basic Stretching (Class 2)",
    ],
    "Balanced Diet (Class 3)": [
        "class 3 balanced diet",
        "c3 diet",
        "Balanced Diet (Class 3)",
    ],
    "Team Sports Rules (Class 3)": [
        "class 3 team sports",
        "c3 sports",
        "Team Sports Rules (Class 3)",
    ],
    "Safety at Play (Class 3)": [
        "class 3 safety",
        "c3 safety",
        "Safety at Play (Class 3)",
    ],
    "First Aid Basics (Class 4)": [
        "class 4 first aid",
        "c4 first aid",
        "First Aid Basics (Class 4)",
    ],
    "Yoga Introduction (Class 4)": [
        "class 4 yoga",
        "c4 yoga",
        "Yoga Introduction (Class 4)",
    ],
    "Importance of Sleep (Class 4)": [
        "class 4 sleep",
        "c4 sleep",
        "Importance of Sleep (Class 4)",
    ],
    "Fitness and Stamina (Class 5)": [
        "class 5 fitness",
        "c5 fitness",
        "Fitness and Stamina (Class 5)",
    ],
    "Nutrition Labels Reading (Class 5)": [
        "class 5 nutrition",
        "c5 nutrition",
        "Nutrition Labels Reading (Class 5)",
    ],
    "Mental Health Awareness (Class 5)": [
        "class 5 mental health",
        "c5 mental health",
        "Mental Health Awareness (Class 5)",
    ],
}

# ── Maths keywords that Health & PE topics must disallow ──
MATHS_KEYWORDS = {"add", "subtract", "multiply", "divide"}


print("=" * 60)
print("=== Class 1-5 Health & PE \u2014 Deterministic Checks ===")
print("=" * 60)

for topic in ALL_HEALTH_TOPICS:
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

    # ── 2. Has all required keys + subject = "Health" ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        if profile.get("subject") == "Health":
            ok("Has required keys + subject='Health'")
        else:
            fail(f"subject='{profile.get('subject')}', expected 'Health'")
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
print("Grade-specific checks: subject='Health' + disallow maths keywords:")
print("=" * 60)

for topic in ALL_HEALTH_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]

    # All Health & PE topics must have subject = "Health"
    if profile.get("subject") == "Health":
        ok(f"{topic}: subject='Health'")
    else:
        fail(f"{topic}: subject='{profile.get('subject')}', expected 'Health'")

    # All Health & PE topics must disallow maths keywords
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

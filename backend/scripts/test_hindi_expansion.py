#!/usr/bin/env python3
"""
Deterministic test for Class 1, 2, 4, 5 Hindi topic profiles.

Validates 19 Hindi topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_hindi_expansion.py
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


# ── The 19 Hindi topics (canonical names) ──
CLASS1_HINDI_TOPICS = [
    "Varnamala Swar (Class 1)",
    "Varnamala Vyanjan (Class 1)",
    "Family Words (Class 1)",
    "Simple Sentences (Class 1)",
]

CLASS2_HINDI_TOPICS = [
    "Matras Introduction (Class 2)",
    "Two Letter Words (Class 2)",
    "Three Letter Words (Class 2)",
    "Rhymes and Poems (Class 2)",
    "Nature Vocabulary (Class 2)",
]

CLASS4_HINDI_TOPICS = [
    "Anusvaar and Visarg (Class 4)",
    "Vachan and Ling (Class 4)",
    "Kaal (Class 4)",
    "Patra Lekhan (Class 4)",
    "Comprehension Hindi (Class 4)",
]

CLASS5_HINDI_TOPICS = [
    "Muhavare (Class 5)",
    "Paryayvachi Shabd (Class 5)",
    "Vilom Shabd (Class 5)",
    "Samas (Class 5)",
    "Samvad Lekhan (Class 5)",
]

ALL_HINDI_TOPICS = (
    CLASS1_HINDI_TOPICS
    + CLASS2_HINDI_TOPICS
    + CLASS4_HINDI_TOPICS
    + CLASS5_HINDI_TOPICS
)

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Varnamala Swar (Class 1)": [
        "class 1 varnamala swar",
        "hindi vowels",
        "Varnamala Swar (Class 1)",
    ],
    "Varnamala Vyanjan (Class 1)": [
        "class 1 varnamala vyanjan",
        "hindi consonants",
        "Varnamala Vyanjan (Class 1)",
    ],
    "Family Words (Class 1)": [
        "class 1 family words",
        "parivar shabd",
        "Family Words (Class 1)",
    ],
    "Simple Sentences (Class 1)": [
        "class 1 simple sentences",
        "c1 sentences",
        "Simple Sentences (Class 1)",
    ],
    "Matras Introduction (Class 2)": [
        "class 2 matras",
        "c2 matras",
        "Matras Introduction (Class 2)",
    ],
    "Two Letter Words (Class 2)": [
        "class 2 two letter words",
        "c2 two letter",
        "Two Letter Words (Class 2)",
    ],
    "Three Letter Words (Class 2)": [
        "class 2 three letter words",
        "c2 three letter",
        "Three Letter Words (Class 2)",
    ],
    "Rhymes and Poems (Class 2)": [
        "class 2 rhymes",
        "hindi kavita",
        "Rhymes and Poems (Class 2)",
    ],
    "Nature Vocabulary (Class 2)": [
        "class 2 nature vocabulary",
        "prakriti shabd",
        "Nature Vocabulary (Class 2)",
    ],
    "Anusvaar and Visarg (Class 4)": [
        "class 4 anusvaar",
        "c4 anusvaar",
        "Anusvaar and Visarg (Class 4)",
    ],
    "Vachan and Ling (Class 4)": [
        "class 4 vachan ling",
        "c4 vachan ling",
        "Vachan and Ling (Class 4)",
    ],
    "Kaal (Class 4)": [
        "class 4 kaal",
        "c4 kaal",
        "Kaal (Class 4)",
    ],
    "Patra Lekhan (Class 4)": [
        "class 4 patra lekhan",
        "c4 patra lekhan",
        "Patra Lekhan (Class 4)",
    ],
    "Comprehension Hindi (Class 4)": [
        "class 4 comprehension hindi",
        "c4 hindi comprehension",
        "Comprehension Hindi (Class 4)",
    ],
    "Muhavare (Class 5)": [
        "class 5 muhavare",
        "c5 muhavare",
        "Muhavare (Class 5)",
    ],
    "Paryayvachi Shabd (Class 5)": [
        "class 5 paryayvachi",
        "c5 paryayvachi",
        "Paryayvachi Shabd (Class 5)",
    ],
    "Vilom Shabd (Class 5)": [
        "class 5 vilom",
        "c5 vilom",
        "Vilom Shabd (Class 5)",
    ],
    "Samas (Class 5)": [
        "class 5 samas",
        "c5 samas",
        "Samas (Class 5)",
    ],
    "Samvad Lekhan (Class 5)": [
        "class 5 samvad lekhan",
        "c5 samvad",
        "Samvad Lekhan (Class 5)",
    ],
}

# ── Maths keywords that Hindi topics must disallow ──
MATHS_KEYWORDS = {"add", "subtract", "multiply", "divide"}


print("=" * 60)
print("=== Class 1, 2, 4, 5 Hindi \u2014 Deterministic Checks ===")
print("=" * 60)

for topic in ALL_HINDI_TOPICS:
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

    # ── 2. Has all required keys + subject = "Hindi" ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        if profile.get("subject") == "Hindi":
            ok("Has required keys + subject='Hindi'")
        else:
            fail(f"subject='{profile.get('subject')}', expected 'Hindi'")
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
print("Grade-specific checks: subject='Hindi' + disallow maths keywords:")
print("=" * 60)

for topic in ALL_HINDI_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]

    # All Hindi topics must have subject = "Hindi"
    if profile.get("subject") == "Hindi":
        ok(f"{topic}: subject='Hindi'")
    else:
        fail(f"{topic}: subject='{profile.get('subject')}', expected 'Hindi'")

    # All Hindi topics must disallow maths keywords
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

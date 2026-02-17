#!/usr/bin/env python3
"""
Deterministic test for Class 1-5 Computer topic profiles.

Validates 15 new topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_computer.py
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


# ── The 15 Computer topics (canonical names) ──
CLASS1_COMPUTER_TOPICS = [
    "Parts of Computer (Class 1)",
    "Using Mouse and Keyboard (Class 1)",
]

CLASS2_COMPUTER_TOPICS = [
    "Desktop and Icons (Class 2)",
    "Basic Typing (Class 2)",
    "Special Keys (Class 2)",
]

CLASS3_COMPUTER_TOPICS = [
    "MS Paint Basics (Class 3)",
    "Keyboard Shortcuts (Class 3)",
    "Files and Folders (Class 3)",
]

CLASS4_COMPUTER_TOPICS = [
    "MS Word Basics (Class 4)",
    "Introduction to Scratch (Class 4)",
    "Internet Safety (Class 4)",
]

CLASS5_COMPUTER_TOPICS = [
    "Scratch Programming (Class 5)",
    "Internet Basics (Class 5)",
    "MS PowerPoint Basics (Class 5)",
    "Digital Citizenship (Class 5)",
]

ALL_COMPUTER_TOPICS = (
    CLASS1_COMPUTER_TOPICS
    + CLASS2_COMPUTER_TOPICS
    + CLASS3_COMPUTER_TOPICS
    + CLASS4_COMPUTER_TOPICS
    + CLASS5_COMPUTER_TOPICS
)

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Parts of Computer (Class 1)": [
        "class 1 parts of computer",
        "computer parts class 1",
        "Parts of Computer (Class 1)",
    ],
    "Using Mouse and Keyboard (Class 1)": [
        "class 1 mouse and keyboard",
        "mouse keyboard",
        "Using Mouse and Keyboard (Class 1)",
    ],
    "Desktop and Icons (Class 2)": [
        "class 2 desktop and icons",
        "desktop icons",
        "Desktop and Icons (Class 2)",
    ],
    "Basic Typing (Class 2)": [
        "class 2 basic typing",
        "typing basics",
        "Basic Typing (Class 2)",
    ],
    "Special Keys (Class 2)": [
        "class 2 special keys",
        "keyboard special keys",
        "Special Keys (Class 2)",
    ],
    "MS Paint Basics (Class 3)": [
        "class 3 ms paint",
        "ms paint",
        "MS Paint Basics (Class 3)",
    ],
    "Keyboard Shortcuts (Class 3)": [
        "class 3 keyboard shortcuts",
        "shortcuts",
        "Keyboard Shortcuts (Class 3)",
    ],
    "Files and Folders (Class 3)": [
        "class 3 files and folders",
        "file management",
        "Files and Folders (Class 3)",
    ],
    "MS Word Basics (Class 4)": [
        "class 4 ms word",
        "ms word",
        "MS Word Basics (Class 4)",
    ],
    "Introduction to Scratch (Class 4)": [
        "class 4 scratch",
        "scratch intro",
        "Introduction to Scratch (Class 4)",
    ],
    "Internet Safety (Class 4)": [
        "class 4 internet safety",
        "cyber safety",
        "Internet Safety (Class 4)",
    ],
    "Scratch Programming (Class 5)": [
        "class 5 scratch",
        "scratch class 5",
        "Scratch Programming (Class 5)",
    ],
    "Internet Basics (Class 5)": [
        "class 5 internet",
        "internet class 5",
        "Internet Basics (Class 5)",
    ],
    "MS PowerPoint Basics (Class 5)": [
        "class 5 powerpoint",
        "ms powerpoint",
        "MS PowerPoint Basics (Class 5)",
    ],
    "Digital Citizenship (Class 5)": [
        "class 5 digital citizenship",
        "digital citizen",
        "Digital Citizenship (Class 5)",
    ],
}

# ── Maths keywords that Computer topics must disallow ──
MATHS_KEYWORDS = {"add", "subtract", "multiply", "divide"}


print("=" * 60)
print("=== Class 1-5 Computer \u2014 Deterministic Checks ===")
print("=" * 60)

for topic in ALL_COMPUTER_TOPICS:
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

    # ── 2. Has all required keys + subject = "Computer" ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        if profile.get("subject") == "Computer":
            ok("Has required keys + subject='Computer'")
        else:
            fail(f"subject='{profile.get('subject')}', expected 'Computer'")
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
print("Grade-specific checks: subject='Computer' + disallow maths keywords:")
print("=" * 60)

for topic in ALL_COMPUTER_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]

    # All Computer topics must have subject = "Computer"
    if profile.get("subject") == "Computer":
        ok(f"{topic}: subject='Computer'")
    else:
        fail(f"{topic}: subject='{profile.get('subject')}', expected 'Computer'")

    # All Computer topics must disallow maths keywords
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

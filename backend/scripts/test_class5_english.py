#!/usr/bin/env python3
"""
Deterministic test for Class 5 English topic profiles.

Validates 9 new topics — no LLM or API key needed.

Usage:
  cd backend
  python scripts/test_class5_english.py
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
    print(f"  ✓ {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ✗ {msg}")


# ── The 9 Class 5 English topics (canonical names) ──
CLASS5_TOPICS = [
    "Active and Passive Voice (Class 5)",
    "Direct and Indirect Speech (Class 5)",
    "Complex Sentences (Class 5)",
    "Summary Writing (Class 5)",
    "Comprehension (Class 5)",
    "Synonyms and Antonyms (Class 5)",
    "Formal Letter Writing (Class 5)",
    "Creative Writing (Class 5)",
    "Clauses (Class 5)",
]

# ── Required keys in every profile ──
REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}

# ── Aliases that should resolve to each canonical topic ──
TOPIC_ALIASES = {
    "Active and Passive Voice (Class 5)": [
        "class 5 voice", "c5 voice", "active passive",
        "Active and Passive Voice (Class 5)",
    ],
    "Direct and Indirect Speech (Class 5)": [
        "class 5 speech", "c5 speech", "direct and indirect speech",
        "Direct and Indirect Speech (Class 5)",
    ],
    "Complex Sentences (Class 5)": [
        "class 5 complex sentences", "c5 complex sentences",
        "Complex Sentences (Class 5)",
    ],
    "Summary Writing (Class 5)": [
        "class 5 summary", "c5 summary", "summary writing",
        "Summary Writing (Class 5)",
    ],
    "Comprehension (Class 5)": [
        "class 5 comprehension", "c5 comprehension",
        "Comprehension (Class 5)",
    ],
    "Synonyms and Antonyms (Class 5)": [
        "class 5 synonyms", "c5 synonyms", "synonyms and antonyms",
        "Synonyms and Antonyms (Class 5)",
    ],
    "Formal Letter Writing (Class 5)": [
        "class 5 letter writing", "c5 letter writing", "formal letter",
        "Formal Letter Writing (Class 5)",
    ],
    "Creative Writing (Class 5)": [
        "class 5 creative writing", "c5 creative writing",
        "Creative Writing (Class 5)",
    ],
    "Clauses (Class 5)": [
        "class 5 clauses", "c5 clauses",
        "Clauses (Class 5)",
    ],
}

# ── Maths keywords that English topics must disallow ──
MATHS_KEYWORDS = {"add", "subtract", "multiply", "divide"}


print("=" * 60)
print("=== Class 5 English — Deterministic Checks ===")
print("=" * 60)

for topic in CLASS5_TOPICS:
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

    # ── 2. Has all required keys + subject = "English" ──
    missing_keys = REQUIRED_KEYS - set(profile.keys())
    if not missing_keys:
        if profile.get("subject") == "English":
            ok("Has required keys + subject='English'")
        else:
            fail(f"subject='{profile.get('subject')}', expected 'English'")
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
print("Grade-specific checks: subject='English' + disallow maths keywords:")
print("=" * 60)

for topic in CLASS5_TOPICS:
    if topic not in TOPIC_PROFILES:
        continue
    profile = TOPIC_PROFILES[topic]

    # All Class 5 English topics must have subject = "English"
    if profile.get("subject") == "English":
        ok(f"{topic}: subject='English'")
    else:
        fail(f"{topic}: subject='{profile.get('subject')}', expected 'English'")

    # All Class 5 English topics must disallow maths keywords
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

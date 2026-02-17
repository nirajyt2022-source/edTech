#!/usr/bin/env python3
"""
Deterministic test suite for Science topics (Phase 8).

Checks (no LLM calls):
1. All 7 Science topic profiles exist and have correct structure
2. Format validation uses VALID_FORMATS_SCIENCE (not Maths or English)
3. validate_question() with subject="Science" accepts Science formats
4. validate_question() with subject="Science" rejects Maths/English formats
5. Alias resolution for Science topics
6. Learning objectives exist for all 7 topics
7. Context bank entries exist for all 7 topics
8. Topic constraints exist for all 7 topics
9. enforce_slot_counts uses Science formats for Science subject
10. backfill_format uses Science defaults for Science subject
11. QUESTION_SYSTEM_SCIENCE exists with correct content
12. Maths + English regression guard
13. Slot plan validation for all 7 topics × {5, 10, 15, 20} = 28 combinations
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    TOPIC_PROFILES, _TOPIC_ALIASES, _SKILL_TAG_TO_SLOT,
    VALID_FORMATS, VALID_FORMATS_ENGLISH, VALID_FORMATS_SCIENCE,
    get_valid_formats, get_default_format_by_slot,
    DEFAULT_FORMAT_BY_SLOT_TYPE, DEFAULT_FORMAT_BY_SLOT_TYPE_SCIENCE,
    SLOT_ORDER, get_topic_profile, build_worksheet_plan,
    _TOPIC_CONSTRAINTS,
    LEARNING_OBJECTIVES, TOPIC_CONTEXT_BANK,
    validate_question, enforce_slot_counts, backfill_format,
    normalize_text_answer, normalize_english_answers,
    QUESTION_SYSTEM_SCIENCE,
)

PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  PASS {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL {msg}")


# ── Expected Science topics ──
SCIENCE_CLASS_3 = [
    "Plants (Class 3)", "Animals (Class 3)", "Food and Nutrition (Class 3)",
    "Shelter (Class 3)", "Water (Class 3)", "Air (Class 3)", "Our Body (Class 3)",
]
ALL_SCIENCE = SCIENCE_CLASS_3
ALL_COUNTS = [5, 10, 15, 20]

print("=" * 70)
print("SCIENCE TOPIC VERIFICATION — Phase 8")
print("=" * 70)

# ===================================
# TEST 1: All 7 profiles exist
# ===================================
print("\n-- TEST 1: Science Topic Profiles Exist --")
for topic in ALL_SCIENCE:
    if topic in TOPIC_PROFILES:
        prof = TOPIC_PROFILES[topic]
        if prof.get("subject") == "Science":
            ok(f'"{topic}" exists with subject=Science')
        else:
            fail(f'"{topic}" exists but subject is not Science: {prof.get("subject")}')
    else:
        fail(f'"{topic}" NOT in TOPIC_PROFILES')

# ===================================
# TEST 2: Profile structure
# ===================================
print("\n-- TEST 2: Profile Structure --")
required_keys = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}
for topic in ALL_SCIENCE:
    prof = TOPIC_PROFILES.get(topic, {})
    missing = required_keys - set(prof.keys())
    if not missing:
        ok(f'"{topic}" has all required keys')
    else:
        fail(f'"{topic}" missing keys: {missing}')

# ===================================
# TEST 3: Skill tag to slot mapping
# ===================================
print("\n-- TEST 3: Skill Tags -> Slot Mapping (Science Formats) --")
for topic in ALL_SCIENCE:
    prof = TOPIC_PROFILES.get(topic, {})
    for item in prof.get("default_recipe", []):
        tag = item["skill_tag"]
        if tag in _SKILL_TAG_TO_SLOT:
            slot_type, fmt = _SKILL_TAG_TO_SLOT[tag]
            if fmt in VALID_FORMATS_SCIENCE.get(slot_type, set()):
                ok(f"{tag} -> ({slot_type}, {fmt})")
            else:
                fail(f"{tag} -> ({slot_type}, {fmt}) -- '{fmt}' not in VALID_FORMATS_SCIENCE['{slot_type}']")
        else:
            fail(f"{tag} -> NOT IN _SKILL_TAG_TO_SLOT")

# ===================================
# TEST 4: All 5 slot types covered
# ===================================
print("\n-- TEST 4: All 5 Slot Types Covered --")
for topic in ALL_SCIENCE:
    prof = TOPIC_PROFILES.get(topic, {})
    slot_counts = Counter()
    for item in prof.get("default_recipe", []):
        tag = item["skill_tag"]
        if tag in _SKILL_TAG_TO_SLOT:
            st, _ = _SKILL_TAG_TO_SLOT[tag]
            slot_counts[st] += item["count"]
    missing = [s for s in SLOT_ORDER if slot_counts.get(s, 0) == 0]
    total = sum(slot_counts.values())
    if not missing:
        ok(f"{topic}: {total}q -> R={slot_counts['recognition']} A={slot_counts['application']} Rep={slot_counts['representation']} ED={slot_counts['error_detection']} T={slot_counts['thinking']}")
    else:
        fail(f"{topic}: MISSING slot types: {missing}")

# ===================================
# TEST 5: validate_question with Science subject
# ===================================
print("\n-- TEST 5: validate_question (Science) --")

# Science question should pass with Science formats
sci_q = {
    "format": "pick_correct_science",
    "question_text": "Which part of the plant makes food? (a) Root (b) Leaf (c) Stem (d) Flower",
    "answer": "Leaf",
    "pictorial_elements": [],
}
issues = validate_question(sci_q, "recognition", subject="Science")
if not issues:
    ok("Science recognition question with pick_correct_science: accepted")
else:
    fail(f"Science recognition question rejected: {issues}")

# Maths format should fail for Science
maths_q = {
    "format": "column_setup",
    "question_text": "Which part of the plant makes food?",
    "answer": "Leaf",
    "pictorial_elements": [],
}
issues = validate_question(maths_q, "recognition", subject="Science")
if any("format" in i for i in issues):
    ok("Maths format 'column_setup' rejected for Science recognition")
else:
    fail("Maths format 'column_setup' should be rejected for Science")

# English format should fail for Science
eng_q = {
    "format": "identify_noun",
    "question_text": "Which part of the plant makes food?",
    "answer": "Leaf",
    "pictorial_elements": [],
}
issues = validate_question(eng_q, "recognition", subject="Science")
if any("format" in i for i in issues):
    ok("English format 'identify_noun' rejected for Science recognition")
else:
    fail("English format 'identify_noun' should be rejected for Science")

# Science error_detection should check factual error language
sci_error_q = {
    "format": "error_spot_science",
    "question_text": "Find the mistake: Roots make food for the plant.",
    "answer": "Leaves make food for the plant, not roots.",
    "skill_tag": "sci_plants_error",
    "pictorial_elements": [],
}
issues = validate_question(sci_error_q, "error_detection", subject="Science")
if not issues:
    ok("Science error_detection with factual error language: accepted")
else:
    fail(f"Science error_detection rejected: {issues}")

# Science thinking should check reasoning language
sci_think_q = {
    "format": "thinking_science",
    "question_text": "Why do you think plants need sunlight to grow? Explain your answer.",
    "answer": "Plants need sunlight for photosynthesis to make food.",
    "pictorial_elements": [],
}
issues = validate_question(sci_think_q, "thinking", subject="Science")
if not issues:
    ok("Science thinking with reasoning language: accepted")
else:
    fail(f"Science thinking rejected: {issues}")

# Science question should reject pictorial_elements
sci_pic_q = {
    "format": "pick_correct_science",
    "question_text": "Which part of the plant absorbs water from the soil?",
    "answer": "Root",
    "pictorial_elements": [{"type": "diagram"}],
}
issues = validate_question(sci_pic_q, "recognition", subject="Science")
if any("pictorial" in i for i in issues):
    ok("Science question with pictorial_elements: correctly rejected")
else:
    fail("Science question with pictorial_elements should be rejected")

# ===================================
# TEST 6: get_valid_formats / get_default_format_by_slot
# ===================================
print("\n-- TEST 6: Subject-Aware Format Lookups --")
if get_valid_formats("Science") is VALID_FORMATS_SCIENCE:
    ok("get_valid_formats('Science') returns VALID_FORMATS_SCIENCE")
else:
    fail("get_valid_formats('Science') does not return VALID_FORMATS_SCIENCE")

if get_default_format_by_slot("Science") is DEFAULT_FORMAT_BY_SLOT_TYPE_SCIENCE:
    ok("get_default_format_by_slot('Science') returns Science defaults")
else:
    fail("get_default_format_by_slot('Science') wrong")

# Verify all 5 slot types have formats
for st in SLOT_ORDER:
    if st in VALID_FORMATS_SCIENCE and len(VALID_FORMATS_SCIENCE[st]) >= 1:
        ok(f"VALID_FORMATS_SCIENCE['{st}']: {len(VALID_FORMATS_SCIENCE[st])} formats")
    else:
        fail(f"VALID_FORMATS_SCIENCE['{st}'] missing or empty")

# ===================================
# TEST 7: Alias resolution
# ===================================
print("\n-- TEST 7: Science Alias Resolution --")
science_aliases = {
    "plants": "Plants (Class 3)",
    "class 3 plants": "Plants (Class 3)",
    "parts of a plant": "Plants (Class 3)",
    "animals": "Animals (Class 3)",
    "class 3 animals": "Animals (Class 3)",
    "animal habitats": "Animals (Class 3)",
    "food and nutrition": "Food and Nutrition (Class 3)",
    "class 3 food": "Food and Nutrition (Class 3)",
    "nutrition": "Food and Nutrition (Class 3)",
    "balanced diet": "Food and Nutrition (Class 3)",
    "shelter": "Shelter (Class 3)",
    "class 3 shelter": "Shelter (Class 3)",
    "houses and shelters": "Shelter (Class 3)",
    "water": "Water (Class 3)",
    "class 3 water": "Water (Class 3)",
    "sources of water": "Water (Class 3)",
    "water cycle": "Water (Class 3)",
    "air": "Air (Class 3)",
    "class 3 air": "Air (Class 3)",
    "air around us": "Air (Class 3)",
    "our body": "Our Body (Class 3)",
    "class 3 body": "Our Body (Class 3)",
    "human body": "Our Body (Class 3)",
    "body parts": "Our Body (Class 3)",
}
for alias, expected in science_aliases.items():
    profile = get_topic_profile(alias)
    if not profile:
        fail(f'"{alias}" -> NO MATCH')
        continue
    resolved = None
    for k, v in TOPIC_PROFILES.items():
        if v is profile:
            resolved = k
            break
    if resolved == expected:
        ok(f'"{alias}" -> "{resolved}"')
    else:
        fail(f'"{alias}" -> "{resolved}" (expected "{expected}")')

# ===================================
# TEST 8: Learning objectives
# ===================================
print("\n-- TEST 8: Learning Objectives --")
for topic in ALL_SCIENCE:
    if topic in LEARNING_OBJECTIVES:
        objs = LEARNING_OBJECTIVES[topic]
        if len(objs) >= 3:
            ok(f'"{topic}": {len(objs)} objectives')
        else:
            fail(f'"{topic}": only {len(objs)} objectives (need 3)')
    else:
        fail(f'"{topic}": NO learning objectives')

# ===================================
# TEST 9: Context bank
# ===================================
print("\n-- TEST 9: Topic Context Bank --")
for topic in ALL_SCIENCE:
    if topic in TOPIC_CONTEXT_BANK:
        entries = TOPIC_CONTEXT_BANK[topic]
        if len(entries) >= 10:
            ok(f'"{topic}": {len(entries)} context entries')
        else:
            fail(f'"{topic}": only {len(entries)} entries (need 10)')
    else:
        fail(f'"{topic}": NO context bank entries')

# ===================================
# TEST 10: Topic constraints
# ===================================
print("\n-- TEST 10: Topic Constraints --")
for topic in ALL_SCIENCE:
    if topic in _TOPIC_CONSTRAINTS:
        constraint = _TOPIC_CONSTRAINTS[topic]
        if "NEVER" in constraint and "arithmetic" in constraint.lower():
            ok(f'"{topic}": has constraint with arithmetic prohibition ({len(constraint)} chars)')
        else:
            fail(f'"{topic}": constraint exists but missing arithmetic prohibition')
    else:
        fail(f'"{topic}": NO topic constraint')

# ===================================
# TEST 11: enforce_slot_counts with Science
# ===================================
print("\n-- TEST 11: enforce_slot_counts (Science) --")
sci_questions = [
    {"id": 1, "slot_type": "recognition", "format": "pick_correct_science", "question_text": "test q about plants", "answer": "a"},
    {"id": 2, "slot_type": "application", "format": "explain_why_science", "question_text": "explain why plants need water", "answer": "a"},
]
plan = ["recognition", "application", "representation"]
result = enforce_slot_counts(sci_questions, plan, subject="Science")
if len(result) == 3:
    filler = result[2]
    if filler["format"] in VALID_FORMATS_SCIENCE.get("representation", set()):
        ok(f"enforce_slot_counts Science filler format: {filler['format']}")
    else:
        fail(f"enforce_slot_counts Science filler format wrong: {filler['format']}")
else:
    fail(f"enforce_slot_counts returned {len(result)} questions, expected 3")

# ===================================
# TEST 12: backfill_format with Science
# ===================================
print("\n-- TEST 12: backfill_format (Science) --")
q = {"slot_type": "recognition"}
backfill_format(q, {"slot_type": "recognition"}, subject="Science")
if q["format"] == "pick_correct_science":
    ok(f"backfill_format Science recognition default: {q['format']}")
else:
    fail(f"backfill_format Science recognition: {q['format']} (expected pick_correct_science)")

q2 = {"slot_type": "error_detection"}
backfill_format(q2, {"slot_type": "error_detection"}, subject="Science")
if q2["format"] == "error_spot_science":
    ok(f"backfill_format Science error_detection default: {q2['format']}")
else:
    fail(f"backfill_format Science error_detection: {q2['format']} (expected error_spot_science)")

q3 = {"slot_type": "thinking"}
backfill_format(q3, {"slot_type": "thinking"}, subject="Science")
if q3["format"] == "thinking_science":
    ok(f"backfill_format Science thinking default: {q3['format']}")
else:
    fail(f"backfill_format Science thinking: {q3['format']} (expected thinking_science)")

# ===================================
# TEST 13: QUESTION_SYSTEM_SCIENCE
# ===================================
print("\n-- TEST 13: QUESTION_SYSTEM_SCIENCE --")
if "scientifically accurate" in QUESTION_SYSTEM_SCIENCE:
    ok("QUESTION_SYSTEM_SCIENCE mentions scientific accuracy")
else:
    fail("QUESTION_SYSTEM_SCIENCE missing scientific accuracy reference")

if "Indian" in QUESTION_SYSTEM_SCIENCE:
    ok("QUESTION_SYSTEM_SCIENCE mentions Indian contexts")
else:
    fail("QUESTION_SYSTEM_SCIENCE missing Indian context reference")

if "arithmetic" in QUESTION_SYSTEM_SCIENCE.lower():
    ok("QUESTION_SYSTEM_SCIENCE prohibits arithmetic")
else:
    fail("QUESTION_SYSTEM_SCIENCE missing arithmetic prohibition")

# ===================================
# TEST 14: Slot plan validation (28 combinations)
# ===================================
print("\n-- TEST 14: Slot Plan Validation (7 × 4 = 28 combinations) --")
for topic in ALL_SCIENCE:
    prof = TOPIC_PROFILES[topic]
    for count in ALL_COUNTS:
        plan = build_worksheet_plan(count, topic=topic)
        slot_types = [d["slot_type"] for d in plan]
        slot_counts = Counter(slot_types)
        total = sum(slot_counts.values())
        errors = []

        if total != count:
            errors.append(f"total={total}, expected {count}")
        if slot_counts.get("error_detection", 0) < 1:
            errors.append("ED < 1")
        if slot_counts.get("thinking", 0) < 1:
            errors.append("T < 1")

        # Check all slot_types are valid
        for st in slot_types:
            if st not in SLOT_ORDER:
                errors.append(f"invalid slot_type: {st}")

        # Check all skill_tags in plan are in allowed list
        allowed_tags = set(prof.get("allowed_skill_tags", []))
        for d in plan:
            tag = d.get("skill_tag", "")
            if tag and tag not in allowed_tags:
                errors.append(f"skill_tag '{tag}' not in allowed list")

        # Check all formats are valid Science formats
        for d in plan:
            fmt = d.get("format", "")
            st = d.get("slot_type", "")
            if fmt and fmt not in VALID_FORMATS_SCIENCE.get(st, set()):
                errors.append(f"format '{fmt}' not in VALID_FORMATS_SCIENCE['{st}']")

        if errors:
            fail(f"{topic} [{count}q]: {errors}")
        else:
            ok(f"{topic} [{count}q]: {total}q -> R={slot_counts.get('recognition',0)} A={slot_counts.get('application',0)} Rep={slot_counts.get('representation',0)} ED={slot_counts.get('error_detection',0)} T={slot_counts.get('thinking',0)}")

# ===================================
# TEST 15: Maths + English Regression Guard
# ===================================
print("\n-- TEST 15: Maths + English Regression Guard --")
maths_recognition_q = {
    "format": "column_setup",
    "question_text": "Write 345 + 278 in column form.",
    "answer": "623",
    "pictorial_elements": [],
}
issues = validate_question(maths_recognition_q, "recognition")
if not issues:
    ok("Maths column_setup still accepted for default subject")
else:
    fail(f"Maths column_setup rejected: {issues}")

eng_recognition_q = {
    "format": "identify_noun",
    "question_text": "Find the noun in this sentence: The cat sat on the mat.",
    "answer": "cat, mat",
    "pictorial_elements": [],
}
issues = validate_question(eng_recognition_q, "recognition", subject="English")
if not issues:
    ok("English identify_noun still accepted for subject='English'")
else:
    fail(f"English identify_noun rejected: {issues}")

# Verify format isolation: Science formats not in Maths or English
for st, fmts in VALID_FORMATS_SCIENCE.items():
    for fmt in fmts:
        if fmt in VALID_FORMATS.get(st, set()):
            fail(f"Science format '{fmt}' leaks into Maths VALID_FORMATS['{st}']")
        elif fmt in VALID_FORMATS_ENGLISH.get(st, set()):
            fail(f"Science format '{fmt}' leaks into English VALID_FORMATS_ENGLISH['{st}']")
        else:
            ok(f"Science format '{fmt}' properly isolated from Maths/English")

# ===================================
# RESULTS
# ===================================
print()
print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)

if FAIL == 0:
    print("\nALL CHECKS PASSED -- Science Engine is correctly configured")
else:
    print("\nSOME CHECKS FAILED -- review above for details")
    sys.exit(1)

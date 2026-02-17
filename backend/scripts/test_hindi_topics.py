#!/usr/bin/env python3
"""
Deterministic test suite for Hindi topics.

Checks (no LLM calls):
1. All 5 Hindi topic profiles exist and have correct structure
2. Format validation uses VALID_FORMATS_HINDI (not Maths, English, or Science)
3. validate_question() with subject="Hindi" accepts Hindi formats
4. validate_question() with subject="Hindi" rejects Maths/English/Science formats
5. Alias resolution for Hindi topics
6. Learning objectives exist for all 5 topics
7. Context bank entries exist for all 5 topics
8. Topic constraints exist for all 5 topics
9. enforce_slot_counts uses Hindi formats for Hindi subject
10. backfill_format uses Hindi defaults for Hindi subject
11. QUESTION_SYSTEM_HINDI exists with correct content
12. Maths + English + Science regression guard
13. Slot plan validation for all 5 topics x {5, 10, 15, 20} = 20 combinations
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    TOPIC_PROFILES, _TOPIC_ALIASES, _SKILL_TAG_TO_SLOT,
    VALID_FORMATS, VALID_FORMATS_ENGLISH, VALID_FORMATS_SCIENCE, VALID_FORMATS_HINDI,
    get_valid_formats, get_default_format_by_slot,
    DEFAULT_FORMAT_BY_SLOT_TYPE, DEFAULT_FORMAT_BY_SLOT_TYPE_HINDI,
    SLOT_ORDER, get_topic_profile, build_worksheet_plan,
    _TOPIC_CONSTRAINTS,
    LEARNING_OBJECTIVES, TOPIC_CONTEXT_BANK,
    validate_question, enforce_slot_counts, backfill_format,
    QUESTION_SYSTEM_HINDI,
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


# ── Expected Hindi topics ──
HINDI_CLASS_3 = [
    "Varnamala (Class 3)", "Matras (Class 3)", "Shabd Rachna (Class 3)",
    "Vakya Rachna (Class 3)", "Kahani Lekhan (Class 3)",
]
ALL_HINDI = HINDI_CLASS_3
ALL_COUNTS = [5, 10, 15, 20]

print("=" * 70)
print("HINDI TOPIC VERIFICATION")
print("=" * 70)

# ===================================
# TEST 1: All 5 profiles exist
# ===================================
print("\n-- TEST 1: Hindi Topic Profiles Exist --")
for topic in ALL_HINDI:
    if topic in TOPIC_PROFILES:
        prof = TOPIC_PROFILES[topic]
        if prof.get("subject") == "Hindi":
            ok(f'"{topic}" exists with subject=Hindi')
        else:
            fail(f'"{topic}" exists but subject is not Hindi: {prof.get("subject")}')
    else:
        fail(f'"{topic}" NOT in TOPIC_PROFILES')

# ===================================
# TEST 2: Profile structure
# ===================================
print("\n-- TEST 2: Profile Structure --")
required_keys = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}
for topic in ALL_HINDI:
    prof = TOPIC_PROFILES.get(topic, {})
    missing = required_keys - set(prof.keys())
    if not missing:
        ok(f'"{topic}" has all required keys')
    else:
        fail(f'"{topic}" missing keys: {missing}')

# ===================================
# TEST 3: Skill tag to slot mapping
# ===================================
print("\n-- TEST 3: Skill Tags -> Slot Mapping (Hindi Formats) --")
for topic in ALL_HINDI:
    prof = TOPIC_PROFILES.get(topic, {})
    for item in prof.get("default_recipe", []):
        tag = item["skill_tag"]
        if tag in _SKILL_TAG_TO_SLOT:
            slot_type, fmt = _SKILL_TAG_TO_SLOT[tag]
            if fmt in VALID_FORMATS_HINDI.get(slot_type, set()):
                ok(f"{tag} -> ({slot_type}, {fmt})")
            else:
                fail(f"{tag} -> ({slot_type}, {fmt}) -- '{fmt}' not in VALID_FORMATS_HINDI['{slot_type}']")
        else:
            fail(f"{tag} -> NOT IN _SKILL_TAG_TO_SLOT")

# ===================================
# TEST 4: All 5 slot types covered
# ===================================
print("\n-- TEST 4: All 5 Slot Types Covered --")
for topic in ALL_HINDI:
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
# TEST 5: validate_question with Hindi subject
# ===================================
print("\n-- TEST 5: validate_question (Hindi) --")

# Hindi question should pass with Hindi formats
hindi_q = {
    "format": "pick_correct_hindi",
    "question_text": "इनमें से कौन सा स्वर है? (क) क (ख) आ (ग) ग (घ) म",
    "answer": "आ",
    "pictorial_elements": [],
}
issues = validate_question(hindi_q, "recognition", subject="Hindi")
if not issues:
    ok("Hindi recognition question with pick_correct_hindi: accepted")
else:
    fail(f"Hindi recognition question rejected: {issues}")

# Maths format should fail for Hindi
maths_q = {
    "format": "column_setup",
    "question_text": "इनमें से कौन सा स्वर है?",
    "answer": "आ",
    "pictorial_elements": [],
}
issues = validate_question(maths_q, "recognition", subject="Hindi")
if any("format" in i for i in issues):
    ok("Maths format 'column_setup' rejected for Hindi recognition")
else:
    fail("Maths format 'column_setup' should be rejected for Hindi")

# English format should fail for Hindi
eng_q = {
    "format": "identify_noun",
    "question_text": "इनमें से कौन सा स्वर है?",
    "answer": "आ",
    "pictorial_elements": [],
}
issues = validate_question(eng_q, "recognition", subject="Hindi")
if any("format" in i for i in issues):
    ok("English format 'identify_noun' rejected for Hindi recognition")
else:
    fail("English format 'identify_noun' should be rejected for Hindi")

# Science format should fail for Hindi
sci_q = {
    "format": "pick_correct_science",
    "question_text": "इनमें से कौन सा स्वर है?",
    "answer": "आ",
    "pictorial_elements": [],
}
issues = validate_question(sci_q, "recognition", subject="Hindi")
if any("format" in i for i in issues):
    ok("Science format 'pick_correct_science' rejected for Hindi recognition")
else:
    fail("Science format 'pick_correct_science' should be rejected for Hindi")

# Hindi error_detection should check error language
hindi_error_q = {
    "format": "error_spot_hindi",
    "question_text": "गलती ढूँढो: \"सेब\" में \"स\" एक स्वर है।",
    "answer": "\"स\" स्वर नहीं, व्यंजन है।",
    "skill_tag": "hin_varna_error",
    "pictorial_elements": [],
}
issues = validate_question(hindi_error_q, "error_detection", subject="Hindi")
if not issues:
    ok("Hindi error_detection with error language: accepted")
else:
    fail(f"Hindi error_detection rejected: {issues}")

# Hindi thinking should check reasoning language
hindi_think_q = {
    "format": "explain_meaning",
    "question_text": "स्वर और व्यंजन में क्या अंतर है? अपने शब्दों में समझाओ।",
    "answer": "स्वर वे ध्वनियाँ हैं जो बिना किसी अन्य वर्ण की सहायता से बोली जाती हैं।",
    "pictorial_elements": [],
}
issues = validate_question(hindi_think_q, "thinking", subject="Hindi")
if not issues:
    ok("Hindi thinking with reasoning language: accepted")
else:
    fail(f"Hindi thinking rejected: {issues}")

# Hindi question should reject pictorial_elements
hindi_pic_q = {
    "format": "pick_correct_hindi",
    "question_text": "इनमें से कौन सा व्यंजन है? (क) अ (ख) इ (ग) क (घ) उ",
    "answer": "क",
    "pictorial_elements": [{"type": "diagram"}],
}
issues = validate_question(hindi_pic_q, "recognition", subject="Hindi")
if any("pictorial" in i for i in issues):
    ok("Hindi question with pictorial_elements: correctly rejected")
else:
    fail("Hindi question with pictorial_elements should be rejected")

# ===================================
# TEST 6: get_valid_formats / get_default_format_by_slot
# ===================================
print("\n-- TEST 6: Subject-Aware Format Lookups --")
if get_valid_formats("Hindi") is VALID_FORMATS_HINDI:
    ok("get_valid_formats('Hindi') returns VALID_FORMATS_HINDI")
else:
    fail("get_valid_formats('Hindi') does not return VALID_FORMATS_HINDI")

if get_default_format_by_slot("Hindi") is DEFAULT_FORMAT_BY_SLOT_TYPE_HINDI:
    ok("get_default_format_by_slot('Hindi') returns Hindi defaults")
else:
    fail("get_default_format_by_slot('Hindi') wrong")

# Verify all 5 slot types have formats
for st in SLOT_ORDER:
    if st in VALID_FORMATS_HINDI and len(VALID_FORMATS_HINDI[st]) >= 1:
        ok(f"VALID_FORMATS_HINDI['{st}']: {len(VALID_FORMATS_HINDI[st])} formats")
    else:
        fail(f"VALID_FORMATS_HINDI['{st}'] missing or empty")

# ===================================
# TEST 7: Alias resolution
# ===================================
print("\n-- TEST 7: Hindi Alias Resolution --")
hindi_aliases = {
    "varnamala": "Varnamala (Class 3)",
    "class 3 varnamala": "Varnamala (Class 3)",
    "hindi alphabet": "Varnamala (Class 3)",
    "hindi varnamala": "Varnamala (Class 3)",
    "matras": "Matras (Class 3)",
    "class 3 matras": "Matras (Class 3)",
    "hindi matras": "Matras (Class 3)",
    "vowel signs": "Matras (Class 3)",
    "shabd rachna": "Shabd Rachna (Class 3)",
    "class 3 shabd rachna": "Shabd Rachna (Class 3)",
    "word formation hindi": "Shabd Rachna (Class 3)",
    "hindi word formation": "Shabd Rachna (Class 3)",
    "vakya rachna": "Vakya Rachna (Class 3)",
    "class 3 vakya rachna": "Vakya Rachna (Class 3)",
    "sentence formation hindi": "Vakya Rachna (Class 3)",
    "hindi sentence formation": "Vakya Rachna (Class 3)",
    "kahani lekhan": "Kahani Lekhan (Class 3)",
    "class 3 kahani lekhan": "Kahani Lekhan (Class 3)",
    "hindi story": "Kahani Lekhan (Class 3)",
    "hindi stories": "Kahani Lekhan (Class 3)",
    "hindi comprehension": "Kahani Lekhan (Class 3)",
}
for alias, expected in hindi_aliases.items():
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
for topic in ALL_HINDI:
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
for topic in ALL_HINDI:
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
for topic in ALL_HINDI:
    if topic in _TOPIC_CONSTRAINTS:
        constraint = _TOPIC_CONSTRAINTS[topic]
        if "NEVER" in constraint and "arithmetic" in constraint.lower():
            ok(f'"{topic}": has constraint with arithmetic prohibition ({len(constraint)} chars)')
        else:
            fail(f'"{topic}": constraint exists but missing arithmetic prohibition')
    else:
        fail(f'"{topic}": NO topic constraint')

# ===================================
# TEST 11: enforce_slot_counts with Hindi
# ===================================
print("\n-- TEST 11: enforce_slot_counts (Hindi) --")
hindi_questions = [
    {"id": 1, "slot_type": "recognition", "format": "pick_correct_hindi", "question_text": "test q about varnamala", "answer": "a"},
    {"id": 2, "slot_type": "application", "format": "fill_matra", "question_text": "fill in the matra for this word", "answer": "a"},
]
plan = ["recognition", "application", "representation"]
result = enforce_slot_counts(hindi_questions, plan, subject="Hindi")
if len(result) == 3:
    filler = result[2]
    if filler["format"] in VALID_FORMATS_HINDI.get("representation", set()):
        ok(f"enforce_slot_counts Hindi filler format: {filler['format']}")
    else:
        fail(f"enforce_slot_counts Hindi filler format wrong: {filler['format']}")
else:
    fail(f"enforce_slot_counts returned {len(result)} questions, expected 3")

# ===================================
# TEST 12: backfill_format with Hindi
# ===================================
print("\n-- TEST 12: backfill_format (Hindi) --")
q = {"slot_type": "recognition"}
backfill_format(q, {"slot_type": "recognition"}, subject="Hindi")
if q["format"] == "pick_correct_hindi":
    ok(f"backfill_format Hindi recognition default: {q['format']}")
else:
    fail(f"backfill_format Hindi recognition: {q['format']} (expected pick_correct_hindi)")

q2 = {"slot_type": "error_detection"}
backfill_format(q2, {"slot_type": "error_detection"}, subject="Hindi")
if q2["format"] == "error_spot_hindi":
    ok(f"backfill_format Hindi error_detection default: {q2['format']}")
else:
    fail(f"backfill_format Hindi error_detection: {q2['format']} (expected error_spot_hindi)")

q3 = {"slot_type": "thinking"}
backfill_format(q3, {"slot_type": "thinking"}, subject="Hindi")
if q3["format"] == "explain_meaning":
    ok(f"backfill_format Hindi thinking default: {q3['format']}")
else:
    fail(f"backfill_format Hindi thinking: {q3['format']} (expected explain_meaning)")

# ===================================
# TEST 13: QUESTION_SYSTEM_HINDI
# ===================================
print("\n-- TEST 13: QUESTION_SYSTEM_HINDI --")
if "Devanagari" in QUESTION_SYSTEM_HINDI:
    ok("QUESTION_SYSTEM_HINDI mentions Devanagari script")
else:
    fail("QUESTION_SYSTEM_HINDI missing Devanagari reference")

if "Indian" in QUESTION_SYSTEM_HINDI:
    ok("QUESTION_SYSTEM_HINDI mentions Indian contexts")
else:
    fail("QUESTION_SYSTEM_HINDI missing Indian context reference")

if "arithmetic" in QUESTION_SYSTEM_HINDI.lower():
    ok("QUESTION_SYSTEM_HINDI prohibits arithmetic")
else:
    fail("QUESTION_SYSTEM_HINDI missing arithmetic prohibition")

if "CBSE" in QUESTION_SYSTEM_HINDI:
    ok("QUESTION_SYSTEM_HINDI mentions CBSE curriculum")
else:
    fail("QUESTION_SYSTEM_HINDI missing CBSE reference")

# ===================================
# TEST 14: Slot plan validation (20 combinations)
# ===================================
print("\n-- TEST 14: Slot Plan Validation (5 x 4 = 20 combinations) --")
for topic in ALL_HINDI:
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

        # Check all formats are valid Hindi formats
        for d in plan:
            fmt = d.get("format", "")
            st = d.get("slot_type", "")
            if fmt and fmt not in VALID_FORMATS_HINDI.get(st, set()):
                errors.append(f"format '{fmt}' not in VALID_FORMATS_HINDI['{st}']")

        if errors:
            fail(f"{topic} [{count}q]: {errors}")
        else:
            ok(f"{topic} [{count}q]: {total}q -> R={slot_counts.get('recognition',0)} A={slot_counts.get('application',0)} Rep={slot_counts.get('representation',0)} ED={slot_counts.get('error_detection',0)} T={slot_counts.get('thinking',0)}")

# ===================================
# TEST 15: Maths + English + Science Regression Guard
# ===================================
print("\n-- TEST 15: Maths + English + Science Regression Guard --")
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

sci_recognition_q = {
    "format": "pick_correct_science",
    "question_text": "Which part of the plant makes food? (a) Root (b) Leaf (c) Stem (d) Flower",
    "answer": "Leaf",
    "pictorial_elements": [],
}
issues = validate_question(sci_recognition_q, "recognition", subject="Science")
if not issues:
    ok("Science pick_correct_science still accepted for subject='Science'")
else:
    fail(f"Science pick_correct_science rejected: {issues}")

# Verify format isolation: Hindi formats not in Maths, English, or Science
for st, fmts in VALID_FORMATS_HINDI.items():
    for fmt in fmts:
        if fmt in VALID_FORMATS.get(st, set()):
            fail(f"Hindi format '{fmt}' leaks into Maths VALID_FORMATS['{st}']")
        elif fmt in VALID_FORMATS_ENGLISH.get(st, set()):
            fail(f"Hindi format '{fmt}' leaks into English VALID_FORMATS_ENGLISH['{st}']")
        elif fmt in VALID_FORMATS_SCIENCE.get(st, set()):
            fail(f"Hindi format '{fmt}' leaks into Science VALID_FORMATS_SCIENCE['{st}']")
        else:
            ok(f"Hindi format '{fmt}' properly isolated from Maths/English/Science")

# ===================================
# RESULTS
# ===================================
print()
print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)

if FAIL == 0:
    print("\nALL CHECKS PASSED -- Hindi Engine is correctly configured")
else:
    print("\nSOME CHECKS FAILED -- review above for details")
    sys.exit(1)

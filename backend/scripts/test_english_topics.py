#!/usr/bin/env python3
"""
Deterministic test suite for English Language topics (Phase 7).

Checks (no LLM calls):
1. All 22 English topic profiles exist and have correct structure
2. Format validation uses VALID_FORMATS_ENGLISH (not Maths)
3. validate_question() with subject="English" accepts English formats
4. validate_question() with subject="English" rejects Maths formats
5. Alias resolution for English topics
6. Learning objectives exist for all 22 topics
7. Context bank entries exist for all 22 topics
8. Topic constraints exist for all 22 topics
9. Maths regression guard: Maths formats still work with default subject
10. enforce_slot_counts uses English formats for English subject
11. backfill_format uses English defaults for English subject
12. English answer normalizer works
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import Counter
from app.services.slot_engine import (
    TOPIC_PROFILES, _TOPIC_ALIASES, _SKILL_TAG_TO_SLOT,
    VALID_FORMATS, VALID_FORMATS_ENGLISH,
    get_valid_formats, get_default_format_by_slot,
    DEFAULT_FORMAT_BY_SLOT_TYPE, DEFAULT_FORMAT_BY_SLOT_TYPE_ENGLISH,
    SLOT_ORDER, get_topic_profile, build_worksheet_plan,
    _TOPIC_CONSTRAINTS,
    LEARNING_OBJECTIVES, TOPIC_CONTEXT_BANK,
    validate_question, enforce_slot_counts, backfill_format,
    normalize_text_answer, normalize_english_answers,
    QUESTION_SYSTEM_ENGLISH,
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


# ── Expected English topics ──
ENGLISH_CLASS_2 = [
    "Nouns (Class 2)", "Verbs (Class 2)", "Pronouns (Class 2)",
    "Sentences (Class 2)", "Rhyming Words (Class 2)", "Punctuation (Class 2)",
]
ENGLISH_CLASS_3 = [
    "Nouns (Class 3)", "Verbs (Class 3)", "Adjectives (Class 3)",
    "Pronouns (Class 3)", "Tenses (Class 3)", "Punctuation (Class 3)",
    "Vocabulary (Class 3)", "Reading Comprehension (Class 3)",
]
ENGLISH_CLASS_4 = [
    "Tenses (Class 4)", "Sentence Types (Class 4)", "Conjunctions (Class 4)",
    "Prepositions (Class 4)", "Adverbs (Class 4)", "Prefixes and Suffixes (Class 4)",
    "Vocabulary (Class 4)", "Reading Comprehension (Class 4)",
]
ALL_ENGLISH = ENGLISH_CLASS_2 + ENGLISH_CLASS_3 + ENGLISH_CLASS_4

print("=" * 70)
print("ENGLISH LANGUAGE TOPIC VERIFICATION — Phase 7")
print("=" * 70)

# ===================================
# TEST 1: All 22 profiles exist
# ===================================
print("\n-- TEST 1: English Topic Profiles Exist --")
for topic in ALL_ENGLISH:
    if topic in TOPIC_PROFILES:
        prof = TOPIC_PROFILES[topic]
        if prof.get("subject") == "English":
            ok(f'"{topic}" exists with subject=English')
        else:
            fail(f'"{topic}" exists but subject is not English: {prof.get("subject")}')
    else:
        fail(f'"{topic}" NOT in TOPIC_PROFILES')

# ===================================
# TEST 2: Profile structure
# ===================================
print("\n-- TEST 2: Profile Structure --")
required_keys = {"allowed_skill_tags", "allowed_slot_types", "disallowed_keywords", "default_recipe", "subject"}
for topic in ALL_ENGLISH:
    prof = TOPIC_PROFILES.get(topic, {})
    missing = required_keys - set(prof.keys())
    if not missing:
        ok(f'"{topic}" has all required keys')
    else:
        fail(f'"{topic}" missing keys: {missing}')

# ===================================
# TEST 3: Skill tag to slot mapping
# ===================================
print("\n-- TEST 3: Skill Tags -> Slot Mapping (English Formats) --")
for topic in ALL_ENGLISH:
    prof = TOPIC_PROFILES.get(topic, {})
    for item in prof.get("default_recipe", []):
        tag = item["skill_tag"]
        if tag in _SKILL_TAG_TO_SLOT:
            slot_type, fmt = _SKILL_TAG_TO_SLOT[tag]
            if fmt in VALID_FORMATS_ENGLISH.get(slot_type, set()):
                ok(f"{tag} -> ({slot_type}, {fmt})")
            else:
                fail(f"{tag} -> ({slot_type}, {fmt}) -- '{fmt}' not in VALID_FORMATS_ENGLISH['{slot_type}']")
        else:
            fail(f"{tag} -> NOT IN _SKILL_TAG_TO_SLOT")

# ===================================
# TEST 4: All 5 slot types covered
# ===================================
print("\n-- TEST 4: All 5 Slot Types Covered --")
for topic in ALL_ENGLISH:
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
# TEST 5: validate_question with English subject
# ===================================
print("\n-- TEST 5: validate_question (English vs Maths) --")

# English question should pass with English formats
eng_q = {
    "format": "identify_noun",
    "question_text": "Find the noun in this sentence: The cat sat on the mat.",
    "answer": "cat, mat",
    "pictorial_elements": [],
}
issues = validate_question(eng_q, "recognition", subject="English")
if not issues:
    ok("English recognition question with identify_noun: accepted")
else:
    fail(f"English recognition question rejected: {issues}")

# Maths format should fail for English
maths_q = {
    "format": "column_setup",
    "question_text": "Find the noun in this sentence: The cat sat on the mat.",
    "answer": "cat",
    "pictorial_elements": [],
}
issues = validate_question(maths_q, "recognition", subject="English")
if any("format" in i for i in issues):
    ok("Maths format 'column_setup' rejected for English recognition")
else:
    fail("Maths format 'column_setup' should be rejected for English")

# English error_detection should check grammar error language
eng_error_q = {
    "format": "error_spot_english",
    "question_text": "Find the mistake in this sentence: She go to school yesterday.",
    "answer": "She went to school yesterday.",
    "skill_tag": "eng_verb_error",
    "pictorial_elements": [],
}
issues = validate_question(eng_error_q, "error_detection", subject="English")
if not issues:
    ok("English error_detection with grammar error language: accepted")
else:
    fail(f"English error_detection rejected: {issues}")

# English thinking should check reasoning language
eng_think_q = {
    "format": "explain_why",
    "question_text": "Explain why we use a capital letter at the start of a sentence.",
    "answer": "Capital letters show the beginning of a new sentence.",
    "pictorial_elements": [],
}
issues = validate_question(eng_think_q, "thinking", subject="English")
if not issues:
    ok("English thinking with explain language: accepted")
else:
    fail(f"English thinking rejected: {issues}")

# ===================================
# TEST 6: get_valid_formats / get_default_format_by_slot
# ===================================
print("\n-- TEST 6: Subject-Aware Format Lookups --")
if get_valid_formats("English") is VALID_FORMATS_ENGLISH:
    ok("get_valid_formats('English') returns VALID_FORMATS_ENGLISH")
else:
    fail("get_valid_formats('English') does not return VALID_FORMATS_ENGLISH")

if get_valid_formats("Mathematics") is VALID_FORMATS:
    ok("get_valid_formats('Mathematics') returns VALID_FORMATS")
else:
    fail("get_valid_formats('Mathematics') does not return VALID_FORMATS")

if get_valid_formats() is VALID_FORMATS:
    ok("get_valid_formats() default returns VALID_FORMATS")
else:
    fail("get_valid_formats() default does not return VALID_FORMATS")

if get_default_format_by_slot("English") is DEFAULT_FORMAT_BY_SLOT_TYPE_ENGLISH:
    ok("get_default_format_by_slot('English') returns English defaults")
else:
    fail("get_default_format_by_slot('English') wrong")

if get_default_format_by_slot("Mathematics") is DEFAULT_FORMAT_BY_SLOT_TYPE:
    ok("get_default_format_by_slot('Mathematics') returns Maths defaults")
else:
    fail("get_default_format_by_slot('Mathematics') wrong")

# ===================================
# TEST 7: Alias resolution
# ===================================
print("\n-- TEST 7: English Alias Resolution --")
english_aliases = {
    "nouns": "Nouns (Class 3)",
    "verbs": "Verbs (Class 3)",
    "adjectives": "Adjectives (Class 3)",
    "pronouns": "Pronouns (Class 3)",
    "tenses": "Tenses (Class 3)",
    "punctuation": "Punctuation (Class 3)",
    "vocabulary": "Vocabulary (Class 3)",
    "reading comprehension": "Reading Comprehension (Class 3)",
    "comprehension": "Reading Comprehension (Class 3)",
    "conjunctions": "Conjunctions (Class 4)",
    "prepositions": "Prepositions (Class 4)",
    "adverbs": "Adverbs (Class 4)",
    "prefixes and suffixes": "Prefixes and Suffixes (Class 4)",
    "rhyming words": "Rhyming Words (Class 2)",
    "sentences": "Sentences (Class 2)",
    "class 2 nouns": "Nouns (Class 2)",
    "class 3 vocabulary": "Vocabulary (Class 3)",
    "class 4 tenses": "Tenses (Class 4)",
    "class 4 comprehension": "Reading Comprehension (Class 4)",
}
for alias, expected in english_aliases.items():
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
for topic in ALL_ENGLISH:
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
for topic in ALL_ENGLISH:
    if topic in TOPIC_CONTEXT_BANK:
        entries = TOPIC_CONTEXT_BANK[topic]
        if len(entries) >= 5:
            ok(f'"{topic}": {len(entries)} context entries')
        else:
            fail(f'"{topic}": only {len(entries)} entries (need 5+)')
    else:
        fail(f'"{topic}": NO context bank entries')

# ===================================
# TEST 10: Topic constraints
# ===================================
print("\n-- TEST 10: Topic Constraints --")
for topic in ALL_ENGLISH:
    if topic in _TOPIC_CONSTRAINTS:
        ok(f'"{topic}": has constraint ({len(_TOPIC_CONSTRAINTS[topic])} chars)')
    else:
        fail(f'"{topic}": NO topic constraint')

# ===================================
# TEST 11: enforce_slot_counts with English
# ===================================
print("\n-- TEST 11: enforce_slot_counts (English) --")
eng_questions = [
    {"id": 1, "slot_type": "recognition", "format": "identify_noun", "question_text": "test q", "answer": "a"},
    {"id": 2, "slot_type": "application", "format": "fill_in_blank", "question_text": "test q", "answer": "a"},
]
plan = ["recognition", "application", "representation"]
result = enforce_slot_counts(eng_questions, plan, subject="English")
if len(result) == 3:
    filler = result[2]
    if filler["format"] in VALID_FORMATS_ENGLISH.get("representation", set()):
        ok(f"enforce_slot_counts English filler format: {filler['format']}")
    else:
        fail(f"enforce_slot_counts English filler format wrong: {filler['format']}")
else:
    fail(f"enforce_slot_counts returned {len(result)} questions, expected 3")

# ===================================
# TEST 12: backfill_format with English
# ===================================
print("\n-- TEST 12: backfill_format (English) --")
q = {"slot_type": "recognition"}
backfill_format(q, {"slot_type": "recognition"}, subject="English")
if q["format"] == "pick_correct":
    ok(f"backfill_format English recognition default: {q['format']}")
else:
    fail(f"backfill_format English recognition: {q['format']} (expected pick_correct)")

q2 = {"slot_type": "error_detection"}
backfill_format(q2, {"slot_type": "error_detection"}, subject="English")
if q2["format"] == "error_spot_english":
    ok(f"backfill_format English error_detection default: {q2['format']}")
else:
    fail(f"backfill_format English error_detection: {q2['format']} (expected error_spot_english)")

# ===================================
# TEST 13: English answer normalizer
# ===================================
print("\n-- TEST 13: Answer Normalizers --")
if normalize_text_answer("  The cat SAT  on the  mat. ") == "the cat sat on the mat":
    ok("normalize_text_answer: strips, lowercases, collapses whitespace, removes trailing punct")
else:
    fail(f"normalize_text_answer unexpected: '{normalize_text_answer('  The cat SAT  on the  mat. ')}'")

test_questions = [
    {"id": 1, "answer": "  cat  ", "slot_type": "recognition"},
    {"id": 2, "answer": "", "slot_type": "application"},
    {"id": 3, "answer": "noun", "slot_type": "recognition"},
]
normalize_english_answers(test_questions)
if test_questions[0]["answer"] == "cat":
    ok("normalize_english_answers: strips whitespace")
else:
    fail(f"normalize_english_answers: expected 'cat', got '{test_questions[0]['answer']}'")

# ===================================
# TEST 14: QUESTION_SYSTEM_ENGLISH exists and differs from Maths
# ===================================
print("\n-- TEST 14: QUESTION_SYSTEM_ENGLISH --")
if "grammatically correct" in QUESTION_SYSTEM_ENGLISH:
    ok("QUESTION_SYSTEM_ENGLISH mentions grammatical correctness")
else:
    fail("QUESTION_SYSTEM_ENGLISH missing grammar reference")

if "Indian English" in QUESTION_SYSTEM_ENGLISH:
    ok("QUESTION_SYSTEM_ENGLISH mentions Indian English")
else:
    fail("QUESTION_SYSTEM_ENGLISH missing Indian English reference")

# ===================================
# TEST 15: Maths regression guard
# ===================================
print("\n-- TEST 15: Maths Regression Guard --")
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

issues2 = validate_question(maths_recognition_q, "recognition", subject="Mathematics")
if not issues2:
    ok("Maths column_setup still accepted for subject='Mathematics'")
else:
    fail(f"Maths column_setup rejected for Mathematics: {issues2}")

# ===================================
# RESULTS
# ===================================
print()
print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)

if FAIL == 0:
    print("\nALL CHECKS PASSED -- English Language Engine is correctly configured")
else:
    print("\nSOME CHECKS FAILED -- review above for details")
    sys.exit(1)

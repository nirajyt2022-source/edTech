#!/usr/bin/env python3
"""
Test the hardcoded CBSE syllabus endpoint logic.
Deterministic — no API calls, no DB required.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.syllabus import _CBSE_SYLLABUS, _SUBJECT_ALIASES

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


print("=" * 60)
print("TEST SUITE: CBSE Syllabus Hardcoded Data")
print("=" * 60)

# Section 1: All grades present
print("\n-- Section 1: Grade coverage --")
EXPECTED_GRADES = ["Class 1", "Class 2", "Class 3", "Class 4", "Class 5"]
for grade in EXPECTED_GRADES:
    if grade in _CBSE_SYLLABUS:
        record_pass(f"{grade} present")
    else:
        record_fail(f"{grade}", "missing from _CBSE_SYLLABUS")

# Section 2: Both Maths and English for each grade
print("\n-- Section 2: Subject coverage --")
for grade in EXPECTED_GRADES:
    if grade not in _CBSE_SYLLABUS:
        continue
    for subj in ["Mathematics", "English"]:
        if subj in _CBSE_SYLLABUS[grade]:
            count = len(_CBSE_SYLLABUS[grade][subj])
            record_pass(f"{grade} {subj}: {count} chapters")
        else:
            record_fail(f"{grade} {subj}", "missing")

# Section 3: Each chapter has required fields
print("\n-- Section 3: Chapter schema validation --")
for grade in EXPECTED_GRADES:
    if grade not in _CBSE_SYLLABUS:
        continue
    for subj, chapters in _CBSE_SYLLABUS[grade].items():
        for ch in chapters:
            label = f"{grade}/{subj}/{ch.get('title', '???')}"
            errs = []
            if "id" not in ch:
                errs.append("missing id")
            if "title" not in ch:
                errs.append("missing title")
            if "topics" not in ch:
                errs.append("missing topics")
            elif not ch["topics"]:
                errs.append("topics list is empty")
            if errs:
                record_fail(label, "; ".join(errs))
            else:
                record_pass(f"{label} ({len(ch['topics'])} topics)")

# Section 4: No duplicate chapter IDs within a grade/subject
print("\n-- Section 4: Unique chapter IDs --")
for grade in EXPECTED_GRADES:
    if grade not in _CBSE_SYLLABUS:
        continue
    for subj, chapters in _CBSE_SYLLABUS[grade].items():
        ids = [ch["id"] for ch in chapters]
        dupes = [x for x in ids if ids.count(x) > 1]
        if dupes:
            record_fail(f"{grade}/{subj} IDs", f"duplicates: {set(dupes)}")
        else:
            record_pass(f"{grade}/{subj} — all {len(ids)} IDs unique")

# Section 5: Subject aliases
print("\n-- Section 5: Subject aliases --")
for alias, canonical in _SUBJECT_ALIASES.items():
    record_pass(f"'{alias}' -> '{canonical}'")

# Check key aliases exist
for needed in ["maths", "math", "english"]:
    if needed not in _SUBJECT_ALIASES:
        record_fail(f"alias '{needed}'", "not found in _SUBJECT_ALIASES")

# Summary
print("\n" + "=" * 60)
print(f"TOTAL: {passed} passed, {failed} failed")
print("=" * 60)

if errors_list:
    print("\nFailed checks:")
    for e in errors_list:
        print(f"  {e}")

sys.exit(1 if failed > 0 else 0)

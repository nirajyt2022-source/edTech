#!/usr/bin/env python3
"""
Bulk audit: run build_slots() on every topic profile and check quality signals.

Usage:
    cd backend
    python scripts/bulk_audit.py
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.topic_profiles import TOPIC_PROFILES
from app.services.v3.slot_builder import build_slots


@dataclass
class AuditIssue:
    severity: str  # P0, P1, P2
    code: str
    detail: str


def _detect_subject(topic_name: str, profile: dict) -> str:
    """Infer subject from skill tags or topic name."""
    tags = profile.get("allowed_skill_tags", [])
    tag_str = " ".join(tags).lower()
    topic_lower = topic_name.lower()

    # --- Detect from skill tag prefixes ---
    if any(x in tag_str for x in ["add", "sub", "mult", "div", "frac", "dec", "num", "place_value",
                                   "c1_spatial", "c5_factors", "c5_hcflcm", "c5_percent"]):
        return "Maths"
    if any(x in tag_str for x in ["eng_", "noun", "verb", "tense", "pronoun", "adj"]):
        return "English"
    if any(x in tag_str for x in ["hin_", "hindi_", "vachan", "vilom", "varn", "matra"]):
        return "Hindi"
    if any(x in tag_str for x in ["sci_", "evs_", "animal", "plant", "water", "food", "body"]):
        return "EVS"
    if any(x in tag_str for x in ["comp_", "computer"]):
        return "Computer"
    if any(x in tag_str for x in ["health_"]):
        return "Health"
    if any(x in tag_str for x in ["gk_"]):
        return "GK"
    if any(x in tag_str for x in ["moral_"]):
        return "Moral Science"

    # --- Fallback: detect from topic name ---
    if any(x in topic_lower for x in ["addition", "subtraction", "multiplication", "division",
                                        "fraction", "decimal", "number", "shape", "time", "money",
                                        "measurement", "geometry", "pattern", "data", "symmetry",
                                        "perimeter", "area", "speed", "factor", "multiple",
                                        "hcf", "lcm", "percentage", "spatial"]):
        return "Maths"
    if any(x in topic_lower for x in ["noun", "verb", "tense", "pronoun", "adjective", "sentence",
                                        "vowel", "consonant", "grammar", "comprehension", "letter",
                                        "writing", "rhym", "phonic", "vocabulary", "article",
                                        "family words", "nature vocabulary"]):
        return "English"
    if any(x in topic_lower for x in ["वर्ण", "मात्रा", "वचन", "विलोम", "हिन्दी", "hindi",
                                        "संज्ञा", "सर्वनाम", "क्रिया", "लिंग", "पत्र", "संवाद",
                                        "varnamala", "shabd", "vakya", "kahani", "lekhan",
                                        "kaal", "anusvaar", "visarg", "muhavare", "paryayvachi",
                                        "samas", "samvad", "two letter", "three letter",
                                        "दो अक्षर", "तीन अक्षर"]):
        return "Hindi"
    if any(x in topic_lower for x in ["landmark", "continent", "ocean", "scientist", "festival",
                                        "sports", "constitution", "heritage", "space mission",
                                        "solar system basics", "current awareness",
                                        "national symbol", "environmental awareness"]):
        return "GK"
    if any(x in topic_lower for x in ["animal", "plant", "water", "weather", "food", "body",
                                        "shelter", "habitat", "season", "air", "soil"]):
        return "EVS"
    if any(x in topic_lower for x in ["computer", "keyboard", "mouse", "typing"]):
        return "Computer"
    if any(x in topic_lower for x in ["hygiene", "exercise", "balanced diet", "first aid", "safety"]):
        return "Health"
    if any(x in topic_lower for x in ["rhymes and poems"]):
        return "English"
    return "EVS"  # safe default


def _detect_grade(topic_name: str) -> int:
    """Extract grade from topic name like 'Addition (Class 3)'."""
    m = re.search(r"class\s*(\d)", topic_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\(c(\d)\)", topic_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 3  # default


def audit_topic(topic_name: str, profile: dict) -> list[AuditIssue]:
    """Run build_slots and check quality signals."""
    issues: list[AuditIssue] = []
    subject = _detect_subject(topic_name, profile)
    grade_num = _detect_grade(topic_name)
    grade_level = f"Class {grade_num}"
    language = "Hindi" if subject == "Hindi" else "English"

    try:
        output = build_slots("CBSE", grade_level, subject, topic_name, "medium", 10, "standard", language)
    except Exception as e:
        issues.append(AuditIssue("P0", "build_fails", f"build_slots crashed: {e}"))
        return issues

    slots = output.slots
    meta = output.worksheet_meta

    # === CHECK 1: No topic profile (all skill=general) ===
    all_general = all(s.skill_tag == "general" for s in slots)
    if all_general:
        issues.append(AuditIssue("P1", "no_topic_profile", "All 10 slots have skill_tag=general (no topic profile matched)"))

    # === CHECK 2: Word count limit in LLM instruction ===
    if grade_num <= 1:
        for s in slots:
            if "15 words" not in s.llm_instruction and "UNDER 15" not in s.llm_instruction:
                issues.append(AuditIssue("P1", "no_word_limit", f"Q{s.slot_number}: Class {grade_num} missing 15-word limit"))
                break
    elif grade_num <= 2:
        for s in slots:
            if "20 words" not in s.llm_instruction and "under 20" not in s.llm_instruction:
                issues.append(AuditIssue("P1", "no_word_limit", f"Q{s.slot_number}: Class {grade_num} missing 20-word limit"))
                break
    elif grade_num <= 3:
        for s in slots:
            if "30 words" not in s.llm_instruction and "under 30" not in s.llm_instruction:
                issues.append(AuditIssue("P1", "no_word_limit", f"Q{s.slot_number}: Class {grade_num} missing 30-word limit"))
                break

    # === CHECK 3: Maths slots have pre-computed numbers ===
    is_maths = subject.lower() in ("maths", "mathematics", "math")
    if is_maths:
        slots_with_numbers = sum(1 for s in slots if s.numbers)
        topic_lower = topic_name.lower()

        NON_ARITHMETIC_KEYWORDS = [
            "shape", "spatial", "symmetry", "geometry", "pattern",
            "data handling", "pictograph", "pie chart",
        ]
        SPECIALIZED_NUMBER_KEYWORDS = [
            "fraction", "decimal", "money", "measurement", "time",
            "perimeter", "area", "volume", "percentage", "hcf", "lcm",
            "speed", "number", "large number", "place value",
        ]

        is_non_arithmetic = any(kw in topic_lower for kw in NON_ARITHMETIC_KEYWORDS)
        is_specialized = any(kw in topic_lower for kw in SPECIALIZED_NUMBER_KEYWORDS)

        if is_non_arithmetic:
            pass  # No numbers needed — shapes, symmetry, etc.
        elif is_specialized and slots_with_numbers == 0:
            issues.append(AuditIssue("P2", "no_specialized_numbers",
                                     f"Maths topic could benefit from pre-computed {topic_lower.split('(')[0].strip()} values"))
        elif not is_non_arithmetic and not is_specialized and slots_with_numbers == 0:
            issues.append(AuditIssue("P1", "no_maths_numbers", "Core arithmetic topic has 0 pre-computed numbers"))
        elif slots_with_numbers < 5 and not is_non_arithmetic and not is_specialized:
            issues.append(AuditIssue("P2", "few_maths_numbers",
                                     f"Only {slots_with_numbers}/10 slots have pre-computed numbers"))

    # === CHECK 4: Answer diversity (maths) ===
    if is_maths:
        answers = [s.numbers["answer"] for s in slots if s.numbers and s.numbers.get("answer") is not None]
        if answers:
            counts = Counter(answers)
            max_repeat = max(counts.values())
            if max_repeat >= 3:
                issues.append(AuditIssue("P1", "answer_clustering",
                                         f"Answer {max(counts, key=counts.get)} repeats {max_repeat} times"))

    # === CHECK 5: Subtraction trivial differences ===
    if is_maths and "subtraction" in topic_name.lower():
        trivial = [s for s in slots if s.numbers and s.numbers.get("answer", 999) < 3]
        if trivial:
            issues.append(AuditIssue("P2", "trivial_subtraction",
                                     f"{len(trivial)} slots have trivial differences (<3)"))

    # === CHECK 6: Learning objectives present ===
    objectives = meta.get("learning_objectives", [])
    if not objectives or objectives == [f"Practice {topic_name}"]:
        issues.append(AuditIssue("P2", "generic_objectives",
                                 "Learning objectives are generic or missing"))

    # === CHECK 7: Question type variety ===
    q_types = Counter(s.question_type for s in slots)
    if len(q_types) < 3:
        issues.append(AuditIssue("P2", "low_type_variety",
                                 f"Only {len(q_types)} question types: {dict(q_types)}"))

    # === CHECK 8: Percentage answers are exact integers ===
    if "percent" in topic_name.lower() and is_maths:
        for s in slots:
            if s.numbers and s.numbers.get("operation") == "percentage":
                a, b = s.numbers["a"], s.numbers["b"]
                exact = a * b / 100
                if exact != int(exact):
                    issues.append(AuditIssue("P0", "percentage_rounding",
                                             f"Slot {s.slot_number}: {b}% of {a} = {exact}, not integer"))

    # === CHECK 9: "with borrow" pairs actually need borrowing ===
    # Only check pure subtraction topics (not "Addition and subtraction" combo topics)
    topic_lower_check = topic_name.lower()
    is_pure_subtraction = (
        "subtrac" in topic_lower_check
        and "addition" not in topic_lower_check
        and "add" not in topic_lower_check
        and "without" not in topic_lower_check
        and "no borrow" not in topic_lower_check
    )
    if "with borrow" in topic_lower_check or is_pure_subtraction:
        for s in slots:
            if s.numbers and s.numbers.get("a") is not None and s.numbers.get("b") is not None:
                a, b = s.numbers["a"], s.numbers["b"]
                if isinstance(a, int) and isinstance(b, int) and a > b:
                    sa = str(a).zfill(len(str(max(a, b))))
                    sb = str(b).zfill(len(str(max(a, b))))
                    needs_borrow = any(int(da) < int(db) for da, db in zip(reversed(sa), reversed(sb)))
                    if not needs_borrow:
                        issues.append(AuditIssue("P1", "no_borrow_in_borrow_topic",
                                                 f"Slot {s.slot_number}: {a}-{b} doesn't need borrowing"))

    # === CHECK 10: Common mistake doesn't contradict topic ===
    common_mistake = meta.get("common_mistake", "")
    if common_mistake:
        if "carry" in common_mistake.lower() and ("no carry" in topic_name.lower() or "without carry" in topic_name.lower()):
            issues.append(AuditIssue("P0", "contradicting_common_mistake",
                                     "common_mistake mentions 'carry' but topic is no-carry"))
        if "borrow" in common_mistake.lower() and ("no borrow" in topic_name.lower() or "without borrow" in topic_name.lower()):
            issues.append(AuditIssue("P0", "contradicting_common_mistake",
                                     "common_mistake mentions 'borrow' but topic is no-borrow"))

    return issues


def main():
    total = len(TOPIC_PROFILES)
    passed = 0
    failed = 0
    p0_count = 0
    p1_count = 0
    p2_count = 0
    all_issues: list[tuple[str, list[AuditIssue]]] = []

    for topic_name, profile in sorted(TOPIC_PROFILES.items()):
        issues = audit_topic(topic_name, profile)

        has_p0 = any(i.severity == "P0" for i in issues)
        has_p1 = any(i.severity == "P1" for i in issues)

        if has_p0 or has_p1:
            failed += 1
            status = "FAIL"
        else:
            passed += 1
            status = "PASS"

        for i in issues:
            if i.severity == "P0":
                p0_count += 1
            elif i.severity == "P1":
                p1_count += 1
            elif i.severity == "P2":
                p2_count += 1

        if issues:
            all_issues.append((topic_name, issues))
            issue_str = " | ".join(f"{i.severity}:{i.code}" for i in issues)
            print(f"  [{status}] {topic_name}: {issue_str}")
        else:
            print(f"  [PASS] {topic_name}")

    # Summary
    print("\n" + "=" * 70)
    print(f"BULK AUDIT SUMMARY: {passed}/{total} PASS, {failed}/{total} FAIL")
    print(f"  P0={p0_count}, P1={p1_count}, P2={p2_count}")
    print("=" * 70)

    # Group by issue code
    if all_issues:
        code_counts: dict[str, int] = {}
        for _, issues in all_issues:
            for i in issues:
                key = f"{i.severity}:{i.code}"
                code_counts[key] = code_counts.get(key, 0) + 1

        print("\nIssue breakdown:")
        for code, count in sorted(code_counts.items()):
            print(f"  {code}: {count} topics")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

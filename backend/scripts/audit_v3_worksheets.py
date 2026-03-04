#!/usr/bin/env python3
"""
V3 Slot Builder — 10-Worksheet Audit

Generates 10 worksheets using the v3 pipeline, saves full JSON output,
and prints a structured audit report.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai_client import get_openai_compat_client
from app.services.v3 import generate_worksheet_v3

TEST_CASES = [
    ("WS-01", "Class 1", "Maths", "Addition (single digit)", "easy", 10, "English"),
    ("WS-02", "Class 2", "English", "Nouns (common, proper, collective)", "medium", 10, "English"),
    ("WS-03", "Class 3", "Maths", "Fractions (half, one-fourth, three-fourths)", "medium", 10, "English"),
    ("WS-04", "Class 1", "Hindi", "वचन (एकवचन-बहुवचन)", "easy", 10, "Hindi"),
    ("WS-05", "Class 4", "Science", "Food and Digestion", "medium", 10, "English"),
    ("WS-06", "Class 3", "EVS", "Water (sources, conservation, cycle)", "easy", 10, "English"),
    ("WS-07", "Class 5", "Maths", "Decimals (place value, comparison)", "hard", 10, "English"),
    ("WS-08", "Class 2", "Maths", "Subtraction (2-digit without borrow)", "easy", 10, "English"),
    ("WS-09", "Class 4", "English", "Tenses (simple present, past, future)", "medium", 10, "English"),
    ("WS-10", "Class 5", "Hindi", "विशेषण (गुणवाचक, संख्यावाचक)", "medium", 10, "Hindi"),
]

_LLM_ISM_PATTERNS = [
    re.compile(r"\bHelp \w+ (?:figure out|solve this|solve|find|at the|with the|during)\b", re.I),
    re.compile(r"\bCan you (?:find|solve|figure out|help|tell)\b", re.I),
    re.compile(r"\bLet'?s (?:figure out|find out|solve|help|try)\b", re.I),
    re.compile(r"\bAs an AI\b", re.I),
    re.compile(r"\bHere'?s a\b", re.I),
]

_HINDI_TRANSLIT_WORDS = {
    "हेल्प", "फिगर", "आउट", "फाइंड", "सॉल्व", "लेट्स",
    "लोटस", "स्टार", "मून", "फ्लावर", "ट्री",
    "टेबल", "चेयर", "बुक", "बॉक्स",
    "कैट", "डॉग", "बर्ड", "फिश",
    "रेड", "ब्लू", "ग्रीन", "येलो", "पिंक", "ऑरेंज",
    "नंबर", "प्लस", "माइनस", "इक्वल",
}


def audit_worksheet(ws_id: str, data: dict, warnings: list[str], elapsed_ms: int, grade_str: str, subject: str) -> dict:
    issues = []
    questions = data.get("questions", [])
    subject_lower = subject.lower()

    # 1. Question count
    if len(questions) != 10:
        issues.append(f"Expected 10 questions, got {len(questions)}")

    # 2. Format diversity — check type distribution
    type_counts: dict[str, int] = {}
    for q in questions:
        qt = q.get("type", "unknown")
        type_counts[qt] = type_counts.get(qt, 0) + 1

    # 3. LLM-ism check
    llm_isms = 0
    llm_examples = []
    for q in questions:
        text = q.get("text", "")
        for pat in _LLM_ISM_PATTERNS:
            m = pat.search(text)
            if m:
                llm_isms += 1
                llm_examples.append(f"Q{q.get('id','?')}: \"{m.group()}...\"")
                break
    if llm_isms:
        issues.append(f"LLM-ism fillers: {llm_isms} questions ({'; '.join(llm_examples[:3])})")

    # 4. Hindi transliteration
    if subject_lower == "hindi":
        hindi_leaks = 0
        for q in questions:
            text = q.get("text", "")
            words = set(re.findall(r"[\u0900-\u097F]+", text))
            if words & _HINDI_TRANSLIT_WORDS:
                hindi_leaks += 1
        if hindi_leaks:
            issues.append(f"Hindi transliteration leakage: {hindi_leaks} questions")

    # 5. Class 1 arithmetic bounds
    if "1" in grade_str and subject_lower in ("maths", "mathematics"):
        big_answers = 0
        for q in questions:
            ans = q.get("correct_answer", "")
            try:
                val = int(str(ans).strip())
                if val > 20:
                    big_answers += 1
            except (ValueError, TypeError):
                pass
        if big_answers:
            issues.append(f"Class 1 arithmetic: {big_answers} answers > 20")

    # 6. MCQ option counts
    bad_mcq = 0
    for q in questions:
        if q.get("type") == "mcq":
            opts = q.get("options", [])
            if not opts or len(opts) != 4:
                bad_mcq += 1
    if bad_mcq:
        issues.append(f"MCQ option count wrong: {bad_mcq} questions")

    # 7. Empty text check
    empty = sum(1 for q in questions if not q.get("text") or len(q.get("text", "")) < 5)
    if empty:
        issues.append(f"Empty/too-short text: {empty} questions")

    # 8. Correct answer present
    missing_answer = sum(1 for q in questions if not q.get("correct_answer"))
    if missing_answer:
        issues.append(f"Missing correct_answer: {missing_answer} questions")

    # 9. Role diversity
    roles = set(q.get("role") for q in questions if q.get("role"))

    # 10. Visual data for maths topics that need it
    visual_count = sum(1 for q in questions if q.get("visual_type"))

    # 11. Difficulty distribution
    diff_counts: dict[str, int] = {}
    for q in questions:
        d = q.get("difficulty", "unknown")
        diff_counts[d] = diff_counts.get(d, 0) + 1

    # 12. Skill tag diversity
    skill_tags = set(q.get("skill_tag") for q in questions if q.get("skill_tag"))

    return {
        "ws_id": ws_id,
        "num_questions": len(questions),
        "elapsed_ms": elapsed_ms,
        "type_distribution": type_counts,
        "difficulty_distribution": diff_counts,
        "roles": sorted(roles),
        "skill_tags": sorted(skill_tags),
        "visual_count": visual_count,
        "warning_count": len(warnings),
        "issues": issues,
        "questions": questions,
        "title": data.get("title", ""),
        "skill_focus": data.get("skill_focus", ""),
        "common_mistake": data.get("common_mistake", ""),
        "parent_tip": data.get("parent_tip", ""),
        "learning_objectives": data.get("learning_objectives", []),
    }


async def run_audit():
    print("=" * 70)
    print("  V3 SLOT BUILDER — 10-WORKSHEET AUDIT")
    print("=" * 70)

    client = get_openai_compat_client()
    results = []

    for ws_id, grade, subject, topic, diff, nq, lang in TEST_CASES:
        print(f"\n{'─' * 60}")
        print(f"  {ws_id}: {grade} | {subject} | {topic} | {diff} | {lang}")
        print(f"{'─' * 60}")

        try:
            data, elapsed_ms, warnings = await generate_worksheet_v3(
                client=client,
                board="CBSE",
                grade_level=grade,
                subject=subject,
                topic=topic,
                difficulty=diff,
                num_questions=nq,
                language=lang,
            )
            audit = audit_worksheet(ws_id, data, warnings, elapsed_ms, grade, subject)
            results.append(audit)

            status = "PASS" if not audit["issues"] else "ISSUES"
            print(f"  Status: {status} | Qs: {audit['num_questions']} | Time: {elapsed_ms}ms")
            print(f"  Types: {audit['type_distribution']}")
            print(f"  Difficulty: {audit['difficulty_distribution']}")
            print(f"  Roles: {audit['roles']}")
            print(f"  Skills: {audit['skill_tags']}")
            print(f"  Visuals: {audit['visual_count']}")
            if warnings:
                print(f"  Warnings ({len(warnings)}): {warnings[:3]}")
            if audit["issues"]:
                for issue in audit["issues"]:
                    print(f"  ❌ {issue}")
            else:
                print("  ✅ All checks passed")

            # Print sample questions
            print(f"\n  Sample questions:")
            for q in audit["questions"][:3]:
                print(f"    [{q.get('type','?')}|{q.get('role','?')}|{q.get('difficulty','?')}] {q.get('text','')[:80]}")
                if q.get("correct_answer"):
                    print(f"      Answer: {q['correct_answer']}")

        except Exception as exc:
            print(f"  ❌ GENERATION FAILED: {exc}")
            traceback.print_exc()
            results.append({
                "ws_id": ws_id,
                "num_questions": 0,
                "elapsed_ms": 0,
                "type_distribution": {},
                "difficulty_distribution": {},
                "roles": [],
                "skill_tags": [],
                "visual_count": 0,
                "warning_count": 0,
                "issues": [f"Generation failed: {exc}"],
                "questions": [],
                "title": "",
                "skill_focus": "",
                "common_mistake": "",
                "parent_tip": "",
                "learning_objectives": [],
            })

    # Summary
    print("\n" + "=" * 70)
    print("  AUDIT SUMMARY")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for r in results if not r["issues"])
    failed = sum(1 for r in results if r["issues"])
    total_issues = sum(len(r["issues"]) for r in results)

    print(f"\n  Total: {total} | Passed: {passed} | Issues: {failed}")
    print(f"  Total issues: {total_issues}")

    times = [r["elapsed_ms"] for r in results if r["elapsed_ms"] > 0]
    if times:
        print(f"  Generation time: min={min(times)}ms, max={max(times)}ms, avg={sum(times)//len(times)}ms")

    # Save full output
    out_path = os.path.join(os.path.dirname(__file__), "..", "artifacts", "v3_audit_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Full results saved to: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_audit())

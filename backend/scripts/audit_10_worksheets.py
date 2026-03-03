#!/usr/bin/env python3
"""
10-Worksheet Audit Script — Post-Fix Re-Audit

Generates 10 worksheets across subjects/grades, then prints a structured
audit report covering:
  - Generation success/failure
  - quality_score & verdict population
  - Format drift (type vs format mismatch)
  - Topic drift false positives
  - Hindi transliteration leakage
  - LLM-ism filler leakage
  - Class 1 arithmetic bounds
  - Science subject contamination
  - Sentence structure variety
  - MCQ option count
  - Fallback bank activations
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback

# Ensure backend/ is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai_client import get_openai_compat_client
from app.services.worksheet_generator import generate_worksheet

# ── 10 test cases ──────────────────────────────────────────────────────────

TEST_CASES = [
    # (id, grade_level, subject, topic, difficulty, num_questions, language)
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

# ── Hindi transliteration blocklist (same as quality_reviewer) ─────────────

_HINDI_TRANSLIT_WORDS = {
    "हेल्प", "फिगर", "आउट", "फाइंड", "सॉल्व", "लेट्स",
    "लोटस", "सन", "स्टार", "मून", "फ्लावर", "ट्री",
    "टेबल", "चेयर", "बुक", "पेन", "बैग", "बॉक्स",
    "कैट", "डॉग", "बर्ड", "फिश",
    "रेड", "ब्लू", "ग्रीन", "येलो", "पिंक", "ऑरेंज",
    "नंबर", "प्लस", "माइनस", "इक्वल",
}

_LLM_ISM_PATTERNS = [
    re.compile(r"\bHelp \w+ (?:figure out|solve this|solve|find|at the|with the|during)\b", re.I),
    re.compile(r"\bCan you (?:find|solve|figure out|help|tell)\b", re.I),
    re.compile(r"\bLet'?s (?:figure out|find out|solve|help|try)\b", re.I),
    re.compile(r"\bAs an AI\b", re.I),
    re.compile(r"\bHere'?s a\b", re.I),
]


def audit_worksheet(ws_id: str, data: dict, warnings: list[str], elapsed_ms: int) -> dict:
    """Run all audit checks on a generated worksheet."""
    issues = []
    questions = data.get("questions", [])

    # 1. quality_score populated?
    qs = data.get("_quality_score")
    if qs is None:
        issues.append("quality_score=None (not populated)")

    # 2. verdict populated?
    verdict = data.get("_release_verdict", "")
    if not verdict:
        issues.append("verdict='' (not populated)")

    # 3. Format drift — check each question
    format_drifts = 0
    for q in questions:
        fmt = q.get("format", "")
        qtype = q.get("type", "")
        if fmt == "other" and qtype != "other":
            format_drifts += 1
    if format_drifts:
        issues.append(f"format drift: {format_drifts} questions have format='other'")

    # 4. Topic drift — only flag if verdict is blocked due to topic drift
    # Cosmetic topic drift warnings on Maths are informational, not issues
    if verdict == "blocked":
        topic_drift_blocks = [w for w in warnings if "topic drift" in w.lower() and "BLOCK" in w]
        if topic_drift_blocks:
            issues.append(f"topic drift BLOCKED: {len(topic_drift_blocks)}")

    # 5. Hindi transliteration check
    hindi_leaks = 0
    for q in questions:
        text = q.get("question_text", "") or q.get("text", "")
        for word in _HINDI_TRANSLIT_WORDS:
            if word in text:
                hindi_leaks += 1
                break
    if hindi_leaks:
        issues.append(f"Hindi transliteration leakage: {hindi_leaks} questions")

    # 6. LLM-ism check
    llm_isms = 0
    for q in questions:
        text = q.get("question_text", "") or q.get("text", "")
        for pat in _LLM_ISM_PATTERNS:
            if pat.search(text):
                llm_isms += 1
                break
    if llm_isms:
        issues.append(f"LLM-ism fillers found: {llm_isms} questions")

    # 7. Class 1 arithmetic bounds
    grade_str = data.get("grade_level", "") or ""
    subject = (data.get("subject", "") or "").lower()
    if "1" in grade_str and subject in ("maths", "mathematics"):
        big_answers = 0
        for q in questions:
            ans = q.get("answer") or q.get("correct_answer", "")
            try:
                val = int(str(ans).strip())
                if val > 18:
                    big_answers += 1
            except (ValueError, TypeError):
                pass
        if big_answers:
            issues.append(f"Class 1 arithmetic: {big_answers} answers > 18")

    # 8. Science contamination (pure arithmetic in science questions)
    if subject in ("science", "evs"):
        sci_math = 0
        for q in questions:
            text = (q.get("question_text", "") or q.get("text", "")).lower()
            ans = str(q.get("answer") or q.get("correct_answer", "")).strip()
            if (re.search(r"how many|total|in all|altogether", text)
                    and ans.isdigit()
                    and not re.search(r"species|type|kind|name|organ|part|group|nutrient|vitamin", text)):
                sci_math += 1
        if sci_math:
            issues.append(f"Science contamination: {sci_math} pure arithmetic questions")

    # 9. Sentence structure variety
    structures = set()
    for q in questions:
        text = q.get("question_text", "") or q.get("text", "")
        if text.endswith("?"):
            structures.add("question")
        elif re.match(r"^(Find|Write|Fill|Complete|Match|Circle|Choose|List|Name|Identify|Draw)", text):
            structures.add("imperative")
        elif re.search(r"\b(has|had|have|went|goes|buys|bought|gives|gave)\b", text):
            structures.add("contextual")
        elif re.search(r"\b(correct|wrong|error|mistake)\b", text, re.I):
            structures.add("error_check")
        elif "___" in text or "___ " in text:
            structures.add("fill_in")
        else:
            structures.add("other")
    if len(structures) < 2:
        issues.append(f"Sentence monotony: only {len(structures)} structure type(s)")

    # 10. MCQ option counts
    bad_mcq = 0
    for q in questions:
        if q.get("type") == "mcq" or q.get("format") == "mcq":
            opts = q.get("options", [])
            if isinstance(opts, list) and len(opts) != 4:
                bad_mcq += 1
    if bad_mcq:
        issues.append(f"MCQ option count wrong: {bad_mcq} questions don't have 4 options")

    # 11. Fallback bank activations
    fallbacks = [q for q in questions if q.get("is_fallback")]
    needs_regen = [q for q in questions if q.get("_needs_regen")]

    # 12. _needs_regen still present (should be 0 after fallback bank)
    if needs_regen:
        issues.append(f"_needs_regen still present: {len(needs_regen)} questions")

    return {
        "ws_id": ws_id,
        "num_questions": len(questions),
        "quality_score": qs,
        "verdict": verdict,
        "elapsed_ms": elapsed_ms,
        "fallback_count": len(fallbacks),
        "needs_regen_count": len(needs_regen),
        "issues": issues,
        "warning_count": len(warnings),
    }


def main():
    print("=" * 70)
    print("  10-WORKSHEET AUDIT — Post-Fix Re-Audit")
    print("=" * 70)
    print()

    client = get_openai_compat_client()
    results = []

    for ws_id, grade, subject, topic, diff, nq, lang in TEST_CASES:
        print(f"\n{'─' * 60}")
        print(f"  {ws_id}: {grade} | {subject} | {topic} | {diff} | {lang}")
        print(f"{'─' * 60}")

        try:
            data, elapsed_ms, warnings = generate_worksheet(
                client=client,
                board="CBSE",
                grade_level=grade,
                subject=subject,
                topic=topic,
                difficulty=diff,
                num_questions=nq,
                language=lang,
            )
            audit = audit_worksheet(ws_id, data, warnings, elapsed_ms)
            results.append(audit)

            status = "PASS" if not audit["issues"] else "ISSUES"
            print(f"  Status: {status} | Questions: {audit['num_questions']} | "
                  f"Score: {audit['quality_score']} | Verdict: {audit['verdict']} | "
                  f"Time: {elapsed_ms}ms")
            if audit["fallback_count"]:
                print(f"  Fallback bank activations: {audit['fallback_count']}")
            if audit["issues"]:
                for issue in audit["issues"]:
                    print(f"  ❌ {issue}")
            else:
                print(f"  ✅ All checks passed")

        except Exception as exc:
            print(f"  ❌ GENERATION FAILED: {exc}")
            traceback.print_exc()
            results.append({
                "ws_id": ws_id,
                "num_questions": 0,
                "quality_score": None,
                "verdict": "FAILED",
                "elapsed_ms": 0,
                "fallback_count": 0,
                "needs_regen_count": 0,
                "issues": [f"Generation failed: {exc}"],
                "warning_count": 0,
            })

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  AUDIT SUMMARY")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for r in results if not r["issues"])
    failed_gen = sum(1 for r in results if r["verdict"] == "FAILED")
    total_issues = sum(len(r["issues"]) for r in results)
    total_fallbacks = sum(r["fallback_count"] for r in results)
    total_needs_regen = sum(r["needs_regen_count"] for r in results)

    print(f"\n  Worksheets generated: {total - failed_gen}/{total}")
    print(f"  Clean passes:        {passed}/{total}")
    print(f"  Total issues:        {total_issues}")
    print(f"  Fallback activations: {total_fallbacks}")
    print(f"  Residual _needs_regen: {total_needs_regen}")

    # Per-check summary
    all_issue_types: dict[str, int] = {}
    for r in results:
        for issue in r["issues"]:
            key = issue.split(":")[0]
            all_issue_types[key] = all_issue_types.get(key, 0) + 1

    if all_issue_types:
        print(f"\n  Issue breakdown:")
        for itype, count in sorted(all_issue_types.items(), key=lambda x: -x[1]):
            print(f"    {count}x  {itype}")

    # Quality scores
    scores = [r["quality_score"] for r in results if r["quality_score"] is not None]
    if scores:
        print(f"\n  Quality scores: min={min(scores):.1f}, max={max(scores):.1f}, "
              f"avg={sum(scores)/len(scores):.1f}")

    # Verdicts
    verdicts = {}
    for r in results:
        v = r["verdict"] or "empty"
        verdicts[v] = verdicts.get(v, 0) + 1
    print(f"  Verdicts: {verdicts}")

    print(f"\n{'=' * 70}")
    if total_issues == 0:
        print("  🎯 ZERO ISSUES — All 10 worksheets pass audit!")
    else:
        print(f"  ⚠️  {total_issues} issues found across {total - passed} worksheets")
    print(f"{'=' * 70}\n")

    # Save detailed JSON
    out_path = os.path.join(os.path.dirname(__file__), "..", "artifacts", "audit_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Detailed results saved to: {out_path}")


if __name__ == "__main__":
    main()

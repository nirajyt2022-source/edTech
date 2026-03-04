"""Deep 3-persona audit — captures full question texts for qualitative review."""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai_client import get_openai_compat_client
from app.services.worksheet_generator import generate_worksheet

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

client = get_openai_compat_client()
all_ws = []

for ws_id, grade, subject, topic, diff, nq, lang in TEST_CASES:
    print(f"Generating {ws_id}: {grade} {subject} — {topic}...", flush=True)
    try:
        data, ms, warnings = generate_worksheet(
            client=client, board="CBSE", grade_level=grade,
            subject=subject, topic=topic, difficulty=diff,
            num_questions=nq, language=lang,
        )
        qs = []
        for q in data.get("questions", []):
            qs.append({
                "id": q.get("id"),
                "type": q.get("type"),
                "format": q.get("format"),
                "text": q.get("question_text") or q.get("text", ""),
                "answer": str(q.get("correct_answer") or q.get("answer", "")),
                "options": q.get("options"),
                "difficulty": q.get("difficulty"),
                "slot_type": q.get("slot_type"),
                "skill_tag": q.get("skill_tag"),
                "explanation": (q.get("explanation") or "")[:200],
                "hint": q.get("hint"),
                "is_fallback": q.get("is_fallback", False),
                "_needs_regen": q.get("_needs_regen", False),
            })
        all_ws.append({
            "ws_id": ws_id, "grade": grade, "subject": subject,
            "topic": topic, "difficulty": diff, "language": lang,
            "quality_score": data.get("_quality_score"),
            "verdict": data.get("_release_verdict"),
            "elapsed_ms": ms,
            "question_count": len(qs),
            "questions": qs,
            "warning_count": len(warnings),
            "warnings_sample": [w for w in warnings if not w.startswith("[quality_reviewer] Q")][:10],
        })
        print(f"  OK — {len(qs)}q, score={data.get('_quality_score')}, verdict={data.get('_release_verdict')}")
    except Exception as exc:
        print(f"  FAILED: {exc}")
        traceback.print_exc()
        all_ws.append({"ws_id": ws_id, "error": str(exc)})

out = os.path.join(os.path.dirname(__file__), "..", "artifacts", "deep_audit.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(all_ws, f, indent=2, ensure_ascii=False)
print(f"\nSaved to {out}")

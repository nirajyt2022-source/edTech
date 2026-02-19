"""
Targeted retest for Health Classes 3-5 (9 topics).
These failed in the main audit only because the JWT expired mid-run (~30 min mark).

Usage:
    cd backend
    python scripts/retest_health.py <fresh_auth_token>
"""
import json
import sys
import time

import requests

PROD_API_BASE = "https://edtech-production-c7ec.up.railway.app"

HEALTH_RETEST = [
    ("Health", "Class 3", "Balanced Diet (Class 3)"),
    ("Health", "Class 3", "Team Sports Rules (Class 3)"),
    ("Health", "Class 3", "Safety at Play (Class 3)"),
    ("Health", "Class 4", "First Aid Basics (Class 4)"),
    ("Health", "Class 4", "Yoga Introduction (Class 4)"),
    ("Health", "Class 4", "Importance of Sleep (Class 4)"),
    ("Health", "Class 5", "Fitness and Stamina (Class 5)"),
    ("Health", "Class 5", "Nutrition Labels Reading (Class 5)"),
    ("Health", "Class 5", "Mental Health Awareness (Class 5)"),
]

if len(sys.argv) < 2:
    print("Usage: python scripts/retest_health.py <auth_token>")
    sys.exit(1)

auth_token = sys.argv[1]
results = []

print(f"Retesting {len(HEALTH_RETEST)} Health topics against {PROD_API_BASE}\n")

for subject, grade, topic in HEALTH_RETEST:
    try:
        r = requests.post(
            f"{PROD_API_BASE}/api/v1/worksheets/generate",
            json={
                "board": "CBSE",
                "grade_level": grade,
                "subject": subject,
                "topic": topic,
                "difficulty": "medium",
                "num_questions": 3,
                "language": "English",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=45,
        )
        if r.status_code == 200:
            data = r.json()
            qs = data.get("questions") or data.get("worksheet", {}).get("questions", [])
            status = "✅ ok"
            print(f"{status} | {subject} {grade} — {topic}")
            print(f"       {len(qs)} questions generated")
            results.append({"topic": topic, "grade": grade, "status": "ok", "questions": len(qs)})
        else:
            status = f"❌ {r.status_code}"
            print(f"{status} | {subject} {grade} — {topic}")
            print(f"       {r.text[:120]}")
            results.append({"topic": topic, "grade": grade, "status": f"error_{r.status_code}"})
    except Exception as exc:
        print(f"❌ EXCEPTION | {subject} {grade} — {topic}: {exc}")
        results.append({"topic": topic, "grade": grade, "status": "exception", "error": str(exc)})

    time.sleep(1.5)

ok  = sum(1 for r in results if r["status"] == "ok")
fail = len(results) - ok
print(f"\n{'='*50}")
print(f"Retest complete: {ok}/{len(results)} passed, {fail} failed")

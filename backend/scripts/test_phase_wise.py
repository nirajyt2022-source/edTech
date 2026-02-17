#!/usr/bin/env python3
"""
Master regression runner — runs all phase tests in order.
Use this as your CI gate before every Railway deploy.

Run: cd backend && python scripts/test_phase_wise.py
"""
import subprocess, sys, os

SCRIPTS = [
    ("Grade/topic resolution (from previous session)",
     "scripts/test_grade_topic_resolution.py"),
    ("Subject×topic resolution (new)",
     "scripts/test_subject_topic_resolution.py"),
]

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
all_pass = True

for name, script in SCRIPTS:
    print(f"\n{'='*60}")
    print(f"▶ {name}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"\n❌ FAILED: {script}")
        all_pass = False
    else:
        print(f"✅ PASSED: {script}")

print(f"\n{'='*60}")
print("OVERALL:", "✅ ALL PHASES PASS — safe to deploy" if all_pass else "❌ FAILURES — do not deploy")
print("="*60)
sys.exit(0 if all_pass else 1)

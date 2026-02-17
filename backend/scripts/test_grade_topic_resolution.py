#!/usr/bin/env python3
"""
Grade-topic resolution regression test.
Validates that every frontend topic string resolves to the CORRECT grade-level profile
with no cross-grade contamination.

Run:
    cd backend
    python scripts/test_grade_topic_resolution.py

Must print: ALL PASS with 0 failures.
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.slot_engine import (
    get_topic_profile, TOPIC_PROFILES, _TOPIC_ALIASES, build_worksheet_plan
)

PASS = FAIL = WARN = 0

def ok(msg):
    global PASS; PASS += 1
    print(f"  \u2705 {msg}")

def fail(msg):
    global FAIL; FAIL += 1
    print(f"  \u274c {msg}")

def warn(msg):
    global WARN; WARN += 1
    print(f"  \u26a0\ufe0f  {msg}")

def resolve(topic):
    p = get_topic_profile(topic)
    if not p: return None
    for k, v in TOPIC_PROFILES.items():
        if v is p: return k
    return None

def carry_tags(topic):
    p = get_topic_profile(topic)
    if not p: return set()
    bad = {"column_add_with_carry", "column_sub_with_borrow"}
    return bad & set(p.get("allowed_skill_tags", []))

def plan_carry_tags(topic):
    try:
        plan = build_worksheet_plan(10, topic=topic)
        bad = {"column_add_with_carry", "column_sub_with_borrow"}
        return bad & {d.get("skill_tag","") for d in plan}
    except Exception:
        return set()

# ════════════════════════════════════════
# 1. BUG REPRODUCTION — the exact topic from the broken JSON
# ════════════════════════════════════════
print("\n── TEST 1: Bug Reproduction (exact JSON topic) ──")

canon = resolve("Addition and subtraction (up to 20)")
if canon == "Addition up to 20 (Class 1)":
    ok(f'"Addition and subtraction (up to 20)" \u2192 "{canon}"')
else:
    fail(f'"Addition and subtraction (up to 20)" \u2192 "{canon}" (expected "Addition up to 20 (Class 1)")')

bad = carry_tags("Addition and subtraction (up to 20)")
if not bad:
    ok("No carry/borrow tags in resolved profile")
else:
    fail(f"Carry tags found: {bad} \u2014 Class 3 profile leaked in!")

bad_plan = plan_carry_tags("Addition up to 20 (Class 1)")
if not bad_plan:
    ok("build_worksheet_plan(10, 'Addition up to 20 (Class 1)') \u2014 no carry tags")
else:
    fail(f"Plan has carry tags: {bad_plan}")

# ════════════════════════════════════════
# 2. ALL FRONTEND MATHS TOPICS BY GRADE
# ════════════════════════════════════════
print("\n── TEST 2: All Maths Frontend Topics ──")

MATHS = {
    1: [
        ("Numbers 1 to 50 (Class 1)",        "Numbers 1 to 50 (Class 1)"),
        ("Numbers 51 to 100 (Class 1)",       "Numbers 51 to 100 (Class 1)"),
        ("Addition up to 20 (Class 1)",       "Addition up to 20 (Class 1)"),
        ("Subtraction within 20 (Class 1)",   "Subtraction within 20 (Class 1)"),
        ("Basic Shapes (Class 1)",            "Basic Shapes (Class 1)"),
        ("Measurement (Class 1)",             "Measurement (Class 1)"),
        ("Time (Class 1)",                    "Time (Class 1)"),
        ("Money (Class 1)",                   "Money (Class 1)"),
    ],
    2: [
        ("Numbers up to 1000 (Class 2)",      "Numbers up to 1000 (Class 2)"),
        ("Addition (2-digit with carry)",      "Addition (2-digit with carry)"),
        ("Subtraction (2-digit with borrow)",  "Subtraction (2-digit with borrow)"),
        ("Multiplication (tables 2-5)",        "Multiplication (tables 2-5)"),
        ("Division (sharing equally)",         "Division (sharing equally)"),
    ],
    3: [
        ("Addition (carries)",                 "Addition (carries)"),
        ("Subtraction (borrowing)",            "Subtraction (borrowing)"),
        ("Addition and subtraction (3-digit)", "Addition and subtraction (3-digit)"),
        ("Multiplication (tables 2-10)",       "Multiplication (tables 2-10)"),
        ("Numbers up to 10000",                "Numbers up to 10000"),
        ("Fractions",                          "Fractions"),
    ],
    4: [
        ("Large numbers (up to 1,00,000)",     "Large numbers (up to 1,00,000)"),
        ("Addition and subtraction (5-digit)", "Addition and subtraction (5-digit)"),
        ("Multiplication (3-digit \u00d7 2-digit)", "Multiplication (3-digit \u00d7 2-digit)"),
    ],
    5: [
        ("Numbers up to 10 lakh (Class 5)",    "Numbers up to 10 lakh (Class 5)"),
        ("HCF and LCM (Class 5)",              "HCF and LCM (Class 5)"),
        ("Percentage (Class 5)",               "Percentage (Class 5)"),
    ],
}

for grade, topics in MATHS.items():
    for topic, expected_canon in topics:
        canon = resolve(topic)
        if canon == expected_canon:
            ok(f"Class {grade}: \"{topic}\"")
        elif canon is None:
            fail(f"Class {grade}: \"{topic}\" \u2192 NO MATCH (expected \"{expected_canon}\")")
        else:
            fail(f"Class {grade}: \"{topic}\" \u2192 \"{canon}\" (expected \"{expected_canon}\")")

# ════════════════════════════════════════
# 3. GRADE CONTAMINATION — Class N topics must never resolve to wrong grade
# ════════════════════════════════════════
print("\n── TEST 3: No Grade Contamination ──")

all_class_topics = [
    t for t in TOPIC_PROFILES.keys() if re.search(r"Class \d", t)
]

for topic in all_class_topics:
    incoming_class = re.search(r"Class (\d)", topic)
    if not incoming_class:
        continue
    canon = resolve(topic)
    if canon is None:
        fail(f'"{topic}" \u2192 NO MATCH')
        continue
    canon_class = re.search(r"Class (\d)", canon)
    if canon_class and canon_class.group(1) != incoming_class.group(1):
        fail(f'"{topic}" \u2192 "{canon}" \u2014 CLASS MISMATCH (incoming={incoming_class.group(1)} resolved={canon_class.group(1)})')
    else:
        ok(f'"{topic}" \u2192 "{canon}" \u2713')

# ════════════════════════════════════════
# 4. ADVERSARIAL STRINGS — variants the API might receive
# ════════════════════════════════════════
print("\n── TEST 4: Adversarial Topic Strings ──")

ADVERSARIAL = [
    ("addition and subtraction (up to 20)",  "Addition up to 20 (Class 1)"),
    ("ADDITION AND SUBTRACTION (UP TO 20)",  "Addition up to 20 (Class 1)"),
    ("Addition & Subtraction (up to 20)",    "Addition up to 20 (Class 1)"),
    ("subtraction (up to 20)",               "Subtraction within 20 (Class 1)"),
    ("Subtraction up to 20",                 "Subtraction within 20 (Class 1)"),
    # Class 3 must still work
    ("Addition",                             "Addition (carries)"),
    ("addition",                             "Addition (carries)"),
    ("Subtraction",                          "Subtraction (borrowing)"),
    ("Addition and subtraction",             "Addition and subtraction (3-digit)"),
    ("Multiplication",                       "Multiplication (tables 2-10)"),
    ("Fractions",                            "Fractions"),
    ("Time",                                 "Time (reading clock, calendar)"),
    ("Money",                                "Money (bills and change)"),
]

for topic, expected in ADVERSARIAL:
    canon = resolve(topic)
    if canon == expected:
        ok(f'"{topic}" \u2192 "{canon}"')
    else:
        fail(f'"{topic}" \u2192 "{canon}" (expected "{expected}")')

# ════════════════════════════════════════
# 5. BUILD_WORKSHEET_PLAN — Class 1 plans must never contain carry/borrow
# ════════════════════════════════════════
print("\n── TEST 5: Class 1 Plans \u2014 No Carry/Borrow Tags ──")

CLASS1_MATHS = [
    "Addition up to 20 (Class 1)",
    "Subtraction within 20 (Class 1)",
    "Numbers 1 to 50 (Class 1)",
    "Numbers 51 to 100 (Class 1)",
    "Basic Shapes (Class 1)",
    "Measurement (Class 1)",
    "Time (Class 1)",
    "Money (Class 1)",
]

CARRY_TAGS = {"column_add_with_carry", "column_sub_with_borrow"}

for topic in CLASS1_MATHS:
    try:
        plan = build_worksheet_plan(10, topic=topic)
        plan_tags = {d.get("skill_tag", "") for d in plan}
        bad = CARRY_TAGS & plan_tags
        if not bad:
            ok(f'"{topic}" plan(10) \u2014 no carry/borrow tags')
        else:
            fail(f'"{topic}" plan(10) has carry/borrow tags: {bad}')
    except Exception as e:
        fail(f'"{topic}" build_worksheet_plan raised: {e}')

# ════════════════════════════════════════
# 6. CLASS 3 CARRY INTEGRITY — must still get carry/borrow tags
# ════════════════════════════════════════
print("\n── TEST 6: Class 3 Carry Integrity (regression) ──")

CLASS3_ARITH = [
    "Addition (carries)",
    "Subtraction (borrowing)",
    "Addition and subtraction (3-digit)",
]

for topic in CLASS3_ARITH:
    try:
        plan = build_worksheet_plan(10, topic=topic)
        plan_tags = {d.get("skill_tag", "") for d in plan}
        has_carry = bool(CARRY_TAGS & plan_tags)
        if has_carry:
            ok(f'"{topic}" plan(10) correctly has carry/borrow tags')
        else:
            fail(f'"{topic}" plan(10) MISSING carry/borrow tags \u2014 regression!')
    except Exception as e:
        fail(f'"{topic}" build_worksheet_plan raised: {e}')

# ════════════════════════════════════════
print("\n" + "=" * 60)
print(f"RESULTS: {PASS} passed  |  {FAIL} failed  |  {WARN} warnings")
print("=" * 60)

if FAIL > 0:
    print("\n\u274c SOME TESTS FAILED \u2014 do not deploy until all pass")
    sys.exit(1)
else:
    print("\n\u2705 ALL TESTS PASSED \u2014 safe to deploy")
    sys.exit(0)

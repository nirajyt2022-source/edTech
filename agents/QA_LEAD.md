# QA_LEAD.md — QA Lead Agent

## Role
You are the **QA Lead Agent** for the edTech CBSE Worksheet Generator. You own all test coverage across backend and frontend. You write deterministic tests, validate topic profiles, catch regressions, and ensure the pipeline meets quality standards before any feature ships. You report failures to PjM_AGENT with exact file/line references.

You always read `CLAUDE.md` AND `PjM_AGENT.md` at the start of every session before writing any tests.

---

## Domain Ownership
```
backend/scripts/
├── test_slot_engine.py        ← Existing: slot engine unit tests
├── verify_topics.py           ← Existing: topic profile verification (no LLM)
└── test_all_topics.py         ← NEW (S1-QA-01): full 12-topic × 4-count matrix

frontend/
└── [future: vitest tests]     ← Component tests (P2 priority)
```

---

## Current Task Queue (from PjM_AGENT.md)

### 🔴 ACTIVE: S1-QA-01 — Class 3 Maths Full Topic Test Suite

**Create**: `backend/scripts/test_all_topics.py`

**Test matrix**: 12 topics × {5, 10, 15, 20} questions = 48 combinations (deterministic, no LLM)

**All 12 topics to test**:
```python
ALL_TOPICS = [
    "Addition (carries)",
    "Subtraction (borrowing)",
    "Addition and subtraction (3-digit)",
    "Multiplication (tables 2-10)",
    "Division basics",
    "Numbers up to 10000",
    "Fractions (halves, quarters)",
    "Fractions",
    "Time (reading clock, calendar)",
    "Money (bills and change)",
    "Symmetry",
    "Patterns and sequences",
]
ALL_COUNTS = [5, 10, 15, 20]
```

**Per-combination validation checklist**:
```python
def validate_combination(topic, count, slot_plan, questions):
    errors = []

    # 1. Slot count exact match
    expected = get_slot_plan(count)
    actual_counts = Counter(q['slot_type'] for q in questions)
    for slot_type, expected_count in expected.items():
        if actual_counts.get(slot_type, 0) != expected_count:
            errors.append(f"Slot count mismatch: {slot_type} expected {expected_count} got {actual_counts.get(slot_type, 0)}")

    # 2. ED >= 1
    if actual_counts.get('error_detection', 0) < 1:
        errors.append("error_detection count < 1")

    # 3. T >= 1
    if actual_counts.get('thinking', 0) < 1:
        errors.append("thinking count < 1")

    # 4. No duplicate question text
    texts = [q['question_text'] for q in questions]
    if len(texts) != len(set(texts)):
        errors.append("Duplicate question text found")

    # 5. No visual phrases in question text
    VISUAL_PHRASES = ['draw', 'shade', 'colour', 'color', 'circle the', 'tick the', 'cross the']
    for q in questions:
        for phrase in VISUAL_PHRASES:
            if phrase.lower() in q['question_text'].lower():
                errors.append(f"Visual phrase '{phrase}' in question: {q['question_text'][:60]}")

    # 6. No empty answers
    for q in questions:
        if not q.get('answer') or str(q['answer']).strip() == '':
            errors.append(f"Empty answer for question: {q['question_text'][:60]}")

    # 7. Question text >= 10 chars
    for q in questions:
        if len(q.get('question_text', '')) < 10:
            errors.append(f"Question text too short: {q['question_text']}")

    # 8. Format in VALID_FORMATS for that slot_type
    for q in questions:
        slot = q['slot_type']
        fmt = q['format']
        if fmt not in VALID_FORMATS.get(slot, set()):
            errors.append(f"Invalid format '{fmt}' for slot_type '{slot}'")

    return errors
```

**Script exit behavior**:
```python
if __name__ == "__main__":
    all_passed = True
    for topic in ALL_TOPICS:
        for count in ALL_COUNTS:
            errors = run_test(topic, count)
            if errors:
                all_passed = False
                print(f"FAIL [{topic}][{count}q]: {errors}")
            else:
                print(f"PASS [{topic}][{count}q]")
    sys.exit(0 if all_passed else 1)  # CI-compatible exit code
```

**Definition of done**: Script exits 0 with 48/48 PASS. Run time < 60s.

---

### 🟡 NEXT: Extend verify_topics.py for add/sub recipes_by_count

**File to edit**: `backend/scripts/verify_topics.py`

**What to add**:
```python
# Verify recipes_by_count for "Addition and subtraction (3-digit)"
def verify_add_sub_recipes():
    topic = "Addition and subtraction (3-digit)"
    profile = TOPIC_PROFILES.get(topic)
    assert profile is not None, f"Topic profile missing: {topic}"
    recipes = profile.get('recipes_by_count', {})
    for count in [5, 10, 15, 20]:
        assert count in recipes, f"recipes_by_count missing count: {count}"
        recipe = recipes[count]
        total = sum(recipe.values())
        assert total == count, f"recipes_by_count[{count}] sums to {total}, expected {count}"
        assert recipe.get('error_detection', 0) >= 1, f"ED < 1 in recipe for count {count}"
        assert recipe.get('thinking', 0) >= 1, f"T < 1 in recipe for count {count}"
```

---

## QA Coverage Matrix

### Backend — Current Coverage
| Module | Covered | Notes |
|---|---|---|
| slot_engine.py — slot plans | ✅ | test_slot_engine.py |
| slot_engine.py — validators | ✅ | test_slot_engine.py |
| topic profiles — 12 topics | 🟡 Partial | verify_topics.py (no count tests) |
| topic profiles — all counts | ❌ | S1-QA-01 target |
| skill contracts | ❌ | Needs dedicated test |
| visual hydration | ❌ | Needs dedicated test |
| API endpoints | ❌ | P1 priority |
| syllabus parser | ❌ | Add when S1-BE-02 ships |
| payment webhook | ❌ | Add when S1-DA-01 ships |

### Frontend — Current Coverage
| Module | Covered | Notes |
|---|---|---|
| Components | ❌ | P2 priority (vitest) |
| API layer | ❌ | P2 priority |
| Visual rendering | ❌ | P2 priority |

---

## QA Operating Rules (extends global CLAUDE.md rules)

### Test philosophy
- **Deterministic first**: Tests must run without `OPENAI_API_KEY`. LLM-dependent tests are integration tests only.
- **CI-compatible**: All test scripts exit with code 0 (pass) or non-zero (fail). No interactive prompts.
- **Exact assertions**: Never assert "at least" or "approximately" — assert exact counts, exact formats
- **Isolated**: Each test combination must be independent — no shared state between test runs

### Regression rules
- Any change to `slot_engine.py` → run `test_slot_engine.py` AND `test_all_topics.py` before commit
- Any new topic profile → add to `ALL_TOPICS` in `test_all_topics.py` on same commit
- Any validator change → update test expectations in `test_slot_engine.py` on same commit
- `verify_topics.py` must pass with exit code 0 after ANY change to `slot_engine.py`

### Bug reporting format
```
BUG-[date]-[seq]: [Short description]
File: [exact file path]
Line: [line number if known]
Repro: [exact command to reproduce]
Expected: [what should happen]
Actual: [what happens]
Severity: P0/P1/P2/P3
Assigned to: [Backend/Frontend/Data Lead]
```

### What makes a test COMPLETE
- [ ] Script runs without API keys
- [ ] Exit code 0 on all pass, non-zero on any fail
- [ ] Output clearly identifies which combination failed
- [ ] Run time measured and under target (60s for full suite)
- [ ] Added to CI pipeline documentation in CLAUDE.md

---

## Specialist Agents Under QA Lead

### Backend Test Agent (activate when: writing backend unit tests, validator tests)
**Focus**: `backend/scripts/test_*.py`, `backend/scripts/verify_*.py`
**Trigger phrase**: "You are the Backend Test Agent. Read QA_LEAD.md and CLAUDE.md, then [task]."

### Frontend Test Agent (activate when: writing component tests, hook tests)
**Focus**: `frontend/src/**/*.test.tsx`, vitest config
**Trigger phrase**: "You are the Frontend Test Agent. Read QA_LEAD.md and CLAUDE.md, then [task]."

### Integration Test Agent (activate when: end-to-end pipeline tests)
**Focus**: Full worksheet generation pipeline, API contract tests
**Trigger phrase**: "You are the Integration Test Agent. Read QA_LEAD.md and CLAUDE.md, then [task]."

---

## Common QA Commands
```bash
# Run all deterministic backend tests
cd backend && python scripts/test_slot_engine.py
cd backend && python scripts/verify_topics.py

# Run new full topic matrix test (after S1-QA-01 ships)
cd backend && python scripts/test_all_topics.py

# Check for silent failure patterns (feeds into S1-BE-01 bug list)
grep -rn "except Exception: pass\|except Exception: return\|except:\s*$" backend/app/

# Check for visual phrase violations (feeds into topic quality)
grep -rn "draw\|shade\|colour\|circle the" backend/app/services/slot_engine.py
```

---

## Update Log (QA)
- **2026-02-17**: Agent file created. S1-QA-01 test plan documented. Coverage matrix established.

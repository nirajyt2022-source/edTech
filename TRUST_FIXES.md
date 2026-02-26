# Trust-Destroying Weaknesses — Fix Tracker

> **Goal:** Eliminate silent quality degradation. Every failure must be visible or blocked.
> **Created:** 2026-02-26

---

## Fix Now (High Impact, Low Risk)

| # | Weakness | Fix | Status |
|---|---|---|---|
| 1 | Fail-open validation — CHECK 1 (arithmetic) silently skips | Make arithmetic check a hard block; if it throws, flag question as unverified | [x] Done |
| 2 | Unknown question types → silent "short_answer" | Retry on unknown type; only fallback after 2 retries | [x] Done |
| 5 | 80% question count accepted | Raise to 100% match or trigger retry | [x] Done |
| 10 | Warnings collected but never surfaced | Add `warnings` array to API response; frontend shows banner | [x] Done |

## Fix Next (Medium Effort, Structural)

| # | Weakness | Fix | Status |
|---|---|---|---|
| 3 | Calibrator Steps D/E only log, never fix | Step D: swap excess format types; Step E: reorder by number magnitude | [ ] |
| 8 | Retry only on drift/duplicates | Add validation_errors to retry trigger conditions | [ ] |
| 9 | Recipe skill_tags not validated against allowed_skill_tags | Add startup validation script + CI check | [ ] |

## Fix Later (Design Decisions Required)

| # | Weakness | Fix | Status |
|---|---|---|---|
| 4 | Curriculum context silently optional | Decision: hard-fail or remove badge when context missing | [ ] |
| 6 | Adaptive difficulty defaults to recall | Requires mastery data pipeline to be reliable first | [ ] |
| 7 | Math verification gaps on 3+ number problems | Extend parser to handle chained operations | [ ] |

---

## Fix Details

### Fix 1: Hard-block arithmetic failures

**File:** `backend/app/services/quality_reviewer.py`

- CHECK 1: Remove `except Exception: logger.debug(skip)` pattern
- If arithmetic extraction succeeds but correction throws → mark question `_math_unverified: true`
- If `_math_unverified` count > 2 in a worksheet → trigger retry
- Never silently ship a wrong answer

### Fix 2: Retry on unknown question type

**File:** `backend/app/services/worksheet_generator.py`

- In `validate_response()`, when unknown type detected, don't default to short_answer
- Instead: add to `type_errors` list, return as retry trigger
- Only fallback to short_answer on final retry (attempt 3)

### Fix 5: Enforce exact question count

**File:** `backend/app/services/output_validator.py`

- Change `min_required = max(1, int(num_questions * 0.8))` → `min_required = num_questions`
- If count < requested, return as retry trigger (not just warning)
- After max retries, accept what we have but surface warning

### Fix 10: Surface warnings in API + frontend

**Files:** `backend/app/api/worksheets_v2.py`, `frontend/src/components/WorksheetGenerator.tsx`

- API: Include `warnings` array in response (already collected, just hidden)
- Frontend: Show amber banner when `warnings.length > 0`
- Categories: math_unverified, count_mismatch, format_drift, near_duplicates

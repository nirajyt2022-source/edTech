# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Development Commands

## Backend
```bash
# Install dependencies (from backend/)
pip install -r requirements.txt
# or with pyproject.toml: pip install -e ".[dev]"

# Run dev server
cd backend && uvicorn app.main:app --reload --port 8000

# Run tests (deterministic only, no API key needed)
cd backend && python scripts/test_slot_engine.py

# Run tests with LLM integration (requires OPENAI_API_KEY)
cd backend && OPENAI_API_KEY=sk-... python scripts/test_slot_engine.py
```

## Frontend
```bash
# Install dependencies (from frontend/)
cd frontend && npm install

# Run dev server
cd frontend && npm run dev

# Build
cd frontend && npm run build   # runs tsc -b && vite build

# Lint
cd frontend && npm run lint    # eslint
```

## Pre-commit Hook
The repo has a git pre-commit hook that auto-appends a dated entry to the `# Update Log` section of CLAUDE.md with changed file paths. **You must replace that auto-generated path list with a human-readable summary** before the commit is finalized.

# Architecture

- **Backend**: FastAPI app in `backend/app/main.py`, config via `backend/app/core/config.py`
- **Frontend**: React + Vite + TailwindCSS v4 + shadcn/ui in `frontend/src/`
- **Top-level folders**: `backend/`, `frontend/`, `contracts/`, `curriculum/`, `engine/`, `scripts/`, `stitch/`, `syllabus_cbse/`, `docs/`, `artifacts/`
- **Backend internals**: `backend/app/api/` (routers), `backend/app/services/` (business logic), `backend/app/core/` (config), `backend/app/skills/` (skill contracts)
- **Frontend internals**: `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/lib/`, `frontend/src/types/`
- **Entry point**: `backend/app/main.py` mounts 14 routers via `app.include_router()`
- **CORS**: configured for localhost:3000/5173/5174 and `ed-tech-drab.vercel.app`

# Skill System

- **Registry**: `backend/app/skills/registry.py` — read-only dict `SKILL_REGISTRY` mapping skill_tag to contract instance, loaded at module init
- **Contracts**: 3 registered — `column_add_with_carry` (ColumnAdditionContract), `column_sub_with_borrow` (ColumnSubtractionWithBorrowContract), `multiplication_table_recall` (MultiplicationTableRecallContract)
- **Base class**: `backend/app/skills/base.py` — abstract interface with optional hooks: `build_variant()`, `validate()`, `build_slots()`, `repair()`, `explain()`, `grade()`, `recommend_next()`, `generate_drill()`
- **Carry/borrow enforcement**: 15 precomputed 3-digit CARRY_PAIRS requiring carry/borrow in both ones and tens columns. `make_carry_pair(rng, op)` generates valid pairs with 50-retry loop + hardcoded fallback
- **Error computation**: `compute_wrong(a, b, tag)` produces deterministic wrong answers for 5 misconception tags: `lost_carry_ones`, `lost_carry_tens`, `double_carry`, `carry_to_wrong_col`, `no_carry_digitwise`
- **Pipeline hooks**: contracts inject at variant selection (step 5), slot materialization (step 8d-post), and validation/repair/regen (step 8e-pre)

# Slot Builder Rules

- **Slot plans** (exact): 5 &rarr; 1R,1A,1Rep,1ED,1T | 10 &rarr; 2,4,2,1,1 | 15 &rarr; 3,6,3,2,1 | 20 &rarr; 4,8,4,2,2. Non-standard counts use proportional fallback with mandatory ED&ge;1, T&ge;1
- **Plan construction**: `get_slot_plan()` returns slot_type sequence; `build_worksheet_plan()` converts mix_recipe into directives with slot_type, format_hint, and constraints
- **Valid formats per slot**: recognition={column_setup, place_value}, application={word_problem}, representation={missing_number, estimation, place_value}, error_detection={error_spot}, thinking={thinking}
- **Per-question validation** (`validate_question`): format in VALID_FORMATS, no visual phrases, non-empty answer, text &ge;10 chars, error_detection needs error language + 2 numbers, representation needs blank markers, thinking needs reasoning language, pictorial_elements must be empty
- **Worksheet validation** (`validate_worksheet_slots`): slot counts match plan, ED&ge;1 and T&ge;1, unique number pairs, no duplicate question text, no repeated contexts in application questions
- **enforce_slot_counts**: deterministic trim (keep first N per slot_type) / fill (synthesize fallback with valid format), re-numbers IDs 1&rarr;N
- **Answer normalizers**: `normalize_estimation_answers` recomputes closer-to/round-to sums deterministically; `normalize_error_spot_answers` extracts numeric answer from LLM explanatory text

# API Surface

- `/api/worksheets/` — legacy worksheet generation + PDF export (`worksheets.py`)
- `/api/v1/worksheets/` — v1 API: generate, grade, explain, recommend, drill, chain, attempt, mastery (`worksheets_v1.py`)
- `/api/v1/dashboard/` — dashboard endpoints (`dashboard.py`)
- `/api/children/` — child profile CRUD (`children.py`)
- `/api/users/` — user management (`users.py`)
- `/api/classes/` — class management (`classes.py`)
- `/api/subscription/` — subscription status (`subscription.py`)
- `/api/syllabus/` — syllabus tree (`syllabus.py`)
- `/api/cbse-syllabus/` — CBSE-specific syllabus (`cbse_syllabus.py`)
- `/api/curriculum/` — curriculum endpoints (`curriculum.py`)
- `/api/topic-preferences/` — user topic preferences (`topic_preferences.py`)
- `/api/engagement/` — engagement tracking (`engagement.py`)
- `/api/analytics/` — analytics endpoints (`analytics.py`)
- `/health` — health check (`health.py`)

# Database Schema

- **worksheets**: id (UUID), user_id, title, board, grade, subject, topic, difficulty, language, questions (JSONB), child_id, class_id, regeneration_count, timestamps
- **children**: id (UUID), user_id, name, grade, board, notes, timestamps
- **user_subscriptions**: id (UUID), user_id (UNIQUE), tier (free/paid), worksheets_generated_this_month, month_reset_at, timestamps. Auto-created on auth.users INSERT via trigger
- **user_profiles**: user_id (UNIQUE ref auth.users), role (parent/teacher), active_role, subjects[], grades[], school_name, timestamps
- **teacher_classes**: id (UUID), user_id, name, grade, subject, board, syllabus_source (cbse/custom), custom_syllabus (JSONB), timestamps
- **cbse_syllabus**: id (UUID), grade, subject, chapters (JSONB), UNIQUE(grade, subject), timestamps
- **topic_preferences**: id (UUID), user_id, child_id, subject, selected_topics (JSONB), UNIQUE(child_id, subject), timestamps
- **child_engagement**: id (UUID), user_id, child_id (UNIQUE), total_stars, current_streak, longest_streak, last_activity_date, total_worksheets_completed, timestamps
- **mastery_state**: PK (student_id, skill_tag), streak, total_attempts, correct_attempts, last_error_type, mastery_level (unknown/learning/improving/mastered), updated_at. Migration: `backend/scripts/sql/migrations/001_mastery_state.sql`
- **attempt_events**: student_id, worksheet_id, attempt_id, question, student_answer, grade_result, mastery_before/after, ts. Gated by `ENABLE_ATTEMPT_AUDIT_DB=1`
- **telemetry_events**: event, route, version, student_id, skill_tag, error_type, latency_ms, ok, ts. Gated by `ENABLE_TELEMETRY_DB=1`
- All tables use **Row-Level Security (RLS)** with Supabase Auth policies. Schema in `backend/supabase_schema.sql`

# Visual Rendering

- **Data flow**: LLM generates question_text → `hydrate_visuals()` applies deterministic regex rules → sets `representation`, `visual_spec`, `visual_model_ref` → `_map_visual_fields()` translates to API `visual_type`/`visual_data` → frontend `VisualProblem` component renders SVG
- **Hydration rules** (checked in order): blank markers (`___`,`?`,`□`) + 2 ints → `NUMBER_LINE`; closer-to/estimate keywords → `NUMBER_LINE`; add/subtract keywords + 2 ints → `BASE_TEN_REGROUPING`; else → `TEXT_ONLY`
- **Model IDs**: `NUMBER_LINE` (start, end, tick_interval, markers), `BASE_TEN_REGROUPING` (numbers[], operation)
- **Frontend components**: `number_line` → NumberLineVisual, `base_ten_regrouping` → BaseTenRegroupingVisual (interactive H/T/O digit inputs), `clock` → ClockVisual, `object_group` → ObjectGroupVisual, `shapes` → ShapeVisual. Unknown types return `null`
- **Field mapping** (`_map_visual_fields` in worksheets.py): `tick_interval` → `step`, `markers` → `highlight`; returns `(None, None)` if `representation != "PICTORIAL_MODEL"` or missing `model_id`
- **visuals_only mode**: `enforce_visuals_only()` replaces TEXT_ONLY questions with synthetic BASE_TEN_REGROUPING column-form until >=80% visual coverage
- **Failure conditions**: missing/malformed `visual_spec` → text-only fallback; empty `numbers[]` in BASE_TEN_REGROUPING → frontend returns null; invalid NUMBER_LINE range (start >= end) → null; unknown `visual_type` → null
- **Contract auditing**: `verify_visual_contract()` logs table of all questions confirming representation + model_id + visual_model_ref present

# Environment & Deployment

- **Required env**: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`), `OPENAI_API_KEY`
- **Optional env**: `DEBUG` (default false), `FRONTEND_URL` (default `http://localhost:5173`)
- **Feature flags**: `ENABLE_TELEMETRY_DB=1` (persist telemetry to DB), `ENABLE_ATTEMPT_AUDIT_DB=1` (persist attempt audits to DB), `PRACTICECRAFT_MASTERY_STORE=supabase` (default `memory` — in-memory resets on restart)
- **Frontend env**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (default `http://localhost:8000`)
- **Deployment**: Railway with NIXPACKS builder. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Restart policy: ON_FAILURE (max 10 retries). Config in `backend/railway.json`
- **Frontend hosting**: Vercel at `ed-tech-drab.vercel.app`

# Known Issues

## Incomplete Features
- `subscription.py:upgrade_to_paid()` — sets tier to "paid" immediately with no payment verification (Stripe/Razorpay placeholder)
- `syllabus.py:parse_syllabus()` — returns raw_response only; no structured parsing or AI extraction implemented
- `syllabus.py:get_syllabus()` — GET endpoint returns "not implemented yet" placeholder

## Silent Failures (bare except)
- `audit.py:write_attempt_event()` — `except Exception: return` with no logging; audit trail silently breaks
- `telemetry.py:emit_event()` — `except Exception: pass` on DB write; only stderr logging survives
- `mastery_store.py:get_mastery_store()` — Supabase init failure silently falls back to in-memory store; all progress lost on restart
- `worksheets_v1.py:attempt_v1()` — two `except Exception: pass` blocks around mastery tracking and audit
- `slot_engine.py` — multiple silent skips: slot building (~L1128), mastery update (~L1242), LLM retry loop (~L1696)

## Degraded Output (best-effort proceeds)
- Failed question generation after 3 retries inserts `"[Generation failed for {slot_type} question]"` stub into worksheet
- `enforce_slot_counts()` synthesizes filler questions with `"[Slot fill]"` marker when slots are missing
- Difficulty auto-escalates easy→medium if sanity check fails (no user consent)
- Worksheet-level and carry validation warnings are logged but worksheet is still returned
- Contract repair failure → regen attempt → if regen fails, keeps original invalid question

## Frontend Silent Failures
- `subscription.tsx` — fetch failure silently downgrades user to free tier; no error shown
- `engagement.tsx` — completion recording failure returns null; user unaware progress didn't persist
- `profile.tsx` — fetch failure clears profile to null; UI shows "needs role selection" instead of error
- `api.ts` — v1 endpoint 500 silently falls back to legacy API; both-fail shows generic error

## Legacy Code (dead but present)
- `worksheets.py`: `build_system_prompt()`, `_fixup_question_types()`, `_fix_computational_answers()`, `_fix_inconsistent_visuals()` — defined but not called from main pipeline

# Versioning Rules

# Claude Operating Rules

- **Deterministic-first**: Backend owns structure (slot plans, variants, validation). LLM fills content only. All post-generation fixes must be deterministic — no LLM calls for repair.
- **No silent fallback**: Every `except` block must log. Mastery store, audit, and telemetry failures must be visible. Never swallow errors with bare `pass`.
- **Contracts override generation**: If a skill contract exists for a skill_tag, its `validate()` → `repair()` → regen cycle takes precedence over generic pipeline logic.
- **Slot discipline is mandatory**: Slot counts must exactly match the plan. `enforce_slot_counts()` is the last resort — generation and repair should produce correct counts first.
- **Visual coverage must be 100%**: Every question with `representation="PICTORIAL_MODEL"` must have valid `visual_spec.model_id` and `visual_model_ref`. `verify_visual_contract()` must show all YES.
- **Never relax carry/borrow enforcement**: `has_carry()`/`has_borrow()` checks are non-negotiable for `column_add_with_carry` and `column_sub_with_borrow` skills. Fallback to hardcoded CARRY_PAIRS if random generation exhausts retries.
- **Update CLAUDE.md on commit**: Before every commit, update the `# Update Log` section with a meaningful one-line summary of what changed. The git pre-commit hook adds file paths automatically; Claude must replace that with a human-readable description.

# Update Log

- **2026-02-12**: Initial documentation pass. Populated all sections from codebase scan.
- **2026-02-12**: v1.3 multi-skill bundle — generate_worksheet splits questions across skills, returns worksheets[] array. Fixed single-skill topic metadata bug. Frontend tab UI for switching worksheets in bundle. Test #37 added.
- **2026-02-12**: Skill purity enforcement — UI_SKILL_TO_CONTRACTS mapping forces contract key on bundled worksheets. Off-topic questions repaired via contract.repair(). skill_tag propagation fixed in _slot_to_question. Test #38 (7 cases).
- **2026-02-12**: Add/sub expansion — "Addition and subtraction (3-digit)" now expands to two contracts (column_add_with_carry + column_sub_with_borrow), producing separate addition and subtraction worksheets. Honest topic labels via CONTRACT_TOPIC_LABEL. Test #39 (8 cases).
- **2026-02-12**: Role-based explanations — `_fill_role_explanations()` adds deterministic explanations for thinking (estimation/closer-to/compare) and error_detection (carry/borrow) roles only. Other roles stay null. Capped at 160 chars, preserves pre-existing explanations. Test #40 (10 cases).
- **2026-02-12**: Estimation visual highlight fix — `normalize_estimation_answers()` now sets NUMBER_LINE highlight to the estimate (rounded sum / closer ref), not the exact sum. Widens number line range if estimate falls outside bounds. Test #41 (7 cases).
- **2026-02-16**: Changes in backend/app/api, backend/app/services, backend/scripts
- **2026-02-17**: Changes in backend/app/services, backend/scripts

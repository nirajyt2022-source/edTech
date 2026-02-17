# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Development Commands

## Backend
```bash
# Install dependencies (from backend/)
pip install -r requirements.txt

# Run dev server
cd backend && uvicorn app.main:app --reload --port 8000

# Run tests (deterministic only, no API key needed)
cd backend && python scripts/test_slot_engine.py

# Run tests with LLM integration (requires OPENAI_API_KEY)
cd backend && OPENAI_API_KEY=sk-... python scripts/test_slot_engine.py

# Verify all topic profiles (deterministic, no LLM)
cd backend && python scripts/verify_topics.py
```

## Frontend
```bash
cd frontend && npm install
cd frontend && npm run dev        # dev server on :5173
cd frontend && npm run build      # tsc -b && vite build
cd frontend && npm run lint       # eslint
```

## Pre-commit Hook
The repo has a git pre-commit hook that auto-appends a dated entry to the `# Update Log` section of CLAUDE.md with changed file paths. **You must replace that auto-generated path list with a human-readable summary** before the commit is finalized.

# Architecture

- **Backend**: FastAPI app in `backend/app/main.py`, config via `backend/app/core/config.py`
- **Frontend**: React + Vite + TailwindCSS v4 + shadcn/ui in `frontend/src/`
- **Backend internals**: `backend/app/api/` (routers), `backend/app/services/` (business logic), `backend/app/core/` (config), `backend/app/skills/` (skill contracts)
- **Frontend internals**: `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/lib/`, `frontend/src/types/`
- **Entry point**: `backend/app/main.py` mounts 14 routers via `app.include_router()`
- **CORS**: configured for localhost:3000/5173/5174 and `ed-tech-drab.vercel.app`
- **Frontend API layer**: `frontend/src/lib/api.ts` uses axios with Supabase auth token injection; `apiV1WithFallback()` tries v1 endpoint first, falls back to legacy `/api/worksheets/` on 404/500

# Worksheet Generation Pipeline

Core file: `backend/app/services/slot_engine.py` — two-phase generation.
API endpoint: `backend/app/api/worksheets.py` calls `run_slot_pipeline()`.

## Pipeline Order
`generate_meta` (1 LLM call) → `get_slot_plan` → per-question generate+validate (N calls, 3 retries each) → `validate_worksheet_slots` → map to API response

## Slot Plans (exact, no rounding)
5→ 1R,1A,1Rep,1ED,1T | 10→ 2,4,2,1,1 | 15→ 3,6,3,2,1 | 20→ 4,8,4,2,2. Non-standard counts use proportional fallback with mandatory ED≥1, T≥1.

## Valid Formats per Slot (Maths)
```
recognition:     {column_setup, place_value, simple_identify, fraction_number, clock_question,
                  calendar_question, money_question, symmetry_question, shape_pattern,
                  division_problem, place_value_question, comparison_question, multiplication_problem}
application:     {word_problem, sequence_question, symmetry_complete, pattern_question,
                  ordering_question, comparison_question}
representation:  {missing_number, estimation, place_value, shape_question, expanded_form}
error_detection: {error_spot}
thinking:        {thinking, growing_pattern, multi_step}
```

## Valid Formats per Slot (English)
```
recognition:     {identify_noun, identify_verb, identify_adjective, identify_pronoun,
                  identify_adverb, identify_preposition, identify_conjunction, identify_tense,
                  identify_sentence_type, identify_prefix, identify_suffix, identify_rhyme,
                  identify_punctuation, pick_correct}
application:     {fill_in_blank, rewrite_sentence, match_columns, use_in_sentence,
                  word_problem_english, correct_sentence}
representation:  {complete_sentence, rearrange_words, change_form, expand_sentence, paragraph_cloze}
error_detection: {error_spot_english}
thinking:        {explain_why, creative_writing}
```

## Valid Formats per Slot (Science)
```
recognition:     {identify_part, classify_object, true_false, match_function,
                  label_diagram, pick_correct_science}
application:     {explain_why_science, what_happens_if, give_example,
                  compare_two, word_problem_science}
representation:  {fill_diagram, sequence_steps, cause_effect, complete_sentence_science}
error_detection: {error_spot_science}
thinking:        {thinking_science, multi_step_science}
```

## Valid Formats per Slot (Hindi)
```
recognition:     {identify_letter, identify_matra, identify_word_type, pick_correct_hindi,
                  match_letter_sound}
application:     {fill_matra, make_word, make_sentence_hindi, word_problem_hindi,
                  use_in_sentence_hindi}
representation:  {complete_word, complete_sentence_hindi, rearrange_letters, word_formation}
error_detection: {error_spot_hindi}
thinking:        {explain_meaning, creative_writing_hindi}
```

Subject-aware lookups: `get_valid_formats(subject)`, `get_default_format_by_slot(subject)` — default to Maths.

## Per-Question Schema (internal)
`{format, question_text, pictorial_elements:[], answer}` — LLM fills content only, backend controls slot_type/difficulty.

## Validators
- **Per-question** (`validate_question`): format in VALID_FORMATS (subject-aware via `get_valid_formats()`), no visual phrases (Maths only), non-empty answer, text ≥10 chars, error_detection needs error language + 2 numbers (Maths) or grammar error language (English), representation needs blank markers, thinking needs reasoning language, pictorial_elements must be empty
- **Worksheet-level** (`validate_worksheet_slots`): slot counts match plan, ED≥1 and T≥1, unique number pairs, no duplicate question text, no repeated contexts in application questions
- **Safety net** (`enforce_slot_counts`): deterministic trim/fill, re-numbers IDs 1→N
- **Answer normalizers**: `normalize_estimation_answers` recomputes closer-to/round-to sums deterministically; `normalize_error_spot_answers` extracts numeric answer from LLM explanatory text; `normalize_english_answers` cleans up text answers for English

# Topic System

## 112 Supported Topics (TOPIC_PROFILES keys)

### Class 1 Maths (8 topics)
1. Numbers 1 to 50 (Class 1) — counting, comparing, ordering 1-50
2. Numbers 51 to 100 (Class 1) — counting, comparing, ordering 51-100
3. Addition up to 20 (Class 1) — sums ≤20, no carrying, horizontal only
4. Subtraction within 20 (Class 1) — differences within 20, no borrowing
5. Basic Shapes (Class 1) — circle, square, triangle, rectangle only
6. Measurement (Class 1) — longer/shorter, heavier/lighter, no standard units
7. Time (Class 1) — days of week, morning/afternoon/night, no clock reading
8. Money (Class 1) — ₹1, ₹2, ₹5 coins only, totals ≤₹20

### Class 2 Maths (10 topics)
1. Numbers up to 1000 (Class 2) — 3-digit place value
2. Addition (2-digit with carry)
3. Subtraction (2-digit with borrow)
4. Multiplication (tables 2-5)
5. Division (sharing equally) — division by 2-5, no remainders
6. Shapes and space (2D) — circle, square, triangle, rectangle
7. Measurement (length, weight) — cm, m, kg, g
8. Time (hour, half-hour) — o'clock and half past only
9. Money (coins and notes) — amounts up to ₹100
10. Data handling (pictographs)

### Class 3 Maths (12 topics)
11. Addition (carries) — 3-digit with carry enforcement
12. Subtraction (borrowing) — 3-digit with borrow enforcement
13. Addition and subtraction (3-digit) — combined, uses `recipes_by_count` for 5/10/15/20
14. Multiplication (tables 2-10)
15. Division basics
16. Numbers up to 10000 — place value, comparison, expansion, ordering
17. Fractions (halves, quarters) — limited scope
18. Fractions — broader fractions
19. Time (reading clock, calendar)
20. Money (bills and change)
21. Symmetry
22. Patterns and sequences

### Class 4 Maths (10 topics)
23. Large numbers (up to 1,00,000) — Indian system, 5-digit
24. Addition and subtraction (5-digit)
25. Multiplication (3-digit × 2-digit)
26. Division (long division) — 3-digit ÷ 1-digit with remainder
27. Fractions (equivalent, comparison)
28. Decimals (tenths, hundredths)
29. Geometry (angles, lines)
30. Perimeter and area — rectangles, squares
31. Time (minutes, 24-hour clock)
32. Money (bills, profit/loss)

### Class 5 Maths (10 topics)
33. Numbers up to 10 lakh (Class 5) — Indian system, 7-digit
34. Factors and multiples (Class 5)
35. HCF and LCM (Class 5)
36. Fractions (add and subtract) (Class 5) — unlike fractions
37. Decimals (all operations) (Class 5)
38. Percentage (Class 5)
39. Area and volume (Class 5) — cubes, cuboids
40. Geometry (circles, symmetry) (Class 5)
41. Data handling (pie charts) (Class 5)
42. Speed distance time (Class 5)

### Class 1 English (7 topics)
43. Alphabet (Class 1), 44. Phonics (Class 1), 45. Self and Family Vocabulary (Class 1), 46. Animals and Food Vocabulary (Class 1), 47. Greetings and Polite Words (Class 1), 48. Seasons (Class 1), 49. Simple Sentences (Class 1)

### Class 2 English (6 topics)
50. Nouns (Class 2), 51. Verbs (Class 2), 52. Pronouns (Class 2), 53. Sentences (Class 2), 54. Rhyming Words (Class 2), 55. Punctuation (Class 2)

### Class 3 English (8 topics)
56. Nouns (Class 3), 57. Verbs (Class 3), 58. Adjectives (Class 3), 59. Pronouns (Class 3), 60. Tenses (Class 3), 61. Punctuation (Class 3), 62. Vocabulary (Class 3), 63. Reading Comprehension (Class 3)

### Class 4 English (8 topics)
64. Tenses (Class 4), 65. Sentence Types (Class 4), 66. Conjunctions (Class 4), 67. Prepositions (Class 4), 68. Adverbs (Class 4), 69. Prefixes and Suffixes (Class 4), 70. Vocabulary (Class 4), 71. Reading Comprehension (Class 4)

### Class 5 English (9 topics)
72. Active and Passive Voice (Class 5), 73. Direct and Indirect Speech (Class 5), 74. Complex Sentences (Class 5), 75. Summary Writing (Class 5), 76. Comprehension (Class 5), 77. Synonyms and Antonyms (Class 5), 78. Formal Letter Writing (Class 5), 79. Creative Writing (Class 5), 80. Clauses (Class 5)

### Class 1 EVS (6 topics)
81. My Family (Class 1), 82. My Body (Class 1), 83. Plants Around Us (Class 1), 84. Animals Around Us (Class 1), 85. Food We Eat (Class 1), 86. Seasons and Weather (Class 1)

### Class 2 EVS (6 topics)
87. Plants (Class 2-EVS), 88. Animals and Habitats (Class 2), 89. Food and Nutrition (Class 2), 90. Water (Class 2), 91. Shelter (Class 2), 92. Our Senses (Class 2)

### Class 3 Science (7 topics)
93. Plants (Class 3), 94. Animals (Class 3), 95. Food and Nutrition (Class 3), 96. Shelter (Class 3), 97. Water (Class 3), 98. Air (Class 3), 99. Our Body (Class 3)

### Class 3 Hindi (5 topics)
100. Varnamala (Class 3), 101. Matras (Class 3), 102. Shabd Rachna (Class 3), 103. Vakya Rachna (Class 3), 104. Kahani Lekhan (Class 3)

Each Maths profile has: `allowed_skill_tags`, `allowed_slot_types`, `disallowed_keywords`, `disallowed_visual_types`, `default_recipe`, optional `recipes_by_count`.
Each English profile additionally has: `subject: "English"`. English topics use `VALID_FORMATS_ENGLISH` and skip visual hydration (text-only).
Each Science profile additionally has: `subject: "Science"`. Science topics use `VALID_FORMATS_SCIENCE` and skip visual hydration (text-only).
Each Hindi profile additionally has: `subject: "Hindi"`. Hindi topics use `VALID_FORMATS_HINDI` and skip visual hydration (text-only). Questions use Devanagari script.

## Topic Alias Resolution
`get_topic_profile()` resolves frontend short names → canonical profile keys via `_TOPIC_ALIASES` + fuzzy matching. Key aliases: "Addition" → "Addition (carries)", "Multiplication" → "Multiplication (tables 2-10)", "Numbers"/"Place Value" → "Numbers up to 10000", "add/sub" → "Addition and subtraction (3-digit)".

In `run_slot_pipeline()`, the topic is canonicalized early so downstream lookups (e.g., `_TOPIC_CONSTRAINTS.get(topic)`) use the canonical key.

## Topic Constraints
`_TOPIC_CONSTRAINTS` provides per-topic LLM prompt guardrails for non-arithmetic topics (e.g., "NEVER generate addition/subtraction questions" for Symmetry). Arithmetic topics don't need constraints.

## Topic Instruction Builders
`_build_slot_instruction()` has early-return blocks per topic with VERIFY rules and dedup guards. Each block includes "DO NOT repeat the same numbers or scenarios" directives.

# Skill System

- **Registry**: `backend/app/skills/registry.py` — read-only `SKILL_REGISTRY` mapping skill_tag to contract instance
- **3 contracts**: `column_add_with_carry`, `column_sub_with_borrow`, `multiplication_table_recall`
- **Base class**: `backend/app/skills/base.py` — abstract interface: `build_variant()`, `validate()`, `build_slots()`, `repair()`, `explain()`, `grade()`, `recommend_next()`, `generate_drill()`
- **Carry/borrow enforcement**: 15 precomputed CARRY_PAIRS. `make_carry_pair(rng, op)` with 50-retry + hardcoded fallback. `has_carry()`/`has_borrow()` checks are non-negotiable.
- **Error computation**: `compute_wrong(a, b, tag)` produces deterministic wrong answers for 5 misconception tags

## Multi-Skill Bundle (v1.3)
`UI_SKILL_TO_CONTRACTS` in `worksheets.py` maps UI skill labels to contract keys. When `request.skills` produces 2+ expanded entries, the bundle path splits `num_questions` across skills and generates separate worksheets with purity enforcement.

**Important**: "Addition and subtraction (3-digit)" is intentionally NOT in `UI_SKILL_TO_CONTRACTS`. It uses `slot_engine.py`'s topic profile recipe to produce a single mixed worksheet.

# Visual Rendering

- **Data flow**: LLM generates question_text → `hydrate_visuals()` (deterministic regex) → sets `representation`, `visual_spec`, `visual_model_ref` → `_map_visual_fields()` → API `visual_type`/`visual_data` → frontend `VisualProblem` renders SVG
- **Hydration rules** (priority order): blank markers + 2 ints → NUMBER_LINE; closer-to/estimate → NUMBER_LINE; add/subtract + 2 ints → BASE_TEN_REGROUPING; else → TEXT_ONLY
- **Frontend components**: `number_line` → NumberLineVisual, `base_ten_regrouping` → BaseTenRegroupingVisual (H/T/O digit inputs), `clock` → ClockVisual, `object_group` → ObjectGroupVisual, `shapes` → ShapeVisual
- **visuals_only mode**: `enforce_visuals_only()` replaces TEXT_ONLY with synthetic BASE_TEN_REGROUPING until ≥80% visual coverage
- **Role-based explanations**: `_fill_role_explanations()` adds deterministic explanations for thinking and error_detection roles only. Capped at 160 chars.

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
- `/api/worksheets/{id}/share` — generate public share link (`share.py`)
- `/api/shared/{token}` — public worksheet viewer (`share.py`)
- `/api/analytics/` — analytics endpoints (`analytics.py`)
- `/health` — health check (`health.py`)

# Database Schema

- **worksheets**: id (UUID), user_id, title, board, grade, subject, topic, difficulty, language, questions (JSONB), child_id, class_id, regeneration_count, timestamps
- **children**: id (UUID), user_id, name, grade, board, notes, timestamps
- **user_subscriptions**: id (UUID), user_id (UNIQUE), tier (free/paid), worksheets_generated_this_month, month_reset_at, timestamps. Auto-created via trigger
- **user_profiles**: user_id (UNIQUE), role (parent/teacher), active_role, subjects[], grades[], school_name, timestamps
- **teacher_classes**: id (UUID), user_id, name, grade, subject, board, syllabus_source (cbse/custom), custom_syllabus (JSONB), timestamps
- **cbse_syllabus**: id (UUID), grade, subject, chapters (JSONB), UNIQUE(grade, subject), timestamps
- **topic_preferences**: id (UUID), user_id, child_id, subject, selected_topics (JSONB), UNIQUE(child_id, subject), timestamps
- **child_engagement**: id (UUID), user_id, child_id (UNIQUE), total_stars, current_streak, longest_streak, last_activity_date, total_worksheets_completed, timestamps
- **mastery_state**: PK (student_id, skill_tag), streak, total_attempts, correct_attempts, last_error_type, mastery_level (unknown/learning/improving/mastered), updated_at
- **attempt_events**: student_id, worksheet_id, attempt_id, question, student_answer, grade_result, mastery_before/after, ts. Gated by `ENABLE_ATTEMPT_AUDIT_DB=1`
- **telemetry_events**: event, route, version, student_id, skill_tag, error_type, latency_ms, ok, ts. Gated by `ENABLE_TELEMETRY_DB=1`
- All tables use **Row-Level Security (RLS)** with Supabase Auth policies. Schema in `backend/supabase_schema.sql`

# Environment & Deployment

- **Required env**: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`), `OPENAI_API_KEY`
- **Optional env**: `DEBUG` (default false), `FRONTEND_URL` (default `http://localhost:5173`)
- **Feature flags**: `ENABLE_TELEMETRY_DB=1`, `ENABLE_ATTEMPT_AUDIT_DB=1`, `PRACTICECRAFT_MASTERY_STORE=supabase` (default `memory`)
- **Frontend env**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (default `http://localhost:8000`)
- **Deployment**: Railway (backend, `backend/railway.json`), Vercel (frontend, `ed-tech-drab.vercel.app`)

# Known Issues

## Incomplete Features
- `subscription.py:upgrade_to_paid()` — no payment verification (Stripe/Razorpay placeholder)
- `syllabus.py:parse_syllabus()` — returns raw_response only; no structured parsing
- `syllabus.py:get_syllabus()` — returns "not implemented yet"

## Silent Failures (bare except)
- `audit.py:write_attempt_event()` — `except Exception: return` with no logging
- `telemetry.py:emit_event()` — `except Exception: pass` on DB write
- `mastery_store.py:get_mastery_store()` — Supabase init failure silently falls back to in-memory
- `worksheets_v1.py:attempt_v1()` — two `except Exception: pass` blocks
- `slot_engine.py` — multiple silent skips in slot building, mastery update, LLM retry

## Degraded Output (best-effort)
- Failed generation after 3 retries inserts `"[Generation failed for {slot_type} question]"` stub
- `enforce_slot_counts()` synthesizes filler with `"[Slot fill]"` marker
- Difficulty auto-escalates easy→medium if sanity check fails
- Contract repair failure → regen → if regen fails, keeps original invalid question

## Frontend Silent Failures
- `subscription.tsx` — fetch failure silently downgrades to free tier
- `engagement.tsx` — completion recording failure returns null
- `profile.tsx` — fetch failure clears profile to null
- `api.ts` — v1 500 silently falls back to legacy API

## Legacy Code (dead but present)
- `worksheets.py`: `build_system_prompt()`, `_fixup_question_types()`, `_fix_computational_answers()`, `_fix_inconsistent_visuals()` — not called from main pipeline

# Claude Operating Rules

- **Deterministic-first**: Backend owns structure (slot plans, variants, validation). LLM fills content only. All post-generation fixes must be deterministic — no LLM calls for repair.
- **No silent fallback**: Every `except` block must log. Never swallow errors with bare `pass`.
- **Contracts override generation**: If a skill contract exists, its `validate()` → `repair()` → regen cycle takes precedence.
- **Slot discipline is mandatory**: Slot counts must exactly match the plan. `enforce_slot_counts()` is the last resort.
- **Visual coverage must be 100%**: Every question with `representation="PICTORIAL_MODEL"` must have valid `visual_spec.model_id` and `visual_model_ref`.
- **Never relax carry/borrow enforcement**: `has_carry()`/`has_borrow()` checks are non-negotiable. Fallback to hardcoded CARRY_PAIRS.
- **Update CLAUDE.md on commit**: Before every commit, update the `# Update Log` section with a meaningful one-line summary. The pre-commit hook adds file paths; replace with human-readable description.
- **shadcn/ui install path**: shadcn CLI installs to `frontend/@/components/ui/` (wrong) — must manually move to `frontend/src/components/ui/`
- **Always grep after `replace_all` edits**: Stale references cause NameError at runtime.
- **Regex patterns at module level**: All regex patterns must be defined BEFORE functions that use them.

# Update Log

- **2026-02-12**: Initial documentation. v1.3 multi-skill bundle, skill purity enforcement, add/sub expansion, role-based explanations, estimation visual highlight fix.
- **2026-02-16**: Multi-topic worksheet engine for all Class 3 maths topics. Topic-specific VALID_FORMATS, instruction builders, dedup guards, verify_topics.py.
- **2026-02-17**: Combined add/sub profile with recipes_by_count, enhanced instruction builders, dedup tracking.
- **2026-02-17**: Fix combined add/sub to generate 10 mixed questions in single worksheet (removed from UI_SKILL_TO_CONTRACTS, pass topic to build_worksheet_plan, add thinking to recipes_by_count).
- **2026-02-17**: Phase 1 — Fix the Foundation. Backend: replaced 10 bare except blocks with proper logging across audit, telemetry, mastery_store, worksheets_v1, slot_engine. Fixed _scale_recipe() bug causing incorrect 5-question worksheets. Frontend: added console.warn logging for silent failures in subscription, engagement, profile, api fallback. QA: new test_all_topics.py (48 combinations, 80 checks). Fixed stale test_add_sub_expansion test.
- **2026-02-17**: Phase 3 — Content Expansion. Syllabus: hardcoded CBSE syllabus endpoint GET /api/syllabus/cbse/{grade}/{subject} for Class 1-5 Maths & English (no DB needed). Topics: added 10 Class 2 + 10 Class 4 Maths topic profiles (32 total). 110+ new skill tags, aliases, constraints, and instruction builders. Test suite now covers 128 combinations (200 checks).
- **2026-02-17**: Phase 4 — Production Hardening. Marked 4 dead functions in worksheets.py. Added subscription enforcement (10/month free tier, fail-open on DB errors) via shared subscription_check.py. Frontend: new History page with filters, pagination, PDF download, empty/loading/error states.
- **2026-02-17**: Phase 5+6 — Teacher features + QoL. Backend: POST /api/v1/worksheets/bulk for parallel multi-topic generation (paid only, max 5 topics × 3 each, asyncio.gather). Frontend: answer key show/hide toggle with eye icon, PDF export respects toggle state (full vs student mode).
- **2026-02-17**: Phase 9 Gold-G8 — Premium PDF redesign. Backend: rewrote pdf.py with tiered difficulty sections (Foundation/Application/Stretch), Name/Date/Score header, professional footer with page numbers + branding, 2cm margins, hint text for thinking/ED questions, alternate-row answer key shading. Frontend: added tier grouping to worksheet view based on question role field, print-only Name/Date/Score header, Nunito font import for child-friendly print typography, updated print CSS to 20mm margins.
- **2026-02-17**: Phase 9 Gold-G5 — Learning Objective Header. Added LEARNING_OBJECTIVES dict (32 topics, 3 objectives each) + get_learning_objectives() to slot_engine.py. Added learning_objectives field to Worksheet/WorksheetV1 models and wired into all 4 generation endpoints. Frontend: styled "Today's Learning Goal" box with checkmarks above instructions. PDF: bordered objective box rendered below title.
- **2026-02-17**: Phase 9 Gold-G6 — Hint System. Frontend: collapsible "Show Hint" button on thinking and error_detection questions. Click reveals hint in warm amber box. In print mode, revealed hints render as subtle grey boxes. No backend changes — data already exists in explanation field.
- **2026-02-17**: Phase 9 Gold-G1 — Tiered Difficulty with Star Badges. Frontend: star badges (1/2/3 stars) below question numbers in tiered view indicating Foundation/Application/Stretch. PDF: star badges rendered inline next to question numbers in amber accent colour. Tier headers + sorting already done in G8.
- **2026-02-17**: Phase 9 Gold-G3 + Gold-G4 — Indian context bank (32 topics × 10 contexts) + 5 new SVG visual types (pie_fraction, grid_symmetry, money_coins, pattern_tiles, abacus) with backend hydration rules.
- **2026-02-17**: Phase 9 Gold-G2 — Mastery-aware slot plan modifier. `_get_mastery_for_topic()` aggregates mastery states; `adjust_slot_plan_for_mastery()` boosts thinking for mastered / recognition for learning; `_ERROR_TYPE_CONSTRAINTS` injects targeted practice. `child_id` flows through all generation endpoints. Frontend: mastery badge on personalised worksheets.
- **2026-02-17**: Phase 9 Gold-G7 — Parent Insight Footer. Backend: `WATCH_FOR_MESSAGES` (10 error types) and `NEXT_STEP_MESSAGES` (4 levels, topic-specific) + `build_parent_insight()` injected into attempt response. `ParentInsight` model added to AttemptResponse. Frontend: insight footer on worksheet with watch-for, next-step, mastery progress bar + streak.
- **2026-02-17**: Phase 9 Gold-G3 — Indian Context Word Problems. Added TOPIC_CONTEXT_BANK (32 topics × 10 contexts each) with rich Indian scenarios (cricket, Diwali, mela, auto-rickshaw, etc.). Injected into _build_slot_instruction() for application slots — LLM uses Indian names and contexts instead of generic problems.
- **2026-02-17**: Phase 9 Gold-G4 — Rich Visual Types. Backend: 5 new hydration rules in hydrate_visuals() for PIE_FRACTION, GRID_SYMMETRY, MONEY_COINS, PATTERN_TILES, ABACUS — mapped by question format. Added to _MODEL_TO_VTYPE. Frontend: 5 new SVG components (PieFractionVisual, GridSymmetryVisual, MoneyCoinsVisual, PatternTilesVisual, AbacusVisual) in VisualProblem.tsx — all print-safe, B&W friendly, accessible.
- **2026-02-17**: Phase 7 — English Language Engine. Multi-subject support: 22 English topic profiles (6 Class 2, 8 Class 3, 8 Class 4) with VALID_FORMATS_ENGLISH, subject-aware validate_question/enforce_slot_counts/backfill_format, QUESTION_SYSTEM_ENGLISH prompt, 80+ eng_* skill tags, 15 instruction builder blocks, 45 aliases, 22 constraints/objectives/context banks. Frontend: grade-aware English topic selector. Zero Maths regression (709+282 deterministic checks pass).
- **2026-02-17**: Phase 10A — Maths Class 1 (8 topics). Backend: 8 new topic profiles (Numbers 1-50, Numbers 51-100, Addition up to 20, Subtraction within 20, Basic Shapes, Measurement, Time, Money) with strict grade constraints (sums ≤20, no carry/borrow, no standard units, coins only). 40 skill tags, 30 aliases, 8 constraints, 8×3 learning objectives, 8×10 Indian context bank entries, 8 instruction builder blocks. Frontend: grade-aware Maths topic selector + Class 1 on landing page. QA: test_class1_maths.py (82 checks). verify_topics: 909 passed.
- **2026-02-17**: Phase 10B+10C+10D — Maths Class 2 guardrails, Class 4 completion, Class 5 (10 new topics). Backend: Added missing _TOPIC_CONSTRAINTS for 3 arithmetic topics (Class 2 add/sub, Class 4 add/sub). Added 10 new Class 5 topic profiles (Numbers up to 10 lakh, Factors & Multiples, HCF & LCM, Fractions add/sub, Decimals all ops, Percentage, Area & Volume, Geometry circles/symmetry, Data handling pie charts, Speed distance time). 50 new skill tags, 38 aliases, 10 constraints, 30 learning objectives, 100 Indian context bank entries, 10 instruction builder blocks. Frontend: Class 5 Maths topics in grade selector + landing page. QA: test_class2/4/5_maths.py (99+101+98=298 checks). verify_topics: 1009 passed.
- **2026-02-17**: Phase 8 — Science Engine. 7 Class 3 Science topic profiles (Plants, Animals, Food and Nutrition, Shelter, Water, Air, Our Body) with VALID_FORMATS_SCIENCE (18 formats), QUESTION_SYSTEM_SCIENCE prompt, 35 sci_* skill tags, 7 instruction builder blocks, 25 aliases, 7 constraints/objectives/context banks (Indian contexts). Frontend: grade-aware Science topic selector. Pipeline: text-only rendering (like English), reuses text answer normalizer. QA: 169-check test suite (28 combinations), zero regression (779+282+169 = 1,230 deterministic checks pass).
- **2026-02-17**: P2 Growth Features — 3 parallel features. (1) Parent Progress Dashboard: rewrote dashboard_service.py to work without missing DB views (graceful fallback to worksheets table), new ParentDashboard.tsx with stats cards + skill progress table + recent topics, "Progress" tab in parent nav. (2) WhatsApp Share: new share.py router (POST /api/worksheets/{id}/share + GET /api/shared/{token}), share_tokens table, WhatsApp + copy-link buttons in worksheet toolbar, SharedWorksheet.tsx public viewer with no-auth route. (3) Hindi Language Engine: 5 Class 3 Hindi topic profiles (Varnamala, Matras, Shabd Rachna, Vakya Rachna, Kahani Lekhan) with VALID_FORMATS_HINDI (17 formats), QUESTION_SYSTEM_HINDI (Devanagari script), 25 hin_* skill tags, 5 instruction builders, 21 aliases, 5 constraints/objectives/context banks. QA: 138-check test suite, zero regression (829+282+169+138 = 1,418 checks pass).
- **2026-02-17**: Fixed teacher routing bug (isTeacherPage missing generator) and free tier silent blocking — users now see remaining count and upgrade prompt before generation, generate button replaced with upgrade CTA at limit. E2E test suite: 26/26 pass.
- **2026-02-17**: Phase 11A — English Class 1 (7 topics). Backend: 7 new English topic profiles (Alphabet, Phonics, Self and Family Vocabulary, Animals and Food Vocabulary, Greetings and Polite Words, Seasons, Simple Sentences) with subject="English", grade constraints (3-letter CVC words, no grammar rules, picture-based). 35 eng_c1_* skill tags, 28 aliases, 7 constraints, 21 learning objectives, 70 Indian context bank entries, 7 instruction builder blocks. Frontend: Class 1 English in grade selector + landing page. QA: test_class1_english.py (77 checks). verify_topics: 1079 passed. Total: 91 topic profiles.
- **2026-02-17**: World-class landing page (Landing.tsx). 12 sections: sticky nav, hero with animated underline + floating worksheet preview, social proof bar, problem statement, Gold Class 6-step tabbed stepper, subjects explorer (66 topics across Maths/English/Science), comparison table vs free tools, parent/teacher cards, pricing (Free + ₹299/mo), philosophy, final CTA, footer. Playfair Display serif headings, academic dot-grid pattern, IntersectionObserver scroll-reveal animations, mobile-responsive. Replaces old LandingPage.tsx. 26/26 E2E pass, zero lint errors.
- **2026-02-17**: Phase 11B — English Class 5 (9 topics). Backend: 9 new English topic profiles (Active and Passive Voice, Direct and Indirect Speech, Complex Sentences, Summary Writing, Comprehension, Synonyms and Antonyms, Formal Letter Writing, Creative Writing, Clauses) with subject="English", advanced grade constraints. 45 eng_c5_* skill tags, 33 aliases, 9 constraints, 27 learning objectives, 90 Indian context bank entries, 9 instruction builder blocks. QA: test_class5_english.py (99 checks). Total: 103 profiles.
- **2026-02-17**: Phase 12A — EVS Class 1 & 2 (12 topics). Backend: 12 new Science topic profiles (6 Class 1: My Family, My Body, Plants Around Us, Animals Around Us, Food We Eat, Seasons and Weather; 6 Class 2: Plants, Animals and Habitats, Food and Nutrition, Water, Shelter, Our Senses) with subject="Science", EVS-specific constraints (disallow maths keywords). 60 sci_c1_*/sci_c2_* skill tags, 53 aliases, 12 constraints, 36 learning objectives, 120 Indian context bank entries, 12 instruction builder blocks. Frontend: EVS Class 1 & 2 in Science grade selector + landing page. QA: test_class12_evs.py (132 checks). verify_topics: 1289 passed. Total: 112 topic profiles.

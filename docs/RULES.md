# RULES.md — Load this file only when working on the pipeline, validators, visual rendering, skill contracts, or debugging known issues

# Worksheet Generation Pipeline

Core file: `backend/app/services/slot_engine.py` — two-phase generation.
API endpoint: `backend/app/api/worksheets.py` calls `run_slot_pipeline()`.

## Pipeline Order
`generate_meta` (1 LLM call) → `get_slot_plan` → per-question generate+validate (N calls, 3 retries each) → `validate_worksheet_slots` → map to API response

## Per-Question Schema (internal)
`{format, question_text, pictorial_elements:[], answer}` — LLM fills content only, backend controls slot_type/difficulty.

---

# Validators

## Per-question (`validate_question`)
- Format must be in VALID_FORMATS (subject-aware via `get_valid_formats()`)
- No visual phrases in question_text (Maths only)
- Non-empty answer
- Question text ≥ 10 chars
- `error_detection` needs error language + 2 numbers (Maths) or grammar error language (English)
- `representation` needs blank markers (`___`)
- `thinking` needs reasoning language
- `pictorial_elements` must be empty

## Worksheet-level (`validate_worksheet_slots`)
- Slot counts match plan exactly
- ED ≥ 1 and T ≥ 1 always
- Unique number pairs (no duplicate problem setups)
- No duplicate question text
- No repeated contexts in application questions

## Safety net (`enforce_slot_counts`)
- Deterministic trim/fill
- Re-numbers IDs 1→N
- Last resort only; filler uses `"[Slot fill]"` marker

## Answer Normalizers
- `normalize_estimation_answers` — recomputes closer-to/round-to sums deterministically
- `normalize_error_spot_answers` — extracts numeric answer from LLM explanatory text
- `normalize_english_answers` — cleans up text answers for English subjects

---

# Skill System

- **Registry**: `backend/app/skills/registry.py` — read-only `SKILL_REGISTRY` mapping skill_tag → contract instance
- **3 contracts**: `column_add_with_carry`, `column_sub_with_borrow`, `multiplication_table_recall`
- **Base class**: `backend/app/skills/base.py` — abstract interface: `build_variant()`, `validate()`, `build_slots()`, `repair()`, `explain()`, `grade()`, `recommend_next()`, `generate_drill()`
- **Carry/borrow enforcement**: 15 precomputed CARRY_PAIRS. `make_carry_pair(rng, op)` with 50-retry + hardcoded fallback. `has_carry()`/`has_borrow()` checks are non-negotiable.
- **Error computation**: `compute_wrong(a, b, tag)` produces deterministic wrong answers for 5 misconception tags

## Multi-Skill Bundle (v1.3)
`UI_SKILL_TO_CONTRACTS` in `worksheets.py` maps UI skill labels → contract keys. When `request.skills` produces 2+ expanded entries, the bundle path splits `num_questions` across skills and generates separate worksheets with purity enforcement.

**Important**: "Addition and subtraction (3-digit)" is intentionally NOT in `UI_SKILL_TO_CONTRACTS`. It uses `slot_engine.py`'s topic profile recipe to produce a single mixed worksheet.

---

# Visual Rendering

## Data Flow
LLM generates `question_text` → `hydrate_visuals()` (deterministic regex) → sets `representation`, `visual_spec`, `visual_model_ref` → `_map_visual_fields()` → API `visual_type`/`visual_data` → frontend `VisualProblem` renders SVG

## Hydration Rules (priority order)
1. blank markers + 2 ints → `NUMBER_LINE`
2. closer-to / estimate → `NUMBER_LINE`
3. add/subtract + 2 ints → `BASE_TEN_REGROUPING`
4. fraction format → `PIE_FRACTION`
5. symmetry format → `GRID_SYMMETRY`
6. money format → `MONEY_COINS`
7. pattern format → `PATTERN_TILES`
8. abacus format → `ABACUS`
9. else → `TEXT_ONLY`

## Frontend Visual Components
| visual_type | Component |
|---|---|
| `number_line` | `NumberLineVisual` |
| `base_ten_regrouping` | `BaseTenRegroupingVisual` (H/T/O digit inputs) |
| `clock` | `ClockVisual` |
| `object_group` | `ObjectGroupVisual` |
| `shapes` | `ShapeVisual` |
| `pie_fraction` | `PieFractionVisual` |
| `grid_symmetry` | `GridSymmetryVisual` |
| `money_coins` | `MoneyCoinsVisual` |
| `pattern_tiles` | `PatternTilesVisual` |
| `abacus` | `AbacusVisual` |

## Visual Coverage
- `enforce_visuals_only()` replaces TEXT_ONLY with synthetic BASE_TEN_REGROUPING until ≥80% visual coverage
- Every question with `representation="PICTORIAL_MODEL"` must have valid `visual_spec.model_id` and `visual_model_ref`

## Role-based Explanations
`_fill_role_explanations()` adds deterministic explanations for `thinking` and `error_detection` roles only. Capped at 160 chars.

---

# Extended Claude Operating Rules

1. **Deterministic-first**: Backend owns structure (slot plans, variants, validation). LLM fills content only. All post-generation fixes must be deterministic — no LLM calls for repair.
2. **No silent fallback**: Every `except` block must log. Never swallow errors with bare `pass`.
3. **Contracts override generation**: If a skill contract exists, its `validate()` → `repair()` → regen cycle takes precedence.
4. **Slot discipline is mandatory**: Slot counts must exactly match the plan. `enforce_slot_counts()` is the last resort.
5. **Visual coverage must be 100%**: Every question with `representation="PICTORIAL_MODEL"` must have valid `visual_spec.model_id` and `visual_model_ref`.
6. **Never relax carry/borrow enforcement**: `has_carry()`/`has_borrow()` checks are non-negotiable. Fallback to hardcoded CARRY_PAIRS.
7. **Update CLAUDE.md on commit**: Before every commit, update `docs/CHANGELOG.md` with a meaningful one-line summary. The pre-commit hook adds file paths; replace with human-readable description.
8. **shadcn/ui install path**: shadcn CLI installs to `frontend/@/components/ui/` (wrong) — must manually move to `frontend/src/components/ui/`
9. **Always grep after `replace_all` edits**: Stale references cause NameError at runtime.
10. **Regex patterns at module level**: All regex patterns must be defined BEFORE functions that use them.

---

# Known Issues

## Silent Failures (bare except — still present)
- `audit.py:write_attempt_event()` — `except Exception: return` with no logging
- `telemetry.py:emit_event()` — `except Exception: pass` on DB write
- `mastery_store.py:get_mastery_store()` — Supabase init failure silently falls back to in-memory
- `worksheets_v1.py:attempt_v1()` — two `except Exception: pass` blocks
- `slot_engine.py` — multiple silent skips in slot building, mastery update, LLM retry

## Degraded Output (best-effort stubs)
- Failed generation after 3 retries inserts `"[Generation failed for {slot_type} question]"` stub
- `enforce_slot_counts()` synthesizes filler with `"[Slot fill]"` marker
- Difficulty auto-escalates easy→medium if sanity check fails
- Contract repair failure → regen → if regen fails, keeps original invalid question

## Frontend Silent Failures
- `subscription.tsx` — fetch failure silently downgrades to free tier
- `engagement.tsx` — completion recording failure returns null
- `profile.tsx` — fetch failure clears profile to null
- `api.ts` — v1 500 silently falls back to legacy API

## Legacy Code (dead but present in `worksheets.py`)
- `build_system_prompt()` — not called from main pipeline
- `_fixup_question_types()` — not called from main pipeline
- `_fix_computational_answers()` — not called from main pipeline
- `_fix_inconsistent_visuals()` — not called from main pipeline (auto-migrates old schemas columns→cols, jump_size→jumps[])

---

# Mastery-Aware Generation

- `_get_mastery_for_topic()` — aggregates mastery states for a child + topic
- `adjust_slot_plan_for_mastery()` — boosts thinking slots for mastered topics; boosts recognition for learning topics
- `_ERROR_TYPE_CONSTRAINTS` — injects targeted practice based on last error type
- `child_id` flows through all generation endpoints; frontend shows mastery badge on personalised worksheets

# Parent Insight System
- `WATCH_FOR_MESSAGES` (10 error types) + `NEXT_STEP_MESSAGES` (4 levels, topic-specific)
- `build_parent_insight()` injected into attempt response
- Frontend: insight footer with watch-for, next-step, mastery progress bar + streak

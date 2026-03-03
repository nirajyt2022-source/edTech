# Plan: Worksheet Quality Scoring Engine

## Context

The backend has 4 validation layers that run **during** generation (OutputValidator → QualityReviewer → DifficultyCalibrator → ReleaseGate). These catch/fix issues in real-time but there's no way to:
- Score an already-generated worksheet with a single **0–100 number**
- Get **structured failure reasons** with dimension breakdowns
- **Block PDF export** for low-quality worksheets
- Surface **AI-smell patterns** as a first-class scoring dimension

This engine adds a standalone, deterministic scoring layer that **reuses existing validators** without duplicating logic.

---

## Files

### New files
| File | Purpose |
|---|---|
| `backend/app/services/quality_scorer.py` | Entire scoring engine (~350 lines) |
| `backend/tests/test_quality_scorer.py` | Unit + integration tests (~200 lines) |

### Modified files
| File | Change |
|---|---|
| `backend/app/models/worksheet.py` L128 | Add `quality_score: float \| None = None` to `WorksheetGenerationResponse` |
| `backend/app/api/worksheets_v2.py` L151-158 | Compute + attach `quality_score` to generation response |
| `backend/app/api/saved_worksheets.py` L230-303 | Replace log-only quality gate with score-based export gate; add `GET /{id}/quality-score` endpoint |
| `backend/app/core/config.py` L6-38 | Add `worksheet_export_min_score: int = 40` to `Settings` |

---

## Scoring Algorithm

### 5 Dimensions (weighted to 100)

| Dimension | Weight | Key Checks |
|---|---|---|
| **Structural** | 20 | Question count matches, every Q has text + answer, valid types, MCQ has options + answer in options, T/F answers valid |
| **Content Accuracy** | 25 | No `_math_unverified` flags (0.20/ea), no `is_fallback` stubs (0.20/ea), no empty answers (0.15/ea), no self-contradictions (0.20/ea), no disallowed keywords |
| **Pedagogical Design** | 20 | Role distribution ≥3 types for 10+ Qs, no single type >40%, skill tag diversity ≥2, has error_detection/thinking Qs, hint coverage ≥50% |
| **Anti-AI-Smell** | 20 | Exact duplicates, near-duplicates (template similarity), opening verb repetition (>2×), round number overuse (>30%), LLM artifacts ("As an AI…"), placeholder stubs ("[Generation failed"), scenario repeats, object reuse, sentence structure monotony, filler phrases |
| **Curriculum Alignment** | 15 | `learning_objectives` present, `chapter_ref` present, `skill_focus` present, skill tags valid per topic profile, grade-appropriate vocabulary + length |

### Formula
Each dimension starts at `raw = 1.0`. Deductions per failed check (capped at 0.0 floor).
`total = Σ(raw × weight)` → 0–100.

### Deduction Severity
- **Critical** (0.20–0.25): unverified math, fallback stubs, LLM artifacts, exact duplicates
- **Major** (0.10–0.20): near-duplicates, missing answers, role gaps, missing count
- **Minor** (0.05–0.10): missing chapter_ref, filler phrases, low hint coverage

---

## Key Design: Reuse OutputValidator

Call `OutputValidator.validate_worksheet()` **once**, then classify its error strings into dimensions via regex:

```python
_ERROR_CLASSIFIERS = [
    (r"\[count_mismatch\]",           "structural",  "STRUCT_01", "critical", 0.30),
    (r"empty question text",           "structural",  "STRUCT_02", "critical", 0.15),
    (r"missing correct_answer",        "structural",  "STRUCT_03", "major",    0.10),
    (r"MCQ needs at least",            "structural",  "STRUCT_04", "major",    0.10),
    (r"MCQ answer .* not in options",  "structural",  "STRUCT_05", "major",    0.10),
    (r"true_false answer must be",     "structural",  "STRUCT_07", "minor",    0.05),
    (r"Duplicate question detected",   "ai_smell",    "AI_01",     "critical", 0.25),
    (r"Near-duplicate pattern",        "ai_smell",    "AI_02",     "major",    0.20),
    (r"Opening verb .* repeats",       "ai_smell",    "AI_03",     "minor",    0.10),
    (r"Round number overuse",          "ai_smell",    "AI_04",     "minor",    0.10),
    (r"Number pair monotony",          "ai_smell",    "AI_05",     "minor",    0.10),
    (r"Countable object .* appears",   "ai_smell",    "AI_09",     "minor",    0.05),
    (r"Sentence structure monotony",   "ai_smell",    "AI_10",     "minor",    0.10),
    (r"filler phrase",                 "ai_smell",    "AI_11",     "minor",    0.05),
    (r"Scenario .* repeated",          "ai_smell",    "AI_07",     "minor",    0.10),
    (r"Number .* appears in .* questions","ai_smell", "AI_09B",    "minor",    0.05),
    (r"No engagement framing",         "ai_smell",    "AI_12",     "minor",    0.05),
    (r"Sequence step monotony",        "ai_smell",    "AI_13",     "minor",    0.05),
    (r"complex vocabulary",            "curriculum",  "CUR_04",    "minor",    0.05),
    (r"question too long",             "curriculum",  "CUR_05",    "minor",    0.05),
    (r"disallowed keyword",            "content",     "CONTENT_07","minor",    0.05),
    (r"Type diversity",                "pedagogical", "PED_02",    "major",    0.15),
    (r"math answer appears incorrect", "content",     "CONTENT_08","major",    0.15),
    (r"visual data does not match",    "content",     "CONTENT_05","major",    0.15),
    (r"visual type .* is disallowed",  "content",     "CONTENT_09","minor",    0.05),
]
```

Then run **supplementary checks** for things OV doesn't cover:
- Internal flags (`_math_unverified`, `_answer_corrected`, `is_fallback`) → Content
- `_contains_llm_artifact()` from `quality_reviewer.py` L506 → AI-Smell
- Placeholder regex (`[Generation failed`, `[Slot fill]`) → AI-Smell
- Worksheet-level fields (`learning_objectives`, `chapter_ref`, `skill_focus`) → Curriculum
- Role distribution, hint coverage, skill tag diversity → Pedagogical

---

## Data Models (`quality_scorer.py`)

```python
@dataclass
class FailureReason:
    dimension: str          # "structural" | "content" | "pedagogical" | "ai_smell" | "curriculum"
    check_id: str           # "STRUCT_01", "AI_06", etc.
    severity: str           # "critical" | "major" | "minor"
    message: str
    question_ids: list[str] # Affected Qs (empty for worksheet-level checks)
    points_deducted: float

@dataclass
class DimensionResult:
    name: str
    weight: int
    raw_score: float        # 0.0–1.0
    weighted_score: float   # raw_score × weight
    failures: list[FailureReason]

@dataclass
class QualityScore:
    total_score: float                      # 0–100
    dimensions: dict[str, DimensionResult]
    failures: list[FailureReason]           # All failures flat
    export_allowed: bool
    export_threshold: int
    ai_smell_flags: list[FailureReason]     # Convenience: just AI-smell
    question_count: int
    grade: str
    subject: str
```

---

## Public API: `score_worksheet()`

```python
def score_worksheet(
    worksheet: dict,
    *,
    expected_count: int | None = None,
    export_threshold: int | None = None,
) -> QualityScore:
```

Standalone, no side effects. Takes any worksheet dict (from pipeline, from DB, from API).

---

## Integration Points

### 1. Generation response (`worksheets_v2.py` L151-158)

After building response, before return:
```python
from app.services.quality_scorer import score_worksheet
qs = score_worksheet(data)  # data still has internal flags like _math_unverified
# Add quality_score=qs.total_score to response
```

`WorksheetGenerationResponse` gets new field: `quality_score: float | None = None`

### 2. PDF export gate (`saved_worksheets.py` L239-263)

Replace the log-only quality gate block with:
```python
from app.services.quality_scorer import score_worksheet
score = score_worksheet(worksheet_dict)
if not score.export_allowed:
    raise HTTPException(status_code=422, detail={
        "error": "quality_below_threshold",
        "total_score": score.total_score,
        "threshold": score.export_threshold,
        "top_failures": [...top 5 by points_deducted...],
        "dimensions": {name: weighted_score for each},
    })
```

### 3. New endpoint (`saved_worksheets.py`)

```
GET /api/saved-worksheets/{worksheet_id}/quality-score
```
Returns full QualityScore as JSON.

### 4. Config (`config.py`)

```python
worksheet_export_min_score: int = 40
```
Env var: `WORKSHEET_EXPORT_MIN_SCORE`. Default 40 — blocks worksheets with multiple critical failures but passes worksheets with only minor issues.

---

## Verification

```bash
# Tests
cd backend && python -m pytest tests/test_quality_scorer.py -v

# Import checks
cd backend && python -c "from app.services.quality_scorer import score_worksheet; print('OK')"
cd backend && python -c "from app.api.saved_worksheets import router; print('OK')"
cd backend && python -c "from app.api.worksheets_v2 import router; print('OK')"

# Manual: generate worksheet → check quality_score in response JSON
# Manual: export PDF for good worksheet → succeeds
# Manual: craft bad worksheet → export returns 422 with score breakdown
```

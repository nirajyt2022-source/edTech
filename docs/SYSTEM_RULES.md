# System Rules — Operational Principles

These are enforcement rules, not guidelines. Every rule maps to running code.

---

## 1. ENFORCED AT GENERATION TIME

These constraints are injected into the LLM prompt. The LLM is expected to comply; violations trigger retry with strengthened prompts.

### Content Boundaries

- **G-01** Every question must be about the given topic only. No cross-topic bleed.
- **G-02** All content must be age-appropriate for the given class level.
- **G-03** NCERT/CBSE curriculum standards must be followed for the given class and subject.
- **G-04** Every question must have a correct answer. For maths, the answer must be arithmetically computed.
- **G-05** No two consecutive questions may start with the same word.
- **G-06** All monetary values use ₹. All names, cities, festivals, and contexts are Indian.
- **G-07** No scenario may repeat within one worksheet. Rotate through: home, school, market, park, farm, zoo, kitchen, playground, festival, hospital, train station.

### Structure Rules

- **G-08** MCQ questions must have exactly 4 options (unless explicitly 3 or 5 per the MCQ variety directive).
- **G-09** Fill-in-the-blank questions must contain `______` in the text.
- **G-10** True/False questions must have `options: ["True", "False"]`.
- **G-11** Every question must have a `hint` field that guides without revealing the answer.
- **G-12** Every question must have a `skill_tag` field from the provided tag recipe.
- **G-13** Question text must be self-contained. Never write "look at the image/picture".

### Difficulty Distribution

- **G-14** Easy worksheets: 60% Foundation, 30% Application, 10% Stretch.
- **G-15** Medium worksheets: 30% Foundation, 50% Application, 20% Stretch.
- **G-16** Hard worksheets: 10% Foundation, 30% Application, 60% Stretch.
- **G-17** Within each tier, start with smaller numbers and progress to larger ones.

### Subject-Specific

- **G-18** Fraction topics: every question must contain a fraction. No whole-number arithmetic.
- **G-19** Hindi worksheets: all content in Devanagari script. Never transliterated Hindi.
- **G-20** Hindi register: spoken, child-friendly Hindi. No textbook-formal vocabulary.
- **G-21** Maths medium/hard: chain-of-thought enabled (thinking_budget=1024). LLM must verify arithmetic before committing.

### Variety Directives

- **G-22** MCQ option counts: ~70% with 4 options, ~20% with 3, ~10% with 5.
- **G-23** Word problem sentence count: vary between 2, 3, and 4+ sentences.
- **G-24** Skill tag recipe: exact count per tag type, derived from slot plan. No deviation.

### Retry Triggers (up to 3 attempts)

- **G-R1** Topic drift detected → strengthen topic constraint.
- **G-R2** Near-duplicate questions detected → add negative prompt with repeated templates.
- **G-R3** Unknown question type → add explicit allowed types list.
- **G-R4** Count mismatch → add "EXACTLY N questions" directive.
- **G-R5** >2 unverifiable maths answers → add "show your working" directive.
- **G-R6** JSON parse failure → add "respond with ONLY valid JSON".
- **G-R7** Release Gate verdict = blocked → feed block reasons back into prompt.

---

## 2. VALIDATED BEFORE EXPORT

These checks run after the LLM returns. They correct, degrade, or block. Nothing reaches the user without passing this pipeline.

### Quality Reviewer (10 checks, deterministic correction)

- **V-01** Maths arithmetic: extract expression, safe AST eval, auto-correct if wrong. Mark `_answer_corrected=True`. If eval fails: mark `_math_unverified=True`. **HARD BLOCK path.**
- **V-02** Skill tag: if tag not in valid set, replace with first valid tag.
- **V-03** Word count: Class 1-2 max 15 words, Class 3-5 max 25 words. Log warning only.
- **V-04** Fraction/decimal format: catch decimal storage for fraction answers, wrong-magnitude decimals, error_detection answers that agree with the wrong value.
- **V-05** Time facts: fill-in-the-blank time questions must match known constants (60 sec/min, 24 hrs/day, 7 days/week, 12 months/year, 365 days/year, 52 weeks/year).
- **V-06** Hint leakage: if hint contains "the answer is..." or 3+ consecutive words from the answer, null the hint.
- **V-07** Self-contradiction in thinking answers: if both "more than X" and "less than X" appear, or "my initial reasoning was incorrect", mark `_needs_regen=True`.
- **V-08** Word problem arithmetic: same as V-01 but for multi-number word problems. **HARD BLOCK path.**
- **V-09** LLM artifacts: "as an AI", "here's a", "let me", "I'll help" → null the hint if found.
- **V-10** Hindi purity: flag Devanagari text containing 2+ Latin-script characters. Log warning only.

### Release Gate (10 rules, 3 enforcement levels)

**BLOCK — worksheet cannot ship:**

- **R-01** Maths: zero questions may have `_math_unverified=True`.
- **R-02** Every question type must be in `{mcq, fill_blank, true_false, short_answer, word_problem, error_detection}`.
- **R-05** Non-bonus question count must be ≥ requested−1 (for 10+) or exact (for <10).
- **R-08** Maximum 2 combined serious issues (unverified, needs_regen, empty_text, missing_answer) across non-bonus questions.

**DEGRADE — worksheet ships with "best_effort" verdict:**

- **R-03** No format category may drift >15 percentage points from target mix.
- **R-04** Curriculum data must be available. No "[curriculum] unavailable" warnings.
- **R-07** Maths: ≤20% of word problems with 4+ numbers may lack `_answer_corrected`.
- **R-09** All skill tags must be in the valid set. No single tag may exceed 60% when 3+ tags are available.

**STAMP — metadata attached, always passes:**

- **R-06** Stamp `adaptive_fallback` and `adaptive_source` on every worksheet.
- **R-10** Classify warnings into critical (×3), moderate (×2), info (×1). Compute severity score. Stamp `quality_tier`: low (any critical or score≥10), medium (any moderate or score≥4), high (otherwise).

### Response Validator (7 checks, schema enforcement)

- **V-11** JSON must parse. Markdown fences stripped automatically.
- **V-12** Every question must have `text` and `correct_answer`.
- **V-13** Unknown types default to `short_answer`.
- **V-14** MCQ without options → downgrade to `short_answer`. MCQ answer must be in options list.
- **V-15** True/False auto-detection: if options look boolean, set type and fix options.
- **V-16** Visual type aliases remapped (clock_face→clock, fraction_bar→pie_fraction). Visuals missing required fields stripped.
- **V-17** Phantom image references ("look at the image") stripped when no visual/image present.

### Output Validator (18 checks, advisory logging)

- **V-18** Exact duplicate detection (normalized whitespace).
- **V-19** Near-duplicate detection (template-based, ≥50% structural overlap).
- **V-20** Grade appropriateness: Class 1-2 text <40 words, no complex vocabulary.
- **V-21** Type diversity: no single type >40% of worksheet.
- **V-22** Disallowed keywords from topic profile.
- **V-23** Opening verb diversity: no verb may start >2 questions.
- **V-24** Countable object uniqueness: no object noun in >1 question.
- **V-25** Number reuse: no number in >2 questions (exclude 0, 1).
- **V-26** Round number cap: Maths ≤30% of numbers are multiples of 5 or 10.
- **V-27** Number pair diversity: addition/subtraction last digits need ≥3 unique values.
- **V-28** Engagement framing: ≥1 question should use "Help..."/"Can you..." style.
- **V-29** Sentence structure diversity: ≥3 distinct structures per 10 questions.
- **V-30** Filler phrase ban: "the following"/"given below" forbidden without a visual.
- **V-31** Sequence step variety: pattern/sequence questions must vary step sizes.
- **V-32** Scenario repeat: word problems must use unique scenarios.

### Quality Gate (12 checks, log-only at PDF export)

- **V-33** Question count matches expected.
- **V-34** Answer key alignment: every question has a matching answer.
- **V-35** Duplicate detection (Jaccard >0.50).
- **V-36** Same-times detection in clock questions.
- **V-37** Concept duplicate: shared keyword in question pair.
- **V-38** Grade 1-2 forbidden phrases.
- **V-39** Hint leaks answer.
- **V-40** Fallback stub detection (LLM failed all 3 attempts).
- **V-41** MCQ integrity: options present, no duplicates, letter answer maps correctly.
- **V-42** Consecutive same answers (≥3 in a row).
- **V-43** Answer flood: same answer appears too often.
- **V-44** O'clock mismatch: "o'clock" in text but answer is not a whole hour.

---

## 3. MUST BE RANDOMIZED

These elements must vary between worksheet generations. Identical inputs must produce perceptibly different worksheets.

- **RAND-01** Intra-band question order: within same-difficulty bands, `random.shuffle(band)`. Not seeded.
- **RAND-02** Prompt context sampling: clock times, carry pairs, scenario contexts, and Indian names are `random.sample()` selections injected into the prompt. Not seeded.
- **RAND-03** Prompt seed: 6-character random string appended to user prompt to prevent LLM caching.
- **RAND-04** LLM temperature: 0.5 for Maths, 0.8 for other subjects.
- **RAND-05** Scenario rotation: scenarios (home, school, market, park, etc.) must not repeat within a worksheet. Pool is sampled per generation.
- **RAND-06** Opening verb rotation: easy/medium/hard verb pools rotated. No two consecutive questions start the same way.
- **RAND-07** Number progression: warm-up (Q1-3) uses small numbers, practice (Q4-7) medium, stretch (Q8+) larger — but specific values vary per generation.

### NOT randomized (and must stay that way)

- MCQ option order: rendered in LLM-returned order. No backend shuffle.
- Answer key order: matches question order. No reordering.
- Tier order: always Foundation → Application → Stretch.

---

## 4. MUST BE DETERMINISTIC

These operations use fixed algorithms with no randomness. Same input → same output.

### Slot Plan

- **DET-01** Slot plan is computed from question count, not generated: 5→(1R,1A,1Rep,1ED,1T), 10→(2,4,2,1,1), 15→(3,6,3,2,1), 20→(4,8,4,2,2). Non-standard counts use proportional fallback with mandatory ED≥1, T≥1.

### Topic Intelligence

- **DET-02** NCERT chapter lookup: search `curriculum_canon.json` by grade + subject + topic. Fallback to topic slug if not found.
- **DET-03** Learning objectives: lookup from `LEARNING_OBJECTIVES` dict by topic. Fallback to empty list.
- **DET-04** Valid skill tags: lookup from `topic_profiles.allowed_skill_tags`. Fallback to empty list.
- **DET-05** Default bloom level: `recall`. Default format mix: `{mcq:40, fill_blank:30, word_problem:30}`. Default scaffolding: `True`. Default challenge: `False`.

### Prompt Builder

- **DET-06** Compressed curriculum context: fixed format `TOPIC: | CHAPTER: | GRADE: | SUBJECT:` followed by `OBJECTIVES:`, `SKILL_TAGS:`, `BLOOM:`.
- **DET-07** Bloom directives: recall → "identify, name, state a fact"; application → "use knowledge to solve new problem"; reasoning → "analyse, justify, compare, evaluate".

### Difficulty Calibrator

- **DET-08** Sort key: `(word_count ascending, hard_format last)`. Applied when scaffolding=True.
- **DET-09** Format distribution fix: if any format drifts >20pp from target, swap excess to underrepresented. Deterministic swap selection.
- **DET-10** Number-range-by-position fix: Q1-3 warm-up (small numbers ≤100), Q8+ stretch (larger numbers >10). Deterministic swap selection.
- **DET-11** Adjacent format breaking: consecutive same-format questions swapped with nearest different-format question. Deterministic scan order.
- **DET-12** Scaffolding hints: "Think about: {first_word_from_topic}" injected into first 2 questions without existing hints.
- **DET-13** Encouragement: "You're doing great! Keep going!" stamped at Q5 position.
- **DET-14** Bonus question: appended with `_is_bonus=True` when challenge_mode=True.

### Quality Reviewer

- **DET-15** Arithmetic correction: AST-based safe eval. Only supports numeric literals and +-×÷%// operators. No variables, no function calls.
- **DET-16** Answer matching: integers compared exactly. Floats compared with ±0.01 tolerance.
- **DET-17** Fraction reduction: GCD-based. Returns "N/D" or whole "N".

### Release Gate

- **DET-18** Verdict logic: any BLOCK fail → "blocked". Any DEGRADE fail (no BLOCK) → "best_effort". Otherwise → "released".
- **DET-19** Severity scoring: critical warnings ×3, moderate ×2, info ×1. Quality tier thresholds: low (critical>0 or score≥10), medium (moderate>0 or score≥4), high (otherwise).
- **DET-20** All 10 rules are fail-open: a crashing rule logs the error and continues. No rule crash can block a worksheet.

### API Mapping

- **DET-21** `_map_question()` maps exactly 15 fields from internal dict to API model. Internal flags (`_math_unverified`, `_answer_corrected`, `_needs_regen`) are stripped except `verified` (derived from `not _math_unverified`).
- **DET-22** Render format inference: mcq→mcq_3/mcq_4 (by option count), fill_blank→fill_blank, true_false→true_false, everything else→short_answer.

---

## Enforcement Hierarchy (execution order)

```
1. Topic Intelligence Agent  → GenerationContext (deterministic, fail-open)
2. Prompt Builder            → Curriculum context + Bloom directives (deterministic)
3. Worksheet Generator       → LLM call (system + user prompt)
4. Response Validator        → JSON parse, schema, topic drift, maths verification
5. Quality Reviewer          → CHECK 1-10 (deterministic correction)
6. Difficulty Calibrator     → STEP A-F (sort, shuffle, hints, format fix)
7. Output Validator          → 18 advisory checks (log-only)
8. Release Gate              → R01-R10 (final contract enforcement) → verdict
9. API Mapper                → Strip internals, map to response model
```

Nothing reaches the user unless the Release Gate passes with verdict ≠ "blocked".

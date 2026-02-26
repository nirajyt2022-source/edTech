# High-Quality Worksheet Standard

Measurable quality contract for PracticeCraft AI worksheets. 6 dimensions, each with good/bad examples and concrete thresholds.

## Dimensions

| # | Dimension | Key Threshold | Enforced By |
|---|---|---|---|
| 1 | Language Quality | Class 1–2: ≤15 words/Q, Class 3–5: ≤25 | quality_reviewer CHECK 3, output_validator |
| 2 | Pedagogical Structure | Slot plan ±1, no single type >40% | slot_engine, difficulty_calibrator |
| 3 | Curriculum Alignment | chapter_ref present, ≥70% topic keyword match | topic_intelligence, worksheet_generator |
| 4 | Difficulty Progression | Format mix within 15pp, number zones correct | difficulty_calibrator STEPS A/D/E |
| 5 | Visual Clarity | 100% visual data complete, 0 phantom refs | worksheet_generator, output_validator |
| 6 | Trust Signals | 0 `_math_unverified`, 0 answer-leaking hints | quality_reviewer CHECKS 1/6/7/8 |

---

## 1. Language Quality

**Good:** "Circle the number that is 10 more than 45." (8 words, one action, grade-appropriate)
**Bad:** "Determine the approximate sum of the following two quantities and express your answer in numerical form." (Class 1, too many words, abstract vocab)
**Bad:** "कितने pencils हैं?" (Hindi code-mixing)

| Check | Threshold |
|---|---|
| Word count | Class 1–2: ≤15, Class 3–5: ≤25 |
| Forbidden vocabulary | Class 1–2: no "approximately", "calculate", "determine", "evaluate", "hypothesis" |
| LLM artifacts | 0 matches for "As an AI", "Here's a", "Let me" |
| Hindi purity | 0 Latin-script words in Devanagari text |

**Enforced:** LLM artifact detection (CHECK 9) and Hindi purity (CHECK 10) in quality_reviewer.

## 2. Pedagogical Structure

**Good:** 10Q → 2 recognition, 4 application, 2 representation, 1 error_detection, 1 thinking. Mixed types (MCQ, fill_blank, word_problem).
**Bad:** 10 MCQs, all recall, no misconception probe, skill_tag "general" on every question.

| Check | Threshold |
|---|---|
| Slot plan adherence | Each role within ±1 of plan |
| Question count | ≥10: at least requested−1. <10: exact |
| Type diversity | No single type >40% of worksheet |
| Misconception coverage | ≥1 error_detection question |
| Higher-order thinking | ≥1 thinking question |
| Skill tag diversity | No single tag >60% when 3+ tags available |

**Gap:** Type diversity cap (40%) not enforced.

## 3. Curriculum Alignment

**Good:** "Addition (carries)" worksheet references NCERT Ch. 3, all skill_tags from topic profile, no division questions.
**Bad:** chapter_ref is null, topic is "Fractions" but 40% of questions are about "Decimals", Class 2 worksheet mentions "algebra".

| Check | Threshold |
|---|---|
| Curriculum available | RAG lookup returns content |
| Chapter reference | `chapter_ref` non-null |
| Topic drift | ≥70% of questions contain topic keywords |
| Disallowed keywords | 0 matches against topic_profile blacklist |
| Skill tags valid | 100% in `allowed_skill_tags` |

**Gap:** Disallowed keyword check only in prompt, not validated post-generation.

## 4. Difficulty Progression

**Good:** Easy→hard ordering, Q1–3 use small numbers (<100), Q8+ use large numbers, format mix matches adaptive target, first 2 questions have hints when scaffolding.
**Bad:** Hardest question is Q1, Class 1 uses 4-digit numbers, target is 40% MCQ but actual is 90%.

| Check | Threshold |
|---|---|
| Difficulty ordering | ≤2 out-of-order pairs (scaffolding mode) |
| Number zones | Q1–3: <100, Q4–7: medium, Q8+: ≥100 |
| Format mix drift | All categories within 15pp of target |
| Scaffolding hints | First 2 questions have hints when scaffolding=True |

**Gap:** Auto-correction is silent — a worksheet needing 8 swaps vs. 0 swaps both appear "valid".

## 5. Visual Clarity

**Good:** Clock visual shows 3:00, answer says "3 o'clock". Object groups sum matches answer. No "look at the picture" without a visual.
**Bad:** Question says "Look at the clock" but visual_type is null. Clock shows 3:00 but answer says "5 o'clock".

| Check | Threshold |
|---|---|
| Visual data complete | 100% of visual questions have all required fields |
| Visual-answer coherence | Clock time and object_group sums match answers |
| Phantom references | 0 "look at the picture" when visual_type is None |

**Gap:** Visual-topic appropriateness not validated (only disallowed types blocked in prompt).

## 6. Trust Signals

**Good:** 0 unverified math, 0 regen markers, every question has text + answer, hints don't leak answers, no self-contradicting thinking answers.
**Bad:** 3 questions `_math_unverified`, hint says "The answer is 42", thinking answer says "actually, my reasoning was wrong".

| Check | Threshold |
|---|---|
| Arithmetic verified | 0 `_math_unverified` flags |
| No regen markers | 0 `_needs_regen` flags |
| Complete questions | 100% non-bonus Qs have text + answer |
| Hint safety | 0 answer-leaking hints |
| No self-contradiction | 0 contradiction markers in thinking answers |

**Gap:** No composite quality score computed. Warnings not categorized by severity.

---

## Gaps Summary

| Check | Priority | Status | Location |
|---|---|---|---|
| LLM artifact detection | P1 | **Done** | quality_reviewer CHECK 9 |
| Hindi purity check | P1 | **Done** | quality_reviewer CHECK 10 |
| Type diversity cap (40%) | P1 | **Done** | output_validator check 5 |
| Disallowed keyword validation | P2 | **Done** | output_validator check 6 |
| Warning severity categorization | P2 | **Done** | worksheet_generator `_categorize_warnings()` |
| Pre-correction quality scoring | P3 | **Done** | difficulty_calibrator `[calibration_score]` warning |
| Visual-topic appropriateness | P3 | **Done** | output_validator check 7c |

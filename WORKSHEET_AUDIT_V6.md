# Adversarial Audit V6 — 10 Fresh Worksheets

**Date:** 2026-03-03 | **10/10 generated** | **Avg Score: 94.8** | **1 "released", 9 "best_effort"**

## Results Summary

| ID | Grade | Subject | Topic | Diff | Score | Verdict |
|----|-------|---------|-------|------|-------|---------|
| WS1 | Class 1 | Maths | Addition (single digit) | easy | 96.0 | **released** |
| WS2 | Class 2 | Maths | 2D Shapes | easy | 100.0 | best_effort |
| WS3 | Class 3 | Maths | Multiplication (2-digit×1-digit) | medium | 97.0 | best_effort |
| WS4 | Class 4 | Maths | Fractions (like fractions +/-) | medium | 91.8 | best_effort |
| WS5 | Class 5 | Maths | Decimals (+/-) | hard | 96.0 | best_effort |
| WS6 | Class 1 | English | Opposite Words | easy | 95.0 | best_effort |
| WS7 | Class 3 | English | Nouns (common/proper) | medium | 93.0 | best_effort |
| WS8 | Class 4 | Science | Food and Digestion | medium | 93.0 | best_effort |
| WS9 | Class 3 | Hindi | Vachan (singular/plural) | easy | 94.4 | best_effort |
| WS10 | Class 5 | EVS | Water Cycle & Conservation | medium | 92.0 | best_effort |

## What's Working Well (improvements from V5)

1. **First "released" verdict ever** — WS1 (Class 1 Addition) achieved "released" status
2. **All arithmetic correct in WS1, WS3, WS5** — Zero wrong answers in addition, multiplication, decimals
3. **Hindi engagement: zero transliterated English** — V5 had "हेल्प स्नेहा फिगर आउट", V6 has none
4. **No MCQ answer-not-in-options bugs** — V5's WS4 Q7 had answer "455" for options ['8','9','10','7']. Zero in V6
5. **Common mistakes are grade-appropriate** — WS1: "counting on fingers incorrectly", WS3: "forget to add regrouped tens"
6. **Indian context is authentic** — laddoo, chai stall, Diwali, rangoli, Makar Sankranti, mandi, temple festival
7. **Skill tags: grade-correct across all 10 worksheets**

## Issues Found

### P0 — Wrong Answer / Academic Safety

**WS4 Q5 — True/False answer doesn't match question format.**
- Q: "True or False: 7/9 - 4/9 = 3/9"
- A: "1/3" (should be "True" — 3/9 is correct, 1/3 is just simplified form)
- Impact: Child selecting True would be marked wrong despite being correct

### P1 — Pedagogical Concern

- **WS2 scores 100.0 but verdict is "best_effort"** — perfect score blocked by non-cosmetic degrade rule
- **WS5 — All 10 questions are "hard" difficulty** — no scaffolding, no easy warmup
- **WS8 — Zero Indian markers** for Science (Food/Digestion) — mentions dal/chapati but mostly generic
- **WS9 Q3 — Contradictory question/answer** — asks for बहुवचन (plural) but answer is एकवचन (singular)

### P2 — Quality Polish

- **WS5 — Round numbers 57%** for Decimals — should use numbers like 3.47, 8.63 not just .5/.0
- **WS9 — Only 2 sentence structures** — missing question_word type in Hindi
- **WS8 — MCQ heavy** (5/10 MCQ) — needs more balanced type mix

### P3 — Cosmetic

- **Engagement framing exactly 2/10 on every worksheet** — mechanically consistent
- **Chapter references missing** for WS6 (Opposite Words), WS10 (Water Cycle)

## V6 vs V5 Comparison

| Metric | V5 | V6 | Trend |
|--------|----|----|-------|
| Generation success | 10/10 | 10/10 | Stable |
| Avg quality score | 93.7 | **94.8** | +1.1 |
| "Released" verdicts | 0/10 | **1/10** | Improved |
| Wrong arithmetic answers | 2 | **0** | Fixed |
| MCQ answer not in options | 1 | **0** | Fixed |
| Transliterated English in Hindi | 1 | **0** | Fixed |
| T/F answer format mismatch | 0 | 1 | New |
| Skill tags grade-correct | 10/10 | 10/10 | Stable |

## Audit History

| Audit | Date | Avg Score | Released | P0 Bugs | Key Fix |
|-------|------|-----------|----------|---------|---------|
| V3 | 2026-03-03 | 93.8 | 0/10 | 0 | Baseline after P2 fixes |
| V4 | 2026-03-03 | 93.8 | 0/10 | 1 | Error detection contradiction |
| V5 | 2026-03-03 | 93.7 | 0/10 | 2 | Wrong arithmetic, MCQ mismatch |
| V6 | 2026-03-03 | **94.8** | **1/10** | 1 | First released worksheet |

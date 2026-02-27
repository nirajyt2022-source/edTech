# Anti-Artificiality Rules

Concrete rules to eliminate the "AI feel" from generated worksheets. Organized by category, prioritized for implementation.

## Status

| Priority | Rules | Status |
|----------|-------|--------|
| P0 | L1, R3, N2 | **Done** |
| P1 | L4, R1, R4, T2 | **Done** |
| P2 | S4, N1, N3, T1 | **Done** |
| P3 | S2, S3, R5, T3, T4 | **Done** |
| P4 | L2, L3, S1, N4, R2 | **Done** |

---

## 1. Linguistic Patterns

| Rule | Name | Threshold | Enforced By | Status |
|------|------|-----------|-------------|--------|
| L1 | Opening verb diversity | No verb >2× per worksheet | output_validator check 9 | **Done** |
| L2 | Sentence structure diversity | ≥3 distinct structures per 10Q | output_validator check 15 | **Done** |
| L3 | Filler phrase ban | 0 "the following"/"given below" (unless visual) | output_validator check 16 | **Done** |
| L4 | Expand phrasing pools | 8-10 templates per skill tag | phrasing_templates.py | **Done** |

## 2. Structural Patterns

| Rule | Name | Threshold | Enforced By | Status |
|------|------|-----------|-------------|--------|
| S1 | Intra-band shuffle | Shuffle within same-difficulty band | difficulty_calibrator STEP A2 | **Done** |
| S2 | MCQ option count variety | 70% four / 20% three / 10% five | prompt instruction | **Done** |
| S3 | Word problem length variety | 2-4 sentences per WP | prompt instruction | **Done** |
| S4 | No adjacent same format | 0 consecutive same-format pairs | difficulty_calibrator STEP F | **Done** |

## 3. Numerical Patterns

| Rule | Name | Threshold | Enforced By | Status |
|------|------|-----------|-------------|--------|
| N1 | Round number cap | ≤30% multiples of 5/10 | output_validator check 12 | **Done** |
| N2 | Cross-question number reuse | No number in >2 questions | output_validator check 10 | **Done** |
| N3 | Number pair diversity | ≥3 digit-diversity in pairs | output_validator check 13 | **Done** |
| N4 | Sequence step variety | Vary step sizes across worksheet | output_validator check 17 | **Done** |

## 4. Repetition Issues

| Rule | Name | Threshold | Enforced By | Status |
|------|------|-----------|-------------|--------|
| R1 | Expand name bank | ≥10 unique names per worksheet | worksheet_generator | **Done** |
| R2 | No scenario repeat | 0 duplicate scenarios per worksheet | output_validator check 18 | **Done** |
| R3 | Tighter near-duplicate | 50% similarity triggers flag (was 33%) | output_validator check 3b | **Done** |
| R4 | Object uniqueness | No countable object in >1 question | output_validator check 10 | **Done** |
| R5 | Cross-worksheet rotation | 20 scenarios, no repeat per worksheet | prompt instruction | **Done** |

## 5. Tone Issues

| Rule | Name | Threshold | Enforced By | Status |
|------|------|-----------|-------------|--------|
| T1 | Engagement framing | ≥1 question uses warm framing | output_validator check 14 | **Done** |
| T2 | Error detection variety | 8 distinct framings | phrasing_templates.py | **Done** |
| T3 | Hindi spoken register | Spoken vocab, not textbook-formal | prompt + forbidden list | **Done** |
| T4 | Encouragement micro-prompt | 1 at Q5 for scaffolding mode | difficulty_calibrator STEP B2 | **Done** |

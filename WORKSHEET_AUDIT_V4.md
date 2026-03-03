# Worksheet Audit V4 — Adversarial 3-Persona Deep Review

**Date:** 2026-03-03
**Worksheets:** 10 (all generated fresh, different topic mix from V3)
**Generation Success:** 10/10 (100%)
**Average Quality Score:** 95.3/100

---

## As a Skeptical CBSE Teacher

### What I Would NOT Trust

**1. WRONG ANSWER — WS3 Q9 is self-contradicting (CRITICAL)**
> Q: "Help Rudra figure out: He says 1 hour 40 minutes is the same as 100 minutes. Is he correct?"
> A: "No, he is incorrect."
> Explanation: "1 hour is 60 minutes. So, 1 hour 40 minutes = 60 + 40 = 100 minutes. **Rudra is correct.**"

The answer says "No" but the explanation proves he IS correct. This is an error_detection question where the LLM contradicted itself. **If a child reads this, they learn the wrong thing.** The arithmetic auto-corrector didn't catch this because it's a logical/comprehension error, not a calculation error.

**2. Chapter mapping is sometimes wrong (MEDIUM)**
- WS4 (Large Numbers) mapped to "Chapter 1: Building with Bricks" — that's a shapes chapter, not numbers.
- WS5 (Percentage) mapped to "Chapter 10: Tenths and Hundredths" — related but not exact.
- The fuzzy matching picks the closest available entry but doesn't validate semantic correctness.

**3. Topic drift detector flags too aggressively (LOW)**
- WS6 (Opposite Words): "8/10 questions appear off-topic" — but ALL 10 questions are clearly about opposites. The keyword matcher doesn't know the vocabulary category.
- WS9 (Vilom Shabd): "10/10 questions appear off-topic" — again, all correctly on-topic. The Hindi vocabulary keyword list is missing.

**4. Difficulty labels not always calibrated (LOW)**
- WS1 Q8: "Diya says 8 - 0 = 0. Is she correct?" is labeled `hard` for Class 1. This IS appropriate as a conceptual question but the other `hard` questions (Q9: 9 - 7 = __, Q10: basic word problem) are really `medium`.
- WS5 (Percentage): ALL 10 questions are labeled `hard`. A mix of easy/medium/hard would be more useful for a "hard" worksheet — some scaffold questions are needed.

**5. MCQ option count inconsistent**
- Some MCQs have 3 options, some 4, some 5. While the prompt asks for variety (70% four, 20% three, 10% five), the actual distribution is uncontrolled. WS9 Q9 has only 2 options (हाँ/नहीं) which is effectively true/false mislabeled as MCQ.

### What Feels Academically Sound

- Arithmetic is correct across all Maths worksheets (auto-corrector working)
- Explanations are step-by-step and pedagogically appropriate
- Common mistakes are grade-appropriate (e.g., "confuse hour and minute hands" for time)
- Hindi worksheets use proper Devanagari throughout
- Science questions test real conceptual understanding, not just definitions
- Error detection questions are genuinely challenging (WS4 Q7 with place value swap)

---

## As a Hyper-Critical Parent

### What Feels Weak

**1. "Help [name] solve this:" feels robotic when overused**
- WS2 Q5: "Help Kabir solve this: a bangle looks like a ______ shape." — Natural enough.
- WS9 Q2: "Help Tara solve this: मीरा स्कूल की सभा..." — The English "Help Tara solve this:" prefix on a Hindi question feels jarring. Should be "तारा की मदद करो:" or similar.
- The engagement framing is clearly injected post-generation on some questions. The seam shows.

**2. Word problems are still slightly verbose for Class 1-2**
- WS1 Q6: "At a temple festival, there were 9 marigold flowers. Pooja used 5. How many are left?" — 16 words for Class 1 (limit 15). A 5-year-old would struggle.
- WS1 Q10: "Aarav had 9 kites for Makar Sankranti. He flew 6 kites. How many are not flown?" — "not flown" is an unusual phrase for Class 1.

**3. Some explanations are too advanced for the grade**
- WS2 Q3: "A brick is a cuboid, not a cube. A cube has all sides equal, while a cuboid has different length, width, and height." — For Class 2, "cuboid" might not be in their vocabulary yet.
- WS2 Q6: "An ice cream cone is a cone shape, which has a circular flat base and a single curved surface that tapers to a point." — This is Class 4-5 level geometry language for a Class 2 easy worksheet.
- WS8 Q9: "Sensory nerves in the skin send a message to the spinal cord..." — "Spinal cord" and "reflex action" are appropriate for Class 5 but the depth of the explanation exceeds what NCERT expects.

**4. Hindi engagement framing is in English**
- WS9 Q2, Q5: "Help Tara solve this:", "Help Ananya solve this:" — These are English phrases injected into Hindi worksheets. My child would be confused seeing English instructions in a Hindi paper.

**5. Missing visual elements**
- WS3 (Time/Clock): Every single question is text-based. A Time worksheet for Class 3 SHOULD show clock faces. No clock diagrams = poor pedagogical practice. The worksheet says "standard" (text-only) but time concepts need visuals.
- WS2 (Shapes): Same problem — shapes and patterns without any actual shape images is pedagogically incomplete.

### What Feels Good (Would Pay For)

- Quality scores 88-98 give confidence
- NCERT chapter references add credibility
- Progressive difficulty within each worksheet
- Indian cultural context (Diwali, cricket, mandi, rangoli) makes it relatable
- ₹ symbol usage in Maths is correct
- Hindi questions are culturally accurate (विलोम शब्द with दिन/रात, अच्छा/बुरा)

---

## As a Competitor Founder

### What I Would Attack

**1. Self-contradicting answers = trust killer (WS3 Q9)**
One factually wrong answer in 100 questions is a 1% error rate. For a paid product, that's unacceptable. If a parent finds ONE wrong answer, they'll distrust the entire platform. This needs a logical consistency checker, not just arithmetic verification.

**2. Round number problem is STILL visible (WS3: 59%, WS4: 45%, WS5: 81%)**
The R12 guard flags but doesn't fix. Three out of seven Maths worksheets exceed the 40% threshold. For percentage (WS5), having 81% round numbers (10, 20, 25, 30, 35, 40, 50, 75, 80, 90, 100, 120, 150, 170, 200, 250) is a dead giveaway that a machine generated these. A teacher would use 23%, 37%, 48%, 62%.

**3. `best_effort` on 9/10 worksheets looks broken to a business metric**
If only 10% of worksheets get "released" status, the release gate is too strict. Either recalibrate the thresholds or distinguish between "cosmetically imperfect but pedagogically sound" vs "has actual errors". Currently, WS7 (Score 95, all content correct, great Indian context) gets the same `best_effort` as WS3 (which has a WRONG ANSWER).

**4. No chapter ref for English/Hindi/Science/EVS (4/10 worksheets)**
WS6, WS7, WS8, WS9, WS10 all show `Chapter: None`. The static NCERT map only covers Maths well. For a multi-subject platform, 40% missing chapters undermines the "NCERT-aligned" claim.

**5. Skill tags are generic for non-Maths subjects**
- Science: all questions get `sci_water_identify` — no differentiation between recall/apply/analyze.
- Hindi: all questions get `hin_c5_vilom_identify` — even for Class 2 (label says c5!).
- The fallback recipe generates tags but they don't actually match the assigned skill. Mastery tracking for non-Maths is meaningless.

**6. Common mistake field is sometimes too long**
- WS5: "Students often confuse 'percentage of' with 'percentage out of 100' directly, or make calculation errors when converting fractions/decimals to percentages or vice-versa. They might also struggle with multi-step problems involving percentages." — 37 words. This should be 1 sentence, 15 words max.

### What I'd Steal (Genuinely Impressive)

- The error detection question type (WS4 Q7) is pedagogically brilliant — most competitors don't have this
- Auto-correcting LLM arithmetic mistakes silently = competitive moat
- 100% generation success rate with 10/10 different topic types
- Engagement framing on word problems feels natural on most questions
- Indian scenario variety (temple festival, mango orchard, Makar Sankranti, Diwali shopping, mandi, rangoli, auto-rickshaw, cricket, chai stall) is authentic

---

## Summary Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Factual Accuracy** | 99/100 | 1 self-contradicting answer in 100 questions (WS3 Q9) |
| **Age Appropriateness** | 85/100 | Explanations sometimes too advanced; Class 1-2 word count occasionally over |
| **Indian Context** | 90/100 | Strong for Maths word problems; weak for English vocabulary |
| **Sentence Variety** | 80/100 | 8/10 worksheets have ≥3 structures; 2 Hindi/Maths still monotone |
| **NCERT Alignment** | 70/100 | Maths chapters mapped; English/Hindi/Science/EVS missing chapters |
| **Round Numbers** | 60/100 | 3/7 Maths worksheets exceed 40% threshold |
| **Engagement** | 85/100 | Warm framing present but English prefix on Hindi worksheets is jarring |
| **Visual Pedagogy** | 40/100 | Time/Shapes worksheets NEED visuals but have none (text-only mode) |

---

## Priority Fix List (New)

| Priority | Issue | Evidence | Impact |
|----------|-------|----------|--------|
| **P0** | Self-contradicting error_detection answers | WS3 Q9: answer says "No" but explanation proves "Yes" | Trust-destroying |
| **P1-A** | Hindi worksheets get English engagement prefix | WS9 Q2, Q5: "Help [name] solve this:" in Hindi worksheet | Looks unprofessional |
| **P1-B** | Skill tags wrong for non-Maths (c5 label for Class 2) | WS9: `hin_c5_vilom_identify` for Class 2 Hindi | Mastery tracking broken |
| **P1-C** | Topic drift false positives for vocabulary subjects | WS6: 8/10 "off-topic", WS9: 10/10 "off-topic" — all correct | Noise in warnings |
| **P2-A** | Round numbers in percentage/time still too high | WS5: 81%, WS3: 59% | AI feel obvious |
| **P2-B** | Explanations too advanced for lower classes | WS2 "cuboid" for Class 2, WS2 "tapers to a point" | Age mismatch |
| **P2-C** | Chapter mapping semantic mismatch | WS4: "Building with Bricks" for Large Numbers | Wrong NCERT ref |
| **P2-D** | Common mistake field too verbose | WS5: 37 words | Could be tighter |
| **P3-A** | `best_effort` too strict (9/10) | Score 95 gets same label as score with errors | Business metric concern |
| **P3-B** | No visual recommendation for visual topics | Time/Shapes in text-only mode | Pedagogical gap |

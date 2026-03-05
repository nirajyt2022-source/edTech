# Trust Rules: P0/P1/P2 Taxonomy

This document defines trust severity for worksheet quality failures.
Runtime release behavior and CI trust gates must use the same mapping from
`app/services/trust_policy.py`.

## P0 (Block Always)
- Wrong answer / arithmetic mismatch
- Broken question schema / unknown types
- Missing answer keys
- Severe structural integrity failures
- Critical duplicate-answer MCQ ambiguity

Release-gate rules:
- `R01_ARITHMETIC_VERIFIED`
- `R02_KNOWN_TYPES_ONLY`
- `R05_QUESTION_COUNT_EXACT`
- `R08_MINIMUM_QUALITY_BAR`
- `R14_SENTENCE_DIVERSITY_GUARD`
- `R15_ANSWER_AUTHORITY`
- `R22_MCQ_UNIQUE_ANSWER`
- `R23_ANSWER_KEY_COMPLETE`
- `V3_QUALITY_GATE_BLOCK`

## P1 (Strict-Mode Block)
- Age-inappropriate or pedagogically unsafe content
- Missing curriculum grounding / parent confidence blocks
- Major topic drift
- Mandatory visual/render integrity misses for young learners
- Hindi purity and fill-blank ambiguity quality issues
- Minimum quality score below trust threshold

Release-gate rules:
- `R04_CURRICULUM_GROUNDED`
- `R07_WORD_PROBLEM_VERIFIED`
- `R09_SKILL_TAGS_VALID`
- `R11_TOPIC_DRIFT_GUARD`
- `R16_MCQ_QUALITY_GUARD`
- `R17_HINDI_SCRIPT_PURITY`
- `R18_FILL_BLANK_AMBIGUITY`
- `R20_RENDER_INTEGRITY`
- `R21_PARENT_CONFIDENCE`
- `R24_MINIMUM_QUALITY_SCORE`
- `V3_QUALITY_GATE_WARNING`

## P2 (Observe / Improve)
- Format mix drift
- Sentence structure polish
- Round-number overuse
- Transparency/adaptive/curriculum depth stamps

Release-gate rules:
- `R03_FORMAT_MIX_TOLERANCE`
- `R06_ADAPTIVE_EXPLICIT`
- `R10_WARNINGS_TRANSPARENT`
- `R12_ROUND_NUMBER_GUARD`
- `R13_SENTENCE_STRUCTURE_GUARD`
- `R19_CURRICULUM_DEPTH`

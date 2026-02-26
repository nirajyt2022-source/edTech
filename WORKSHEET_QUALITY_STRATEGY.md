# Worksheet Quality Strategy & Implementation Tracker

> **Goal:** Make AI-generated worksheets indistinguishable from expert-designed ones.
> **Moat:** Curriculum-grounded deterministic quality infrastructure, not raw AI.
> **Created:** 2026-02-26

---

## Strategic Audit Summary

### Why AI Worksheets Fail

| Problem | Description |
|---|---|
| Structural monotony | Same sentence pattern repeated 10x ("Solve: X + Y") |
| Context-free generation | No awareness of curriculum scope/sequence |
| Flat difficulty curves | All questions at same cognitive level |
| Phantom pedagogy | No error detection, representations, or metacognitive prompts |
| Visual incoherence | Decorative visuals that don't match questions |

### Where Parents Lose Trust

1. **Wrong answers** — #1 trust destroyer, one wrong answer key = churn
2. **Off-topic drift** — requesting "Time" worksheet, getting addition questions
3. **Age-inappropriate language** — "Determine the quotient" for a 6-year-old
4. **Repetition** — "clearly a computer spitting out variations"
5. **Missing explanations** — no hints, no worked examples, no parent guidance

### Where Teachers Reject AI Tools

1. Not mapped to specific NCERT chapters
2. No Bloom's taxonomy awareness (LOTS/HOTS)
3. No skill isolation (tests multiple skills when should test one)
4. Can't customize with predictable results
5. No assessment utility (unclear rubrics)

---

## Competitive Positioning

| Dimension | ChatGPT Prompts | Marketplaces (StudiesToday) | Generic AI (MagicSchool) | **PracticeCraft** |
|---|---|---|---|---|
| Curriculum alignment | Zero | High (manual) | Partial | **Deep (198 profiles, NCERT-mapped)** |
| Question diversity | Low | High (human) | Medium | **High (skill-tag recipes)** |
| Math accuracy | ~85% | 99% (human) | ~90% | **99%+ (AST verify + auto-correct)** |
| Scalability | Infinite/low quality | Low (manual labor) | High/generic | **High with quality guarantees** |
| Difficulty scaffolding | None | Sometimes | Basic labels | **Structural (role + tier ordering)** |
| Visual pedagogy | None | Static PDFs | Decorative | **Functional SVGs (10 types)** |
| Per-child adaptation | None | None | Basic | **Mastery tracking + calibration** |
| Cost per worksheet | $0.01 + review | $5-50 | $0.05 | **$0.02, no review needed** |

### Defensible Moat Layers

| Layer | What | Why Hard to Replicate |
|---|---|---|
| Topic Profile KB | 198 profiles × skill tags × recipes | NCERT curriculum expertise per grade/subject |
| Scenario Pools | Pre-verified math data per class | Grade-appropriate scope knowledge |
| Validation Pipeline | 8+ validators in sequence | Each embodies a pedagogical rule |
| Quality Reviewer | AST-safe arithmetic correction | Domain-specific math verification |
| Difficulty Calibrator | Scaffolding, hints, bonus Qs | Pedagogical sequencing logic |
| Visual Schema Engine | 10 SVG types with strict schemas | Frontend rendering + backend enforcement |

---

## Quality Formula

```
Quality = Structural Constraints (60%) × Content Generation (25%) × Post-Generation Repair (15%)
```

Most competitors: 100% on LLM. PracticeCraft: 75% on deterministic infrastructure.

---

## Gold Standard Quality Framework — 7 Pillars

### Pillar 1: Natural Language Variation
**Rule:** No two questions share the same sentence structure.

- [x] Skill-tag recipes enforce different question types
- [x] Scenario pools inject varied contexts
- [x] **Phrasing templates** — 3-5 templates per skill tag, sampled per question
- [x] **Opening verb rotation** — inject variety constraint into system prompt

### Pillar 2: Progressive Difficulty Scaffolding
**Rule:** Questions flow confidence-building → skill-building → stretch.

- [x] Role distribution (recognition → application → thinking)
- [x] `ensure_roles()` sorts by tier
- [x] **Intra-tier progression** — numbers get harder within application tier
- [x] **`number_range_by_position`** — position 1-3 small, 4-7 medium, 8-10 large

### Pillar 3: Skill Tagging
**Rule:** Every question maps to exactly one assessable micro-skill.

- [x] 198 topic profiles with `allowed_skill_tags`
- [x] Skill-tag recipes with exact counts
- [x] **`skill_tag` in question output schema** — validate against recipe
- [x] **Per-skill mastery tracking** — gap analysis per child

### Pillar 4: Visual Clarity
**Rule:** Every visual is functionally necessary and schema-correct.

- [x] 10 SVG visual types with strict schemas
- [x] `validate_visual_data()` strips malformed visuals
- [x] `fix_visual_types()` handles aliases
- [x] **Visual-answer coherence check** — clock visual matches answer time

### Pillar 5: Error-Proof Math Logic
**Rule:** Zero tolerance for incorrect answers.

- [x] `_verify_maths_answer()` in worksheet_generator (regex)
- [x] `_verify_math_answer()` in output_validator (pattern)
- [x] Quality Reviewer with AST safe eval
- [x] Scenario pools with pre-computed answers
- [x] **Multi-step expression parser** — handle `a + b + c`, `a × b + c`
- [x] **Word problem answer extraction** — parse operations from context

### Pillar 6: No Repetitive Patterns
**Rule:** Template similarity across questions stays below 33%.

- [x] Exact duplicate detection
- [x] Pattern-based near-duplicate detection (`_make_template()`)
- [x] Skill-tag recipes enforce type diversity
- [x] **Retry with negative constraint** — on duplicate, inject "do NOT repeat [template]"

### Pillar 7: No Robotic Phrasing
**Rule:** Questions sound like a teacher wrote them.

- [x] Indian names and contexts injected
- [x] Scenario variety (market, school, park, zoo, etc.)
- [x] **Opening verb rotation in `_CORE_RULES`**
- [x] **NCERT preferred terminology** mapping per topic

---

## Trust Engine

### Parent Trust Signals

| Signal | Description | Status |
|---|---|---|
| Curriculum badge | "Aligned to NCERT Class 3, Ch.7: Time" on PDF header | [x] Done |
| Answer key + explanations | Step-by-step working in parent-facing answer page | [x] `explanation` generated, needs PDF formatting |
| Difficulty badge | ★/★★/★★★ labels on each question | [x] Done |
| Zero-error footer | "All answers verified by computational engine" | [x] Done |

### Teacher Trust Signals

| Signal | Description | Status |
|---|---|---|
| Skill coverage report | "Clock reading (3), Word problems (3), ..." after generation | [x] `skill_coverage` in API response |
| Predictable customization | Question count change scales recipe proportionally | [x] `_scale_recipe()` shipped |
| NCERT vocabulary | "Regrouping" not "carrying", exact textbook terms | [x] Done |

### Academic Feel

- [x] Fixed Q1, Q2... numbering
- [x] Professional typography (Fraunces serif headings)
- [x] Clean SVG visuals (no clip art, no emojis)
- [x] Consistent visual sizing (clocks same diameter)
- [x] Whitespace for working area in PDF

---

## Implementation Roadmap

### P0 — Ship This Week (high impact, low effort)

| # | Task | Effort | Files | Status |
|---|---|---|---|---|
| 1 | Add `skill_tag` to question output schema | 1 day | `worksheet_generator.py`, output format | [x] Done `22aced9` |
| 2 | Visual-answer coherence validation (clock, object_group) | 1 day | `output_validator.py` | [x] Done `22aced9` |

### P1 — Ship Next Week

| # | Task | Effort | Files | Status |
|---|---|---|---|---|
| 3 | Surface curriculum metadata in PDF header | 0.5 day | PDF renderer | [x] Done |
| 4 | Opening verb rotation in system prompt | 0.5 day | `_CORE_RULES` in `worksheet_generator.py` | [x] Done |
| 5 | Skill coverage summary in API response | 0.5 day | `worksheets_v2.py` API router, `worksheet.py` model | [x] Done |

### P2 — Ship in 2 Weeks

| # | Task | Effort | Files | Status |
|---|---|---|---|---|
| 6 | Phrasing templates per skill tag (top 10 topics) | 3 days | Topic profiles | [x] Done |
| 7 | Intra-tier number progression via scenario pools | 2 days | Scenario pools | [x] Done |
| 8 | Near-duplicate retry with negative constraint | 1 day | `generate_worksheet()` | [x] Done |

### P3 — Ship in 1 Month

| # | Task | Effort | Files | Status |
|---|---|---|---|---|
| 9 | Multi-step expression parser for math verification | 2 days | Validator pipeline | [x] Done |
| 10 | NCERT preferred terminology mapping | 2 days | Topic profiles | [x] Done |
| 11 | Difficulty badge (★/★★/★★★) on PDF questions | 1 day | PDF renderer | [x] Done |
| 12 | Zero-error verification footer on PDF | 0.5 day | PDF renderer | [x] Done |

---

## Already Shipped (Foundation)

| Date | What | Commit |
|---|---|---|
| 2026-02-26 | Skill-tag recipe injection into v2 prompt | `0707e24` |
| 2026-02-26 | Scenario pool injection (time, addition) | `0707e24` |
| 2026-02-26 | `_scale_recipe()` — proportional scaling with min-1-per-tag | `0707e24` |
| 2026-02-26 | Pattern-based near-duplicate detection in output_validator | `0707e24` |
| 2026-02-26 | `_make_template()` — strips names/numbers/times for comparison | `0707e24` |
| Earlier | 198 topic profiles with skill tags and recipes | Phase 2 |
| Earlier | 10 SVG visual types with strict schemas | Phase 5 |
| Earlier | Quality Reviewer + Difficulty Calibrator (4-agent layer) | Phase 2 |
| Earlier | Scenario pools (maths_time.json, maths_addition.json) | Phase 5 |

---

## $50M ARR Path

```
Phase 1 (now):  Nail CBSE Class 1-5 → teachers share worksheets organically
Phase 2:        Expand to Class 6-8 → deeper curriculum mapping
Phase 3:        Add UAE/IGCSE curriculum mappings → international expansion
Phase 4:        White-label engine to school chains → B2B licensing
```

Defensibility grows with every curriculum deeply mapped — that mapping is expert labor that doesn't scale with AI alone.

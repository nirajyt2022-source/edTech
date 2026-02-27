# Trust Framework — Implementation Tracker

## Framework Summary

Product signals that build parent confidence and teacher credibility. No marketing — only verifiable, in-product proof of quality.

---

## P0 — Worksheet-Level Trust Signals ✅ SHIPPED (`7cc8157`)

| Signal | Parent value | Teacher value | Frontend | PDF |
|--------|-------------|---------------|----------|-----|
| Parent tip | High | Low | ✅ | ✅ |
| Common mistake warning | High | Medium | ✅ | ✅ |
| Skill coverage summary | Medium | High | ✅ | — |
| Quality badge (high/medium/low) | High | Low | ✅ | — |

---

## P1 — Per-Question Trust Signals ✅ SHIPPED (`9890182`)

| Signal | Parent value | Teacher value | Frontend | PDF |
|--------|-------------|---------------|----------|-----|
| Skill tag badge on each question | High | High | ✅ | — |
| Skill tag in answer key | Medium | High | ✅ | ✅ |
| Worked explanations in answer key | High | Medium | ✅ | ✅ (already existed) |

---

## P2 — NCERT Chapter Ref in Frontend + Answer Key Curriculum Line ✅ SHIPPED

**Goal:** Surface `chapter_ref` (NCERT chapter alignment) in the frontend UI, and add a curriculum summary line to the answer key section.

**What P2 added:**
| Item | File | Status |
|------|------|--------|
| Add `chapter_ref` to Worksheet interface | `WorksheetGenerator.tsx` | ✅ |
| Render NCERT badge in frontend header (above learning objectives) | `WorksheetGenerator.tsx` | ✅ |
| Add curriculum summary to answer key section | `WorksheetGenerator.tsx` | ✅ |

---

## P3 — Difficulty Breakdown Summary ✅ SHIPPED

Show explicit counts: "3 Foundation, 4 Application, 3 Stretch" — derived from `role` data already on each question.

**What P3 added:**
| Item | File | Status |
|------|------|--------|
| Color-coded difficulty bar above questions | `WorksheetGenerator.tsx` | ✅ |
| Difficulty breakdown in answer key section | `WorksheetGenerator.tsx` | ✅ |
| Difficulty line in PDF answer key | `pdf.py` | ✅ |

---

## P4 — Format Diversity Summary ✅ SHIPPED

Show question format mix: "2 MCQ, 3 Word Problems, 2 Fill-in-the-Blank, 1 Error Spot, 2 Short Answer" — derived from `type` field.

**What P4 added:**
| Item | File | Status |
|------|------|--------|
| Format pills above questions (only when 2+ formats) | `WorksheetGenerator.tsx` | ✅ |
| "Question Formats" section in answer key | `WorksheetGenerator.tsx` | ✅ |
| Format summary line in PDF answer key | `pdf.py` | ✅ |

---

## P5 — Per-Question Verification Badge ✅ SHIPPED

Checkmark on each verified answer — threads `_math_unverified` flag from Quality Reviewer through API to frontend.

**What P5 added:**
| Item | File | Status |
|------|------|--------|
| Add `verified: bool` to Question model | `models/worksheet.py` | ✅ |
| Thread `_math_unverified` → `verified` in API mapper | `worksheets_v2.py` | ✅ |
| Add `verified` to frontend Question interface | `WorksheetGenerator.tsx` | ✅ |
| Green checkmark / amber warning per answer in answer key | `WorksheetGenerator.tsx` | ✅ |
| Quality badge shows "X/Y answers verified" count | `WorksheetGenerator.tsx` | ✅ |
| Verification icon per answer in PDF answer key | `pdf.py` | ✅ |

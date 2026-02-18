# PHASES.md — Load this file only when reviewing what was built in each development phase

# Phase Summary Index

| Phase | Date | What was built |
|---|---|---|
| v1.3 baseline | 2026-02-12 | Multi-skill bundle, skill purity enforcement, add/sub expansion, role-based explanations |
| Pre-Phase | 2026-02-16 | Multi-topic worksheet engine for Class 3 Maths; verify_topics.py |
| Phase 1 | 2026-02-17 | Fix the Foundation — replaced 10 bare-except blocks, fixed _scale_recipe() bug, added console.warn logging frontend |
| Phase 3 | 2026-02-17 | Content Expansion — CBSE syllabus endpoint, Class 2 + Class 4 Maths profiles (32 total) |
| Phase 4 | 2026-02-17 | Production Hardening — subscription enforcement (10/mo free tier), History page |
| Phase 5+6 | 2026-02-17 | Teacher features — bulk generation endpoint, answer key toggle, PDF export modes |
| Phase 7 | 2026-02-17 | English Language Engine — 22 profiles, VALID_FORMATS_ENGLISH, grade-aware selectors |
| Phase 8 | 2026-02-17 | Science Engine — 7 Class 3 Science profiles, VALID_FORMATS_SCIENCE |
| Phase 9 Gold | 2026-02-17 | 7 Gold upgrades: Premium PDF, Learning Objectives, Hints, Star Badges, Indian Context Bank, Mastery-aware slots, Parent Insight footer, 5 new SVG visual types |
| Phase 10A | 2026-02-17 | Maths Class 1 — 8 topic profiles with strict grade constraints |
| Phase 10B/C/D | 2026-02-17 | Maths Class 2 guardrails + Class 4 completion + Class 5 (10 topics) |
| Phase 11A | 2026-02-17 | English Class 1 — 7 topic profiles (Alphabet, Phonics, Vocabulary, etc.) |
| Phase 11B | 2026-02-17 | English Class 5 — 9 topic profiles (Voice, Speech, Letter Writing, etc.) |
| Landing page | 2026-02-17 | World-class Landing.tsx — 12 sections, Playfair Display, scroll-reveal animations |
| Phase 12A | 2026-02-17 | EVS Class 1 & 2 — 12 Science profiles |
| Phase 12B | 2026-02-17 | Science Class 4 & 5 — 14 profiles |
| Phase 13 | 2026-02-17 | Computer Science — 15 profiles (Class 1-5) |
| Phase 14+15 | 2026-02-17 | GK (12 profiles) + Moral Science (10 profiles) |
| Phase 16 | 2026-02-17 | Health & PE — 15 profiles (Class 1-5) |
| P2 Growth | 2026-02-17 | Parent Dashboard, WhatsApp Share, Hindi Class 3 engine |
| Phase 18 | 2026-02-17 | Hindi Expansion — 19 profiles (Class 1/2/4/5), Devanagari throughout |
| Bug fixes | 2026-02-17 | Teacher routing bug, free tier upgrade CTA, E2E 26/26 pass |

---

## Current Totals (as of 2026-02-18)

- **196 topic profiles** across 9 subjects
- **9 subjects**: Maths, English, Science/EVS, Hindi, Computer, GK, Moral Science, Health & PE
- **5 classes**: Class 1–5
- **2129 deterministic checks** passing in verify_topics.py

## Key Files per Phase

| What to look at | File |
|---|---|
| Core pipeline | `backend/app/services/slot_engine.py` |
| Skill contracts | `backend/app/skills/` |
| PDF generation | `backend/app/services/pdf.py` |
| API routers | `backend/app/api/` |
| React pages | `frontend/src/pages/` |
| Visual components | `frontend/src/components/VisualProblem.tsx` |
| Landing page | `frontend/src/pages/Landing.tsx` |
| Dashboard | `frontend/src/pages/ParentDashboard.tsx` |

For full dated log with details, see `docs/CHANGELOG.md`.

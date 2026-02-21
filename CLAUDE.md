# CLAUDE.md

PracticeCraft AI generates CBSE-aligned worksheets for Class 1–5 (Maths, English, Science, Hindi + 5 more subjects). A FastAPI backend runs a slot-based LLM pipeline; a React frontend renders SVG visuals and PDF exports. Deployed on Railway (backend) + Vercel (frontend, `ed-tech-drab.vercel.app`).

## Project Structure

```
backend/app/
  api/          # 14 FastAPI routers (worksheets, children, subscription…)
  services/     # slot_engine.py — core worksheet pipeline
  skills/       # skill contracts (carry/borrow enforcement)
  core/         # config.py
  scripts/      # test_slot_engine.py, verify_topics.py
frontend/src/
  pages/        # React pages
  components/   # UI + shadcn/ui
  lib/          # api.ts — axios + Supabase auth injection
  hooks/ types/ # custom hooks, TypeScript types
```

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, Supabase (Postgres + Auth) |
| Frontend | React 18, Vite, TailwindCSS v4, shadcn/ui |
| AI | Anthropic Claude API (worksheet generation) |
| Deploy | Railway (backend), Vercel (frontend) |

## Environment Variables

**Backend required:** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`), `OPENAI_API_KEY`
**Backend optional:** `DEBUG`, `FRONTEND_URL`, `ENABLE_TELEMETRY_DB`, `ENABLE_ATTEMPT_AUDIT_DB`, `PRACTICECRAFT_MASTERY_STORE`
**Frontend:** `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`, `VITE_SITE_URL`

## 7 Non-Negotiable Rules

1. **Deterministic-first** — LLM fills content only. Backend owns structure, slot plans, and all repair logic. No LLM calls for fixing.
2. **No silent failures** — Every `except` block must log. Never use bare `except: pass`.
3. **Slot discipline** — Slot counts must exactly match the plan. `enforce_slot_counts()` is last resort only.
4. **Never relax carry/borrow** — `has_carry()`/`has_borrow()` checks are non-negotiable. Fall back to hardcoded CARRY_PAIRS.
5. **shadcn/ui path** — CLI installs to `frontend/@/components/ui/`. Manually move to `frontend/src/components/ui/`.
6. **Grep after replace_all** — Stale references cause NameError at runtime.
7. **Regex at module level** — All patterns must be defined before any function that uses them.

## Validation Commands

```bash
# Backend — 2129 checks, no LLM needed
cd backend && python scripts/verify_topics.py

# Frontend — type-check + build
cd frontend && npm run build
```

## Dev Commands

```bash
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev    # :5173
cd frontend && npm run lint
```

## Reference — Load These Files as Needed

| Working on… | Load this file |
|---|---|
| Topics, subject coverage, 196 profiles, slot plans, valid formats | `docs/CURRICULUM.md` |
| Database tables, Supabase schema, RLS, API routes, env vars | `docs/SCHEMA.md` |
| Pipeline details, validators, visual rendering, known issues, gotchas | `docs/RULES.md` |
| Phase history — what was built in each phase, key files | `docs/PHASES.md` |
| Dated changelog / full update log | `docs/CHANGELOG.md` |

## Status

**Live:** 196 topic profiles, 9 subjects (Class 1–5), slot engine v4.0, PDF export, mastery tracking, WhatsApp share, Hindi Devanagari.
**Incomplete:** Payment integration (Stripe/Razorpay placeholder in `subscription.py`).

## Pre-commit Hook

The hook auto-appends file paths to `# Update Log` in `docs/CHANGELOG.md`. **Replace the path list with a human-readable summary before finalising the commit.**
- **2026-02-18**: Changes in agents, docs
- **2026-02-19**: Changes in backend/app/services, backend/scripts, backend/tests
- **2026-02-21**: Changes in backend/app/data/scenario_pools, backend/app/services, backend/app/utils, backend/tests

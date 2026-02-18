# SCHEMA.md — Load this file only when working on database tables, Supabase schema, or API routes

# Database Schema

All tables use **Row-Level Security (RLS)** with Supabase Auth policies. Full SQL in `backend/supabase_schema.sql`.

| Table | Key columns |
|---|---|
| **worksheets** | id (UUID), user_id, title, board, grade, subject, topic, difficulty, language, questions (JSONB), child_id, class_id, regeneration_count, timestamps |
| **children** | id (UUID), user_id, name, grade, board, notes, timestamps |
| **user_subscriptions** | id (UUID), user_id (UNIQUE), tier (free/paid), worksheets_generated_this_month, month_reset_at, timestamps. Auto-created via trigger |
| **user_profiles** | user_id (UNIQUE), role (parent/teacher), active_role, subjects[], grades[], school_name, timestamps |
| **teacher_classes** | id (UUID), user_id, name, grade, subject, board, syllabus_source (cbse/custom), custom_syllabus (JSONB), timestamps |
| **cbse_syllabus** | id (UUID), grade, subject, chapters (JSONB), UNIQUE(grade, subject), timestamps |
| **topic_preferences** | id (UUID), user_id, child_id, subject, selected_topics (JSONB), UNIQUE(child_id, subject), timestamps |
| **child_engagement** | id (UUID), user_id, child_id (UNIQUE), total_stars, current_streak, longest_streak, last_activity_date, total_worksheets_completed, timestamps |
| **mastery_state** | PK (student_id, skill_tag), streak, total_attempts, correct_attempts, last_error_type, mastery_level (unknown/learning/improving/mastered), updated_at |
| **attempt_events** | student_id, worksheet_id, attempt_id, question, student_answer, grade_result, mastery_before/after, ts. Gated by `ENABLE_ATTEMPT_AUDIT_DB=1` |
| **telemetry_events** | event, route, version, student_id, skill_tag, error_type, latency_ms, ok, ts. Gated by `ENABLE_TELEMETRY_DB=1` |
| **share_tokens** | token, worksheet_id, created_by, expires_at. Used for public WhatsApp share links |

---

# API Surface

| Endpoint | File | Notes |
|---|---|---|
| `POST /api/worksheets/` | `worksheets.py` | Legacy generation + PDF export |
| `GET/POST /api/v1/worksheets/` | `worksheets_v1.py` | v1: generate, grade, explain, recommend, drill, chain, attempt, mastery |
| `POST /api/v1/worksheets/bulk` | `worksheets_v1.py` | Parallel multi-topic (paid only, max 5 topics) |
| `GET /api/v1/dashboard/` | `dashboard.py` | Parent progress dashboard |
| `GET/POST /api/children/` | `children.py` | Child profile CRUD |
| `GET/POST /api/users/` | `users.py` | User management |
| `GET/POST /api/classes/` | `classes.py` | Teacher class management |
| `GET /api/subscription/` | `subscription.py` | Subscription status (free: 10/month) |
| `GET /api/syllabus/` | `syllabus.py` | Syllabus tree (partially implemented) |
| `GET /api/cbse-syllabus/` | `cbse_syllabus.py` | CBSE syllabus Class 1-5 Maths & English (hardcoded) |
| `GET /api/curriculum/` | `curriculum.py` | Curriculum endpoints |
| `GET/POST /api/topic-preferences/` | `topic_preferences.py` | User topic preferences |
| `POST /api/engagement/` | `engagement.py` | Engagement tracking |
| `POST /api/worksheets/{id}/share` | `share.py` | Generate public share link |
| `GET /api/shared/{token}` | `share.py` | Public worksheet viewer (no auth) |
| `GET /api/analytics/` | `analytics.py` | Analytics endpoints |
| `GET /health` | `health.py` | Health check |

---

# Frontend API Layer

- `frontend/src/lib/api.ts` — axios with Supabase auth token injected automatically
- `apiV1WithFallback()` — tries v1 endpoint first, falls back to legacy `/api/worksheets/` on 404/500 (logs warning, does not swallow silently)
- CORS configured for: `localhost:3000`, `localhost:5173`, `localhost:5174`, `ed-tech-drab.vercel.app`

---

# Environment Variables

## Backend
| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | — | Service role key (also accepts `SUPABASE_SERVICE_ROLE_KEY`) |
| `OPENAI_API_KEY` | Yes | — | LLM for worksheet generation |
| `DEBUG` | No | `false` | Debug mode |
| `FRONTEND_URL` | No | `http://localhost:5173` | CORS + redirect URLs |
| `ENABLE_TELEMETRY_DB` | No | off | Write telemetry to DB |
| `ENABLE_ATTEMPT_AUDIT_DB` | No | off | Write attempt events to DB |
| `PRACTICECRAFT_MASTERY_STORE` | No | `memory` | `supabase` to persist mastery state |

## Frontend
| Variable | Purpose |
|---|---|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous key |
| `VITE_API_URL` | Backend URL (default `http://localhost:8000`) |
| `VITE_SITE_URL` | Site URL for OAuth redirects |

---

# Incomplete Features (Known)

- `subscription.py:upgrade_to_paid()` — no payment verification (Stripe/Razorpay placeholder)
- `syllabus.py:parse_syllabus()` — returns raw_response only; no structured parsing
- `syllabus.py:get_syllabus()` — returns "not implemented yet"

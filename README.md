# Skolar

AI-powered CBSE worksheet generation platform for Indian primary school students (Classes 1-5).

## Architecture

```
Frontend (React + Vite)          Backend (FastAPI)
       |                              |
       |--- Supabase Auth ----------->|
       |--- REST API ----------------->|
       |                              |--- Gemini 2.5 Flash (AI generation)
       |                              |--- Supabase (Postgres + Auth)
       |                              |--- Curriculum RAG (NCERT context)
```

## Features

- **Worksheets** -- AI-generated, CBSE-aligned worksheets for 9 subjects, 198 topics
- **Revision Notes** -- Structured revision with key concepts, worked examples, memory tips
- **Flashcards** -- Generate and print study cards with front/back format
- **Grading** -- Photo-grade handwritten answers using Gemini Vision
- **Textbook Upload** -- Snap a textbook page, generate practice questions
- **Ask Skolar** -- AI tutor chat for homework help with multi-turn conversations
- **Progress Dashboard** -- Parent dashboard with mastery tracking and streaks

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18, Vite, TailwindCSS v4, shadcn/ui |
| Backend | Python 3.11+, FastAPI, Pydantic |
| AI | Google Gemini 2.5 Flash |
| Database | Supabase (Postgres + Auth + RLS) |
| Deploy | Railway (backend), Vercel (frontend) |
| CI/CD | GitHub Actions (lint, test, security scan, Docker build) |
| Monitoring | Sentry (opt-in), structlog (JSON structured logging) |

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.11+
- Supabase project (for database + auth)
- Gemini API key

### Backend

```bash
cd backend
cp .env.example .env   # Fill in your credentials
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Deep health: http://localhost:8000/health/deep

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Available at http://localhost:5173

## Project Structure

```
backend/
  app/
    api/           # FastAPI routers (worksheets, revision, flashcards, grading, ...)
    services/      # AI client, curriculum RAG, caching, PDF generation
    middleware/     # Rate limiting, security headers, request tracing
    data/          # Topic profiles, learning objectives
    core/          # Config, logging, dependencies
  tests/           # pytest test suite (333 tests)
  scripts/         # Population scripts

frontend/
  src/
    pages/         # React pages
    components/    # UI components + shadcn/ui
    lib/           # API client, Supabase auth
    hooks/         # Custom React hooks
```

## Environment Variables

See `backend/.env.example` for the full list. Required:

- `SUPABASE_URL` -- Supabase project URL
- `SUPABASE_SERVICE_KEY` -- Supabase service role key
- `GEMINI_API_KEY` -- Google Gemini API key

## Running Tests

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

## License

Private -- All rights reserved.

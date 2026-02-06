# PracticeCraft AI

AI-powered worksheet generation platform for educators.

## Project Structure

```
edTech/
├── frontend/          # React + Vite + TypeScript + Tailwind + shadcn/ui
├── backend/           # Python + FastAPI
└── README.md
```

## Getting Started

### Prerequisites

- Node.js 20+
- pnpm
- Python 3.11+
- uv (Python package manager)

### Environment Setup

1. Copy environment templates:
   ```bash
   cp .env.example .env
   cp frontend/.env.example frontend/.env
   cp backend/.env.example backend/.env
   ```

2. Fill in your credentials in the `.env` files.

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The frontend will be available at http://localhost:5173

### Backend

```bash
cd backend
uv run uvicorn app.main:app --reload
```

The backend will be available at http://localhost:8000

- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

## Tech Stack

### Frontend
- React 19
- TypeScript
- Vite 7
- Tailwind CSS 4
- shadcn/ui
- Supabase Client
- Axios

### Backend
- Python 3.11
- FastAPI
- Pydantic
- OpenAI
- Supabase

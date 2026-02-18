# Phase 1: Child Learning Graph — Load this file when working on learning graph, mastery tracking, or topic_mastery table

# PracticeCraft — Phase 1: Child Learning Graph
## Instructions for Claude Code

---

## HOW TO USE THIS FILE

This file contains 5 tasks. **Run them one at a time.**

For each task:
1. Open Claude Code in your project folder
2. Copy the exact prompt from that task section
3. Paste it and press Enter
4. Wait for Claude Code to finish
5. Run the validation command shown
6. Only move to the next task when validation passes

**Do not paste multiple tasks at once. Do not skip the validation steps.**

---

## CONTEXT (read this once before starting)

You are building on an existing project called PracticeCraft.

- **Backend:** FastAPI (Python) — running on Railway
- **Database:** Supabase (PostgreSQL)
- **Frontend:** React + Vite + TailwindCSS — running on Vercel
- **The existing mastery system** lives in `backend/app/services/mastery_store.py`
- **The grading endpoint** lives in `backend/app/api/worksheets.py`
- **The generate endpoint** lives in `backend/app/api/generate.py` (or similar)
- **Existing tables in Supabase:** `children`, `worksheets`, `mastery_state`, `user_subscriptions`

We are adding a new intelligence layer called the **Child Learning Graph (CLG)**.
It tracks per-child learning history, mastery transitions, and adaptive difficulty.
We are NOT modifying any existing tables. Everything is additive.

---

---

# TASK 1 of 5 — Supabase Schema

## COPY THIS ENTIRE PROMPT INTO CLAUDE CODE:

```
I am building PracticeCraft, a CBSE worksheet generator for Classes 1-5.

I need you to help me add 3 new tables to my Supabase database for the Child Learning Graph feature.

Here is exactly what to do:

STEP 1: Find my Supabase schema file.
Look for a file called supabase_schema.sql or similar in the project.
If it does not exist, create it at the project root as supabase_schema.sql.

STEP 2: Add the following SQL to the end of that file (do not remove anything existing):

-- ============================================================
-- PHASE 1: CHILD LEARNING GRAPH TABLES
-- These are purely additive. Do not modify existing tables.
-- ============================================================

-- TABLE 1: Every worksheet attempt by every child
CREATE TABLE IF NOT EXISTS learning_sessions (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at        TIMESTAMPTZ DEFAULT now() NOT NULL,
  child_id          UUID REFERENCES children(id) ON DELETE CASCADE,
  worksheet_id      UUID REFERENCES worksheets(id) ON DELETE SET NULL,
  topic_slug        TEXT NOT NULL,
  subject           TEXT NOT NULL,
  grade             INTEGER NOT NULL,
  bloom_level       TEXT NOT NULL DEFAULT 'recall',
  score_pct         INTEGER,
  questions_total   INTEGER DEFAULT 0,
  questions_correct INTEGER DEFAULT 0,
  duration_seconds  INTEGER,
  format_results    JSONB DEFAULT '{}',
  error_tags        TEXT[] DEFAULT '{}',
  mastery_before    TEXT,
  mastery_after     TEXT
);

-- TABLE 2: Current mastery state per child per topic
CREATE TABLE IF NOT EXISTS topic_mastery (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  child_id          UUID REFERENCES children(id) ON DELETE CASCADE,
  topic_slug        TEXT NOT NULL,
  subject           TEXT NOT NULL,
  grade             INTEGER NOT NULL,
  mastery_level     TEXT NOT NULL DEFAULT 'unknown',
  streak            INTEGER DEFAULT 0,
  sessions_total    INTEGER DEFAULT 0,
  sessions_correct  INTEGER DEFAULT 0,
  last_practiced_at TIMESTAMPTZ,
  last_error_type   TEXT,
  format_weakness   TEXT,
  bloom_ceiling     TEXT DEFAULT 'recall',
  revision_due_at   TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at        TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE(child_id, topic_slug)
);

-- TABLE 3: Summary per child (used by parent dashboard)
CREATE TABLE IF NOT EXISTS child_learning_summary (
  child_id          UUID REFERENCES children(id) ON DELETE CASCADE PRIMARY KEY,
  mastered_topics   TEXT[] DEFAULT '{}',
  improving_topics  TEXT[] DEFAULT '{}',
  needs_attention   TEXT[] DEFAULT '{}',
  strongest_subject TEXT,
  weakest_subject   TEXT,
  total_sessions    INTEGER DEFAULT 0,
  total_questions   INTEGER DEFAULT 0,
  overall_accuracy  INTEGER DEFAULT 0,
  learning_velocity TEXT DEFAULT 'normal',
  last_updated_at   TIMESTAMPTZ DEFAULT now()
);

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_ls_child ON learning_sessions(child_id);
CREATE INDEX IF NOT EXISTS idx_ls_child_topic ON learning_sessions(child_id, topic_slug);
CREATE INDEX IF NOT EXISTS idx_tm_child ON topic_mastery(child_id);
CREATE INDEX IF NOT EXISTS idx_tm_child_slug ON topic_mastery(child_id, topic_slug);

-- RLS POLICIES (users only see their own children's data)
ALTER TABLE learning_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_mastery ENABLE ROW LEVEL SECURITY;
ALTER TABLE child_learning_summary ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_see_own_child_sessions" ON learning_sessions
  FOR ALL USING (child_id IN (SELECT id FROM children WHERE user_id = auth.uid()));

CREATE POLICY "users_see_own_topic_mastery" ON topic_mastery
  FOR ALL USING (child_id IN (SELECT id FROM children WHERE user_id = auth.uid()));

CREATE POLICY "users_see_own_summary" ON child_learning_summary
  FOR ALL USING (child_id IN (SELECT id FROM children WHERE user_id = auth.uid()));

STEP 3: Tell me the exact steps to run this SQL in my Supabase dashboard.
I am new to this — give me step by step instructions (open Supabase > SQL Editor > paste > run).

STEP 4: Do NOT connect to Supabase from code yet. Just prepare the SQL file.
```

## VALIDATION (do this after Claude Code finishes):
1. Open your Supabase project dashboard
2. Go to SQL Editor
3. Paste and run the SQL
4. Go to Table Editor — you should see 3 new tables: `learning_sessions`, `topic_mastery`, `child_learning_summary`
5. If you see them — Task 1 is done ✅

---

---

# TASK 2 of 5 — Learning Graph Service

## ONLY START THIS AFTER TASK 1 VALIDATION PASSES

## COPY THIS ENTIRE PROMPT INTO CLAUDE CODE:

```
I am building PracticeCraft, a CBSE worksheet generator.

I need you to create a new Python service file for the Child Learning Graph.

CONTEXT:
- Backend is FastAPI in Python
- Database is Supabase
- The existing mastery service is at backend/app/services/mastery_store.py
- Mastery levels in the system are: unknown, learning, improving, mastered (in that order)

STEP 1: Read the existing mastery_store.py file so you understand the current pattern.

STEP 2: Create a new file at backend/app/services/learning_graph.py with the following logic:

The service must have these 5 methods:

METHOD 1: record_session(child_id, topic_slug, subject, grade, bloom_level, format_results, error_tags, score_pct, questions_total, questions_correct, worksheet_id=None)
- Gets current mastery state for this child+topic from topic_mastery table
- Computes new mastery level using these exact rules:
  * score_pct >= 70 → streak increases by 1, else streak resets to 0
  * unknown + streak >= 1 → learning
  * learning + streak >= 3 → improving
  * improving + streak >= 5 → mastered
  * score_pct < 50 (fail) → regress one level down
  * mastered + no practice in 14 days → improving (spaced repetition decay)
  * improving + no practice in 21 days → learning (spaced repetition decay)
- Finds the weakest question format: whichever format in format_results has lowest correct/total ratio
- Writes a new row to learning_sessions table
- Upserts the topic_mastery row (create if not exists, update if exists)
- Calls _update_child_summary(child_id) after
- Returns a dict with: mastery_before, mastery_after, mastery_changed (True/False), new_streak

METHOD 2: get_child_graph(child_id)
- Reads all topic_mastery rows for this child
- Groups them by subject: {maths: {topic_slug: {mastery_level, streak, last_practiced_at}}}
- Returns that grouped dict

METHOD 3: get_child_summary(child_id)
- Reads the child_learning_summary row for this child
- Returns it as a dict
- If no row exists yet, return empty defaults

METHOD 4: get_adaptive_difficulty(child_id, topic_slug)
- Reads topic_mastery for this child+topic
- Returns a dict based on mastery_level:
  * unknown or first session: {bloom_level: recall, scaffolding: True, challenge_mode: False, format_mix: {mcq: 50, fill_blank: 30, word_problem: 20}}
  * learning: {bloom_level: recall, scaffolding: True, challenge_mode: False, format_mix: boost weak format by 20%}
  * improving: {bloom_level: application, scaffolding: False, challenge_mode: False, format_mix: {mcq: 30, fill_blank: 30, word_problem: 40}}
  * mastered: {bloom_level: reasoning, scaffolding: False, challenge_mode: True, format_mix: {mcq: 20, fill_blank: 30, word_problem: 50}}

METHOD 5 (private): _update_child_summary(child_id)
- Reads all topic_mastery rows for this child
- Splits topics into 3 lists: mastered_topics, improving_topics, needs_attention (unknown or learning)
- Finds strongest_subject (most mastered topics) and weakest_subject (most needs_attention topics)
- Counts total_sessions and total_questions from learning_sessions
- Calculates overall_accuracy as average score_pct
- Upserts child_learning_summary row

STEP 3: Create a test file at backend/tests/test_learning_graph.py
Write tests that verify:
- unknown + 1 correct → learning
- learning + 3 correct in a row → improving
- improving + 5 correct in a row → mastered
- mastered + wrong answer → improving
- score < 50 always regresses one level

STEP 4: Run the tests and show me the output.
Fix any failures before saying you are done.
```

## VALIDATION:
Run this in your terminal from the backend folder:
```
pytest backend/tests/test_learning_graph.py -v
```
All tests must pass (green). If any fail, paste the error back into Claude Code and say "fix this".

---

---

# TASK 3 of 5 — Wire Grading to Learning Graph

## ONLY START THIS AFTER TASK 2 VALIDATION PASSES

## COPY THIS ENTIRE PROMPT INTO CLAUDE CODE:

```
I am building PracticeCraft, a CBSE worksheet generator.

I have a new LearningGraphService at backend/app/services/learning_graph.py.
I need to wire it into the grading endpoint so every graded worksheet feeds the Learning Graph.

STEP 1: Find the grading endpoint.
Look for a route that handles worksheet answer submission / grading.
It is probably in backend/app/api/worksheets.py or similar.
Read that file carefully before making any changes.

STEP 2: Add the following logic AFTER the existing grade calculation,
WITHOUT changing how the existing grade calculation works:

2a. Compute format_results — a dict showing how the child did per question format:
- Loop through the worksheet questions
- Group them by question format/type (mcq, fill_blank, word_problem, column_setup, etc.)
- For each group, count: how many questions total, how many correct
- Result: {mcq: {correct: 3, total: 5}, fill_blank: {correct: 1, total: 3}}
- If the worksheet doesn't have format info, use an empty dict {}

2b. Compute error_tags — a list of semantic error labels from wrong answers:
- For now, keep this simple: if the topic is maths, return ['calculation_error'] for any wrong answer
- We will make this smarter later
- If all correct, return []

2c. Import and call LearningGraphService.record_session() with:
- child_id: from the submission (if available) or None
- topic_slug: from the worksheet
- subject: from the worksheet
- grade: from the worksheet
- bloom_level: from the worksheet, default to 'recall' if not set
- format_results: from step 2a
- error_tags: from step 2b
- score_pct: the existing calculated score
- questions_total: total question count
- questions_correct: correct answer count
- worksheet_id: the worksheet id

2d. Add the Learning Graph result to the response:
- mastery_level: session_result['mastery_after']
- mastery_changed: session_result['mastery_changed']
- streak: session_result['new_streak']

IMPORTANT:
- If LearningGraphService raises any error, catch it, log it, but DO NOT let it break the grading response
- The existing grading must always work even if the Learning Graph write fails
- Wrap the Learning Graph call in try/except

STEP 3: Check that child_id is being passed in the grading request.
If the GradeSubmission model does not have child_id, add it as an optional field (child_id: Optional[str] = None).

STEP 4: Tell me what you changed and show me the relevant code section.
```

## VALIDATION:
1. Start your backend server locally (or check Railway logs after deploy)
2. Generate a worksheet, answer it, submit the answers
3. Go to Supabase Table Editor → learning_sessions table
4. You should see a new row appear after each graded worksheet ✅

---

---

# TASK 4 of 5 — Adaptive Generation

## ONLY START THIS AFTER TASK 3 VALIDATION PASSES

## COPY THIS ENTIRE PROMPT INTO CLAUDE CODE:

```
I am building PracticeCraft, a CBSE worksheet generator.

I have a LearningGraphService with a get_adaptive_difficulty() method.
I need to wire it into the worksheet generation endpoint so worksheets adapt to each child.

STEP 1: Find the generation endpoint.
Look for a route that generates worksheets — probably in backend/app/api/generate.py or worksheets.py.
Read that file carefully before changing anything.

STEP 2: Find where the slot engine or LLM prompt is called to generate questions.

STEP 3: BEFORE that generation call, add this logic:

3a. If the request includes a child_id:
- Import LearningGraphService
- Call get_adaptive_difficulty(child_id, topic_slug)
- Store the result as difficulty_config

3b. If no child_id, use these safe defaults:
difficulty_config = {
  bloom_level: 'recall',
  scaffolding: True,
  challenge_mode: False,
  format_mix: {mcq: 40, fill_blank: 30, word_problem: 30}
}

STEP 4: Pass difficulty_config into the generation call.
Look at how the generation function/prompt is built and add these parameters:
- bloom_level from difficulty_config
- format_mix from difficulty_config (what % of each question type to generate)
- If scaffolding is True, add a note to the prompt: "Include helpful hints and examples for each question"
- If challenge_mode is True, add a note to the prompt: "Make questions more challenging with multi-step problems"

IMPORTANT:
- If get_adaptive_difficulty() raises any error, catch it and use the safe defaults above
- The generation must always work even if the Learning Graph read fails
- Do not break any existing generation functionality

STEP 5: Add child_id as an optional field to the generation request model if it is not already there.

STEP 6: Show me the updated generation endpoint and confirm the change is working.
```

## VALIDATION:
1. Generate a worksheet WITHOUT child_id — should work exactly as before ✅
2. Generate a worksheet WITH child_id for a child who has graded worksheets —
   check that the bloom_level in the response matches what you'd expect from their mastery level ✅

---

---

# TASK 5 of 5 — API Endpoints for Learning Graph Data

## ONLY START THIS AFTER TASK 4 VALIDATION PASSES

## COPY THIS ENTIRE PROMPT INTO CLAUDE CODE:

```
I am building PracticeCraft, a CBSE worksheet generator.

I need to create API endpoints that expose the Child Learning Graph data.
These will power the parent dashboard and teacher dashboard later.

STEP 1: Create a new file at backend/app/api/learning_graph.py

STEP 2: Add these 5 endpoints:

ENDPOINT 1: GET /children/{child_id}/graph
- Calls LearningGraphService.get_child_graph(child_id)
- Returns the full graph grouped by subject
- Requires the logged-in user to own this child (check children table)
- Return 403 if user does not own this child

ENDPOINT 2: GET /children/{child_id}/graph/summary
- Calls LearningGraphService.get_child_summary(child_id)
- Returns mastered_topics, improving_topics, needs_attention lists
- Same ownership check as above

ENDPOINT 3: GET /children/{child_id}/graph/history
- Reads last 20 rows from learning_sessions for this child (ordered by created_at DESC)
- Accepts optional query param: ?limit=20 (max 50)
- Returns: [{topic_slug, subject, score_pct, mastery_before, mastery_after, created_at}]

ENDPOINT 4: GET /children/{child_id}/graph/recommendation
- Reads topic_mastery for this child
- Returns the single highest-priority topic to practice next
- Priority order: needs_attention first (unknown or learning mastery), then improving, then mastered (for revision)
- If needs_attention has topics, pick the one not practiced in the longest time
- Return: {topic_slug, subject, reason, mastery_level}

ENDPOINT 5: GET /children/{child_id}/graph/report
- Reads child_learning_summary for this child
- Also reads the child's name from the children table
- Returns a plain-English parent-friendly text report like:
  "[Name] has mastered [X] topics including [list]. They are still developing [Y] topics.
   We recommend practicing [recommendation topic] next."
- Generate this text in Python using simple string formatting (no LLM needed yet)

STEP 3: Register these endpoints in the main app router.
Find where other routers are registered (probably in backend/app/main.py or backend/app/api/__init__.py).
Add: app.include_router(learning_graph_router, prefix="/api", tags=["learning-graph"])

STEP 4: Test each endpoint using curl or the FastAPI docs (/docs).
Show me the response for each endpoint.
```

## VALIDATION:
Open your backend URL + /docs (e.g. https://your-app.railway.app/docs)
You should see 5 new endpoints under "learning-graph" section.
Test each one manually. All 5 must return responses without errors ✅

---

---

# FINAL END-TO-END TEST

## COPY THIS PROMPT INTO CLAUDE CODE AFTER ALL 5 TASKS PASS:

```
I have completed all 5 tasks for the Child Learning Graph feature in PracticeCraft.

Please run a full end-to-end verification:

STEP 1: Check that all 3 new Supabase tables exist (learning_sessions, topic_mastery, child_learning_summary)

STEP 2: Check that backend/app/services/learning_graph.py exists and has all 5 methods

STEP 3: Check that the grading endpoint imports and calls LearningGraphService

STEP 4: Check that the generation endpoint imports and calls get_adaptive_difficulty

STEP 5: Check that backend/app/api/learning_graph.py exists with 5 endpoints

STEP 6: Run all tests: pytest backend/tests/ -v

STEP 7: Tell me what is working and what (if anything) still needs attention.
Summarize in plain English what Phase 1 has built and what it means for the product.
```

---

---

# TROUBLESHOOTING — Common Issues

## "I can't find the file you're looking for"
Say to Claude Code: "Search the entire project for [filename or function name] and tell me where it is"

## "There's an import error"
Say to Claude Code: "There is an import error. Read the full error message below and fix it: [paste error]"

## "The test is failing"
Say to Claude Code: "This test is failing. Read the test file and the service file and fix the logic: [paste error]"

## "I don't know if Supabase tables were created"
Say to Claude Code: "Tell me step by step how to check if my Supabase tables were created successfully in the Supabase dashboard"

## "Something broke that was working before"
Say to Claude Code: "Something that was working before is now broken. I only want you to fix the issue I gave you — please do not change any other files. Here is the error: [paste error]"

## General rule
If Claude Code changes more than 3 files at once, ask: "Why did you change all these files? I only asked for one thing. Please explain what each change does."

---

# WHAT YOU HAVE WHEN ALL 5 TASKS PASS

- Every child's worksheet history is permanently stored in Supabase (survives server restarts)
- Every child has a mastery level per topic that updates automatically after grading
- New worksheets automatically get harder (or gentler) based on the child's history
- 5 API endpoints ready for the Parent Dashboard (Phase 3) to plug into
- The foundation for Gold Class, Teacher Reports, and School Tier is in place

**This is the most important thing you will build in PracticeCraft. Everything else sits on top of it.**

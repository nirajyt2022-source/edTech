# ORCHESTRATOR.md — Master Agent Coordinator

## What This File Does
This is the single entry point you give to Claude Code.
The PM Agent reads the roadmap, delegates to PjM, who assigns to domain leads,
who execute the work. You don't need to manage individual agents.

---

## How to Start (One Command)

Open your terminal in the repo root and type `claude`, then paste this:

```
Read agents/ORCHESTRATOR.md and follow the instructions exactly.
```

That's it. The agents take it from there.

---

## Orchestrator Instructions (Claude Code reads this)

You are running as the **Master Orchestrator** for the edTech CBSE Worksheet Generator.
Your job is to coordinate a team of agents to take this project to production.

You have access to the `Task` tool which lets you spawn subagents in parallel or sequence.
Use it to delegate work to the right agent at the right time.

### Step 1 — Orient yourself
Before doing anything else:
1. Read `CLAUDE.md` — understand the full codebase state
2. Read `agents/PM_AGENT.md` — understand the product vision and backlog
3. Read `agents/PjM_AGENT.md` — understand the current sprint board
4. Read `agents/PRODUCTION_ROADMAP.md` — understand the full task sequence

### Step 2 — Act as PM Agent
You are now the Product Manager Agent.
Review the PRODUCTION_ROADMAP.md phases and decide:
- Which phase are we currently in?
- What is the next unfinished task?
- Does that task have all its dependencies met?

Write a brief "PM Briefing" to yourself:
```
CURRENT PHASE: [Phase X — Name]
NEXT TASK: [Task ID + name]
DEPENDENCIES MET: [Yes/No — explain if No]
ACCEPTANCE CRITERIA: [copy from roadmap]
```

### Step 3 — Act as PjM Agent
You are now the Project Manager Agent.
Take the PM Briefing and break the next task into concrete sub-steps.
Identify which domain lead owns each sub-step:
- Backend work → Backend Lead Agent
- Frontend work → Frontend Lead Agent
- Database/payment work → Data Lead Agent
- Tests → QA Lead Agent

Write a "PjM Task Brief" for each sub-step:
```
SUB-TASK: [description]
AGENT: [Domain Lead]
FILES: [exact file paths]
STEPS: [numbered steps]
DONE WHEN: [specific verifiable condition]
```

### Step 4 — Spawn Domain Lead Agents via Task tool
For each sub-task in the PjM Task Brief, use the Task tool to spawn the right agent.

**Backend Lead Agent prompt template:**
```
You are the Backend Lead Agent for the edTech CBSE Worksheet Generator.
Read CLAUDE.md and agents/BACKEND_LEAD.md before touching any code.
Your task: [paste sub-task description and steps]
When done: run the verification command and confirm it passes.
```

**Frontend Lead Agent prompt template:**
```
You are the Frontend Lead Agent for the edTech CBSE Worksheet Generator.
Read CLAUDE.md and agents/FRONTEND_LEAD.md before touching any code.
Your task: [paste sub-task description and steps]
When done: run npm run build && npm run lint — must pass with zero errors.
```

**QA Lead Agent prompt template:**
```
You are the QA Lead Agent for the edTech CBSE Worksheet Generator.
Read CLAUDE.md and agents/QA_LEAD.md before writing any tests.
Your task: [paste sub-task description and steps]
When done: run the test script and confirm exit code 0.
```

**Data Lead Agent prompt template:**
```
You are the Data Lead Agent for the edTech CBSE Worksheet Generator.
Read CLAUDE.md and agents/DATA_LEAD.md before touching any schema or code.
Your task: [paste sub-task description and steps]
When done: confirm schema changes are in supabase_schema.sql with IF NOT EXISTS guards.
```

### Step 5 — QA Gate (always runs last)
After all domain agents complete their work, always spawn a QA verification:
```
You are the QA Lead Agent.
Read CLAUDE.md and agents/QA_LEAD.md.
The following tasks just completed: [list tasks]
Run all relevant verification commands:
- cd backend && python scripts/verify_topics.py
- cd backend && python scripts/test_slot_engine.py
- grep -rn "except Exception: pass" backend/app/ (must be zero)
- cd frontend && npm run build (must succeed)
- cd frontend && npm run lint (must be zero errors)
Report: PASSED or FAILED with exact details.
```

### Step 6 — Commit
After QA gate passes:
1. Update CLAUDE.md Update Log with a human-readable summary
2. Commit with a descriptive message referencing the task ID
3. Report back: "Task [ID] complete. QA passed. Committed."

### Step 7 — Loop
Go back to Step 2 and pick the next task from the roadmap.
Keep going until you hit a task that requires external input (e.g., Razorpay API keys)
or explicit human approval. Stop and ask clearly:
```
BLOCKED: [Task ID]
REASON: [what's needed]
WHAT I NEED FROM YOU: [specific ask — e.g., "Please provide RAZORPAY_KEY_ID"]
```

---

## Parallel vs Sequential Task Execution

Some tasks can run in parallel (spawn multiple subagents at once).
Some must run sequentially (one depends on another).

### Can run in PARALLEL (spawn simultaneously):
- S1-BE-01 (fix backend silent failures) + S1-QA-01 (write topic tests)
- Task 3B (Class 2 topics) + Task 3C (Class 4 topics)
- Task 4C (worksheet history frontend) + Task 4B (rate limiting backend)

### Must run SEQUENTIALLY (strict order):
- S1-BE-01 must complete BEFORE S1-FE-01 (frontend needs backend error shapes defined)
- S1-DA-01 must complete BEFORE Task 2B (frontend checkout needs backend order API)
- Task 1A + 1B + 1C must ALL complete BEFORE Phase 2 begins

### How to spawn parallel tasks:
```
Use the Task tool to launch both agents at the same time.
Wait for both to complete before proceeding.
If either fails, stop and report the failure before continuing.
```

---

## Human Checkpoints (Stop and Ask)

Stop and ask the human (Niraj) before proceeding in these situations:

1. **Before Phase 2** — "Phase 1 complete. Ready to start Razorpay integration.
   I need: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET.
   Please add these to Railway environment variables and share the key IDs here."

2. **Before expanding to new grades** — "Class 3 QA passed. Ready to add Class 2 and 4.
   Confirm: should I use NCERT standard chapter names or do you have a custom syllabus?"

3. **Before any database schema change** — "I'm about to add the payment_events table
   to supabase_schema.sql. Please run this migration in your Supabase dashboard first.
   I'll provide the exact SQL."

4. **If any task fails 2+ times** — "Task [ID] has failed twice. Here is the error:
   [error]. I need your input before retrying."

5. **Before deploying to production** — "All tasks complete. Production checklist:
   [checklist]. Please confirm you want to push to Railway/Vercel."

---

## Quick Start Options

### Option A: Run everything from Phase 1 automatically
```
Read agents/ORCHESTRATOR.md and execute from Phase 1, Task 1A.
Run tasks in the correct order, parallelizing where safe.
Stop at each human checkpoint and wait for my input.
```

### Option B: Run a specific phase only
```
Read agents/ORCHESTRATOR.md.
Skip to Phase 2 (payment integration) and execute all tasks in that phase.
```

### Option C: Run a single task
```
Read agents/ORCHESTRATOR.md.
Execute only Task 1C (QA pass on all 12 topics). Report result.
```

### Option D: Get a status report
```
Read agents/ORCHESTRATOR.md, CLAUDE.md, and agents/PjM_AGENT.md.
Act as the PjM Agent and give me a status report:
- What's done
- What's in progress
- What's blocked
- What's next
Do not write any code.
```

---

## Agent Team Reference Card

| Agent | Trigger | Owns |
|---|---|---|
| PM Agent | "You are the Product Manager Agent" | Vision, backlog, acceptance criteria |
| PjM Agent | "You are the Project Manager Agent" | Sprint board, task assignment |
| Backend Lead | "You are the Backend Lead Agent" | slot_engine, topics, APIs |
| Topic Builder | "You are the Topic Builder Agent" | TOPIC_PROFILES, instruction builders |
| Slot Engine | "You are the Slot Engine Agent" | Pipeline, validators, visuals |
| Payment | "You are the Payment Agent" | subscription.py, Razorpay |
| Frontend Lead | "You are the Frontend Lead Agent" | React components, UX, api.ts |
| Component | "You are the Component Agent" | shadcn/ui, SVG visuals |
| UX Flow | "You are the UX Flow Agent" | Pages, user journeys |
| State & API | "You are the State & API Agent" | api.ts, hooks, auth |
| QA Lead | "You are the QA Lead Agent" | All tests, regression checks |
| Backend Test | "You are the Backend Test Agent" | Backend scripts, validators |
| Frontend Test | "You are the Frontend Test Agent" | Component tests, vitest |
| Integration Test | "You are the Integration Test Agent" | End-to-end pipeline tests |
| Data Lead | "You are the Data Lead Agent" | Supabase, mastery, analytics |
| Schema | "You are the Schema Agent" | Migrations, RLS policies |
| Analytics | "You are the Analytics Agent" | Dashboard, engagement |
| Mastery | "You are the Mastery Agent" | mastery_state, attempt_events |

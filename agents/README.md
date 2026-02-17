# /agents — Agent Team Structure

This folder defines the AI agent team hierarchy for the edTech CBSE Worksheet Generator. Each file is a CLAUDE.md-style instruction set for a specific agent role. Use these files in Claude Code to work within a specific agent's context.

---

## Team Hierarchy

```
PM_AGENT.md          ← Product Manager: vision, backlog, acceptance criteria
└── PjM_AGENT.md     ← Project Manager: sprint board, task assignment, CLAUDE.md updates
    ├── BACKEND_LEAD.md   ← Backend: slot engine, topics, skills, APIs
    ├── FRONTEND_LEAD.md  ← Frontend: React components, UX, API layer
    ├── QA_LEAD.md        ← QA: tests, validators, regression coverage
    └── DATA_LEAD.md      ← Data: Supabase schema, payments, mastery, analytics
```

---

## How to Use in Claude Code

### Activating an agent
In Claude Code, start your message with the agent's trigger phrase. Each lead agent's trigger phrase is defined in its file. For example:

```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md, then fix all silent failures per task S1-BE-01.
```

```
You are the QA Lead Agent.
Read CLAUDE.md and agents/QA_LEAD.md, then create the test_all_topics.py script per task S1-QA-01.
```

```
You are the Data Lead Agent.
Read CLAUDE.md and agents/DATA_LEAD.md, then implement the Razorpay payment integration per task S1-DA-01.
```

### Activating a specialist sub-agent
Each lead agent has 3 specialist agents. Activate them via their trigger phrase defined in the lead file:

```
You are the Topic Builder Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md, then add a new topic profile for "Geometry (basic shapes)" for Class 4.
```

### Activating PM/PjM for planning
```
You are the Product Manager Agent.
Read CLAUDE.md and agents/PM_AGENT.md, then update the backlog with a new P1 feature: Hindi language worksheet support.
```

```
You are the Project Manager Agent.
Read CLAUDE.md, agents/PM_AGENT.md, and agents/PjM_AGENT.md, then plan Sprint 2 tasks based on Sprint 1 completion status.
```

---

## Sprint 1 Task Summary

| Task | Domain | Priority | Status |
|---|---|---|---|
| S1-BE-01: Fix all silent failures | Backend | P0 | 🔴 Active |
| S1-BE-02: Structured syllabus parser | Backend | P0 | 🟡 Next |
| S1-DA-01: Razorpay payment integration | Data | P0 | 🔴 Active |
| S1-DA-02: Analytics dashboard completion | Data | P1 | 🟡 Waiting |
| S1-FE-01: Frontend error visibility | Frontend | P0 | 🟡 Blocked (needs BE-01) |
| S1-QA-01: Class 3 full topic test suite | QA | P0 | 🔴 Active |

---

## Rules That Apply to ALL Agents (from CLAUDE.md)

1. **Deterministic-first** — LLM fills content only. Backend owns structure. All post-gen fixes are deterministic.
2. **No silent fallback** — Every `except` block must log. Never bare `pass`.
3. **Contracts override generation** — Skill contract validate() → repair() → regen takes precedence.
4. **Slot discipline is mandatory** — Slot counts must exactly match plan.
5. **Visual coverage 100%** — Every PICTORIAL_MODEL question needs valid visual_spec.
6. **Never relax carry/borrow enforcement** — Non-negotiable.
7. **Update CLAUDE.md on every commit** — Replace auto-generated file paths with human-readable summary.
8. **shadcn/ui install path** — Always move from `frontend/@/` to `frontend/src/`.
9. **grep after replace_all** — Stale references cause runtime errors.
10. **Regex at module level** — Define before functions that use them.

---

## Adding New Agents

When expanding to new domains or grades, add a new agent file following this template:
```
# [ROLE]_AGENT.md — [Role Name] Agent

## Role
[1-paragraph description of what this agent owns and does NOT own]

## Domain Ownership
[File tree of owned files]

## Current Task Queue
[Tasks from PjM_AGENT.md sprint board]

## Current Blockers
[Any blockers with resolution path]

## Operating Rules
[Domain-specific rules that EXTEND global CLAUDE.md rules]

## Specialist Agents Under [Role]
[Sub-agents with trigger phrases]

## Common Commands
[bash commands relevant to this domain]

## Update Log
[Dated entries]
```

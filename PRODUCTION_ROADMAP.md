# PRODUCTION_ROADMAP.md — How to Use Claude Code + Agents to Ship This Project

## How Claude Code + Agents Works (Quick Primer)

Claude Code runs in your terminal inside your repo. You give it a task in plain English,
it reads your files, writes code, runs commands, and commits. The agent files we created
tell Claude Code WHAT ROLE to play and WHAT RULES to follow for that domain.

**The pattern is always:**
1. Open your terminal in the repo root
2. Type: `claude` to start Claude Code
3. Paste the trigger phrase for the agent you want
4. Describe the task
5. Claude Code reads the agent file, does the work, shows you a diff
6. You approve or reject each change

---

## PHASE 1 — Fix the Foundation (Do This First, ~2-3 days)

These are blockers. Nothing else matters until these are done.

---

### Task 1A: Fix All Silent Failures
**Why first**: You cannot trust production logs or debug issues until this is done.

**Paste this into Claude Code:**
```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

Fix all silent failures per task S1-BE-01:
1. backend/app/api/audit.py — replace bare except with logger.error
2. backend/app/services/telemetry.py — replace except pass with logging
3. backend/app/services/mastery_store.py — log warning on Supabase fallback
4. backend/app/api/worksheets_v1.py — fix two except pass blocks
5. backend/app/services/slot_engine.py — fix all silent skips

After each file: run grep -rn "except Exception: pass" backend/app/ to confirm zero results.
Commit with message: "[S1-BE-01] Fix all silent failures - add logging to all except blocks"
```

**How to verify it worked:**
```bash
grep -rn "except Exception: pass\|except Exception: return" backend/app/
# Should return zero results
```

---

### Task 1B: Fix Frontend Silent Failures
**Why**: Users seeing blank screens lose trust immediately.

**Paste this into Claude Code:**
```
You are the Frontend Lead Agent.
Read CLAUDE.md and agents/FRONTEND_LEAD.md before starting.

Fix frontend silent failures per task S1-FE-01:
1. frontend/src/pages/subscription.tsx — add toast on fetch failure, keep free tier fallback
2. frontend/src/hooks/engagement.tsx — add console.warn on failure, don't return null silently
3. frontend/src/pages/profile.tsx — show error state instead of clearing to null
4. frontend/src/lib/api.ts — add console.warn when falling back from v1 to legacy API

Run: npm run build && npm run lint — must pass with zero errors.
Commit with message: "[S1-FE-01] Add error visibility to subscription, profile, engagement, api"
```

---

### Task 1C: Run Full QA Pass on All 12 Topics
**Why**: Before adding more topics or grades, verify the 12 you have actually work.

**Paste this into Claude Code:**
```
You are the QA Lead Agent.
Read CLAUDE.md and agents/QA_LEAD.md before starting.

Complete task S1-QA-01:
Create backend/scripts/test_all_topics.py that tests all 12 Class 3 Maths topics
across question counts 5, 10, 15, 20 (48 combinations total).

Each combination must validate:
- Exact slot counts match plan
- ED >= 1, T >= 1
- No duplicate question text
- No visual phrases (draw, shade, colour, circle)
- No empty answers
- Question text >= 10 chars
- Format valid for slot_type

Script must exit with code 0 on all pass, non-zero on any fail.
Run the script after creating it. All 48 must pass.
Commit with message: "[S1-QA-01] Add full 48-combination topic test matrix, all passing"
```

---

## PHASE 2 — Add Revenue (Week 2)

### Task 2A: Razorpay Payment Integration
**Why**: No payment = no business. This is the most important feature.

**Before running this task**, make sure you have:
- Razorpay account created at razorpay.com (free to create)
- Your `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` from Razorpay dashboard
- `RAZORPAY_WEBHOOK_SECRET` from Razorpay webhook settings

**Paste this into Claude Code:**
```
You are the Data Lead Agent.
Read CLAUDE.md and agents/DATA_LEAD.md before starting.

Complete task S1-DA-01 — Razorpay payment integration:

Step 1: Add payment_events table to backend/supabase_schema.sql
  - id UUID, user_id, razorpay_order_id, razorpay_payment_id, 
    razorpay_signature, status, amount_paise, plan_tier, timestamps
  - Enable RLS: users can read own rows, service role writes

Step 2: In backend/app/api/subscription.py:
  - Implement POST /api/subscription/create-order (creates Razorpay order, returns order_id)
  - Implement POST /api/subscription/webhook (verify signature, update tier on payment.captured)
  - Implement the existing upgrade_to_paid() properly
  - All env vars: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

Step 3: Add razorpay to backend/requirements.txt

All except blocks must log with context (no bare pass).
Commit with message: "[S1-DA-01] Razorpay payment integration - order creation + webhook"
```

---

### Task 2B: Razorpay Frontend Checkout
**After** Task 2A is done:

**Paste this into Claude Code:**
```
You are the Frontend Lead Agent.
Read CLAUDE.md and agents/FRONTEND_LEAD.md before starting.

Add Razorpay checkout to the subscription page:
1. On "Upgrade to Paid" button click: call POST /api/subscription/create-order
2. Load Razorpay checkout.js script and open payment modal with the order_id
3. On payment success: show success toast + refresh subscription status
4. On payment failure: show error toast with retry option
5. Show loading spinner during order creation

Price to display: ₹299/month

Use Razorpay's standard checkout.js (CDN: https://checkout.razorpay.com/v1/checkout.js)
Run: npm run build && npm run lint — must pass.
Commit with message: "[S1-FE-02] Add Razorpay checkout UI to subscription page"
```

---

## PHASE 3 — Content Expansion (Week 3)

### Task 3A: Fix Syllabus Parser
**Why**: Teachers can't select chapters without this. Unlocks the teacher segment.

**Paste this into Claude Code:**
```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

Complete task S1-BE-02 — Fix syllabus.py:

1. Implement get_syllabus(grade, subject) with hardcoded CBSE chapter structure for:
   - Class 1, 2, 3, 4, 5 — Mathematics
   - Class 1, 2, 3, 4, 5 — English
   Use actual NCERT chapter names.

2. Output schema:
   {grade, subject, chapters: [{id, title, topics: [str]}]}

3. Implement parse_syllabus(raw_text) with regex-based parsing
   (no LLM — deterministic only)

4. Return 422 with clear message for unsupported grade/subject

5. Write unit test in backend/scripts/test_syllabus.py

Commit with message: "[S1-BE-02] Implement structured CBSE syllabus parser for Class 1-5"
```

---

### Task 3B: Expand to Class 2 Maths Topics
**Paste this into Claude Code:**
```
You are the Topic Builder Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

Add Class 2 Maths topic profiles to backend/app/services/slot_engine.py.

Class 2 NCERT Maths topics to add:
1. Numbers up to 1000 (hundreds, tens, ones)
2. Addition (2-digit with carry)
3. Subtraction (2-digit with borrow)
4. Multiplication (tables 2-5)
5. Division (sharing equally)
6. Shapes and space (2D shapes)
7. Measurement (length, weight)
8. Time (hour, half-hour)
9. Money (coins and notes)
10. Data handling (pictographs)

For each topic:
- Add to TOPIC_PROFILES with allowed_skill_tags, allowed_slot_types, disallowed_keywords
- Add alias to _TOPIC_ALIASES
- Add constraint to _TOPIC_CONSTRAINTS if non-arithmetic
- Add instruction builder block to _build_slot_instruction()

After adding: run python scripts/verify_topics.py — must pass.
Run python scripts/test_all_topics.py with Class 2 topics added to ALL_TOPICS.
Commit with message: "[P1-01] Add Class 2 Maths topic profiles (10 topics)"
```

---

### Task 3C: Expand to Class 4 Maths Topics
Same pattern as 3B but for Class 4. Paste into Claude Code:
```
You are the Topic Builder Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

Add Class 4 Maths topic profiles following the same pattern as Class 3.

Class 4 NCERT Maths topics:
1. Large numbers (up to 1,00,000)
2. Addition and subtraction (5-digit)
3. Multiplication (3-digit × 2-digit)
4. Division (long division, 3-digit ÷ 1-digit)
5. Fractions (equivalent, comparison)
6. Decimals (tenths, hundredths)
7. Geometry (angles, lines)
8. Perimeter and area
9. Time (minutes, 24-hour clock)
10. Money (bills, profit/loss)

Same checklist as Class 2 expansion.
Commit with message: "[P1-02] Add Class 4 Maths topic profiles (10 topics)"
```

---

## PHASE 4 — Production Hardening (Week 4)

### Task 4A: Clean Up Dead Code
**Paste this into Claude Code:**
```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

In backend/app/api/worksheets.py, the following functions are dead code
(not called from any active pipeline):
- build_system_prompt()
- _fixup_question_types()
- _fix_computational_answers()
- _fix_inconsistent_visuals()

Mark each with a comment: # DEAD: not called from main pipeline [2026-02-17]
Do NOT delete them yet — just mark them clearly.

Run: grep -rn "build_system_prompt\|_fixup_question_types\|_fix_computational_answers\|_fix_inconsistent_visuals" backend/app/
Confirm they are only defined in worksheets.py and called nowhere else.
Commit with message: "[cleanup] Mark 4 dead functions in worksheets.py with DEAD comments"
```

---

### Task 4B: Add Rate Limiting and Subscription Enforcement
**Paste this into Claude Code:**
```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

Add subscription enforcement to worksheet generation:

1. In backend/app/api/worksheets.py and worksheets_v1.py:
   - Before generating: check user_subscriptions.worksheets_generated_this_month
   - Free tier limit: 10 worksheets/month
   - If limit reached: return 402 with message "Monthly limit reached. Upgrade to paid plan."
   - If paid: no limit check needed
   - After successful generation: increment worksheets_generated_this_month

2. Check if month_reset_at has passed — if yes, reset counter to 0 before checking

3. Every check must handle DB errors gracefully (log + allow generation if DB unreachable,
   don't block users due to our own DB issues)

Commit with message: "[subscription] Add monthly worksheet limit enforcement for free tier"
```

---

### Task 4C: Worksheet History
**Paste this into Claude Code:**
```
You are the Frontend Lead Agent.
Read CLAUDE.md and agents/FRONTEND_LEAD.md before starting.

Add a worksheet history page:

1. New page: frontend/src/pages/history.tsx
   - Lists all worksheets for the current user (from /api/v1/worksheets/ GET endpoint)
   - Shows: title, topic, date generated, question count, grade
   - Each row has: "Download PDF" and "Regenerate" buttons
   - Filter by: child, topic, date range
   - Paginated (20 per page)

2. Add "History" link to main navigation

3. Handle empty state: "No worksheets yet. Generate your first worksheet!"

4. Handle loading and error states (no silent failures)

Run: npm run build && npm run lint — must pass.
Commit with message: "[P1-04] Add worksheet history page with PDF download and regenerate"
```

---

## PHASE 5 — Teacher Features (Week 5)

### Task 5A: Bulk Worksheet Generation
**Paste this into Claude Code:**
```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md before starting.

Add bulk worksheet generation endpoint:

POST /api/v1/worksheets/bulk
Request: {
  topics: [str],          // list of topic names
  num_questions: int,      // per worksheet
  grade: str,
  count_per_topic: int     // how many worksheets per topic
}
Response: {
  worksheets: [worksheet],
  failed: [{topic, error}],
  total_generated: int
}

Limits:
- Max 5 topics per bulk request
- Max 3 worksheets per topic
- Total max: 15 worksheets per bulk call
- Paid tier only (return 402 for free tier)

Each generation uses existing run_slot_pipeline() — no new pipeline logic.
Parallel generation using asyncio.gather() for speed.

Commit with message: "[P1-05] Add bulk worksheet generation endpoint for teachers"
```

---

## PHASE 6 — Quality of Life (Ongoing)

### Task 6A: Answer Key Toggle
```
You are the Frontend Lead Agent.
Read CLAUDE.md and agents/FRONTEND_LEAD.md before starting.

Add answer key toggle to worksheet view and PDF export:
1. Toggle button: "Show Answers" / "Hide Answers" 
2. When hidden: answer fields show blank lines (for students)
3. When shown: answers visible (for teachers)
4. PDF export respects the toggle state
5. Default: hidden (student mode)

Commit with message: "[P3-01] Add answer key show/hide toggle to worksheet view"
```

---

## Daily Workflow Once You're Comfortable

Once you get the hang of it, your daily Claude Code workflow will look like this:

```bash
# 1. Start Claude Code in your repo
cd /path/to/edTech
claude

# 2. Check what's next
"Read agents/PjM_AGENT.md and tell me the next unfinished task in Sprint 1"

# 3. Run that task
[paste the trigger phrase from this roadmap]

# 4. Review the diff Claude Code shows you
[approve or reject each change]

# 5. Commit
[Claude Code handles the commit with the message you specified]

# 6. Deploy
git push  # Railway auto-deploys backend, Vercel auto-deploys frontend
```

---

## Environment Variables Checklist (Must Set Before Production)

### Railway (Backend)
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
OPENAI_API_KEY=
RAZORPAY_KEY_ID=           ← Add in Phase 2
RAZORPAY_KEY_SECRET=       ← Add in Phase 2
RAZORPAY_WEBHOOK_SECRET=   ← Add in Phase 2
ENABLE_TELEMETRY_DB=1      ← Enable in Phase 4
ENABLE_ATTEMPT_AUDIT_DB=1  ← Enable in Phase 4
PRACTICECRAFT_MASTERY_STORE=supabase  ← Enable in Phase 4
DEBUG=false
```

### Vercel (Frontend)
```
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_URL=https://your-railway-app.up.railway.app
```

---

## Production Readiness Checklist

### Foundation
- [ ] Zero bare except blocks (Task 1A)
- [ ] Zero frontend silent failures (Task 1B)
- [ ] All 48 topic combinations pass QA (Task 1C)

### Revenue
- [ ] Razorpay order creation working (Task 2A)
- [ ] Razorpay webhook verified and tested (Task 2A)
- [ ] Frontend checkout flow working (Task 2B)
- [ ] Free tier limit enforced (Task 4B)

### Content
- [ ] Syllabus parser returns structured data (Task 3A)
- [ ] Class 2 topics live (Task 3B)
- [ ] Class 4 topics live (Task 3C)

### Polish
- [ ] Dead code marked (Task 4A)
- [ ] Worksheet history page (Task 4C)
- [ ] Answer key toggle (Task 6A)

### Teacher tier
- [ ] Bulk generation endpoint (Task 5A)

**When all boxes are checked = production ready.**

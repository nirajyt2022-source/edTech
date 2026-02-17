# DATA_LEAD.md — Data & Analytics Lead Agent

## Role
You are the **Data & Analytics Lead Agent** for the edTech CBSE Worksheet Generator. You own the Supabase database schema, RLS policies, mastery tracking, engagement analytics, subscription/payment logic, and all database migrations. You coordinate the three data specialist agents (Schema, Analytics, Mastery).

You always read `CLAUDE.md` AND `PjM_AGENT.md` at the start of every session before touching any schema or data code.

---

## Domain Ownership
```
backend/
├── supabase_schema.sql         ← Source of truth for all tables + RLS policies
├── app/api/
│   ├── subscription.py         ← Tier management + Razorpay (INCOMPLETE — P0)
│   ├── analytics.py            ← Analytics endpoints
│   ├── engagement.py           ← Engagement tracking
│   └── dashboard.py            ← Dashboard data aggregation
└── app/services/
    ├── mastery_store.py        ← mastery_state reads/writes (memory or Supabase)
    ├── telemetry.py            ← telemetry_events writes
    └── audit.py                ← attempt_events writes
```

---

## Current Database Schema (Full Reference)

### Core Tables
| Table | PK | Key Columns | Notes |
|---|---|---|---|
| worksheets | UUID | user_id, child_id, class_id, questions (JSONB) | Main content table |
| children | UUID | user_id, name, grade, board | Child profiles |
| user_profiles | user_id | role, active_role, subjects[], grades[] | UNIQUE on user_id |
| teacher_classes | UUID | user_id, grade, subject, syllabus_source | syllabus_source: cbse/custom |

### Subscription & Payment
| Table | PK | Key Columns | Notes |
|---|---|---|---|
| user_subscriptions | UUID | user_id (UNIQUE), tier, worksheets_generated_this_month, month_reset_at | Auto-created via trigger |

**Missing**: `payment_events` table (to be created in S1-DA-01)

### Learning & Analytics
| Table | PK | Key Columns | Notes |
|---|---|---|---|
| mastery_state | (student_id, skill_tag) | streak, mastery_level, last_error_type | Gated by feature flag |
| attempt_events | — | student_id, worksheet_id, grade_result, mastery_before/after | Gated: ENABLE_ATTEMPT_AUDIT_DB=1 |
| telemetry_events | — | event, route, version, latency_ms, ok | Gated: ENABLE_TELEMETRY_DB=1 |
| child_engagement | UUID | child_id (UNIQUE), total_stars, current_streak, longest_streak | |
| topic_preferences | UUID | child_id, subject, selected_topics (JSONB) | UNIQUE(child_id, subject) |
| cbse_syllabus | UUID | grade, subject, chapters (JSONB) | UNIQUE(grade, subject) |

---

## Current Task Queue (from PjM_AGENT.md)

### 🔴 ACTIVE: S1-DA-01 — Razorpay Payment Integration

**Files to edit**: `backend/app/api/subscription.py`, `backend/supabase_schema.sql`

#### Step 1: Add payment_events table to schema
```sql
-- Add to supabase_schema.sql
CREATE TABLE IF NOT EXISTS payment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    razorpay_order_id TEXT NOT NULL,
    razorpay_payment_id TEXT,
    razorpay_signature TEXT,
    status TEXT NOT NULL CHECK (status IN ('created', 'captured', 'failed', 'refunded')),
    amount_paise INTEGER NOT NULL,  -- Amount in paise (INR × 100)
    plan_tier TEXT NOT NULL DEFAULT 'paid',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RLS: Users can only see their own payment events
ALTER TABLE payment_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own payment events"
    ON payment_events FOR SELECT
    USING (auth.uid() = user_id);
-- Service role only for inserts (webhook writes)
```

#### Step 2: Implement Razorpay order creation
```python
# In subscription.py
import razorpay  # pip install razorpay

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
MONTHLY_PRICE_PAISE = 29900  # ₹299/month in paise

@router.post("/create-order")
async def create_payment_order(user=Depends(get_current_user)):
    try:
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        order = client.order.create({
            "amount": MONTHLY_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"order_{user.id[:8]}_{int(time.time())}",
        })
        # Store in payment_events with status='created'
        return {"order_id": order['id'], "amount": MONTHLY_PRICE_PAISE, "currency": "INR"}
    except Exception as e:
        logger.error(f"[subscription.create_order] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not create payment order")
```

#### Step 3: Implement webhook verification
```python
@router.post("/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    try:
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        client.utility.verify_webhook_signature(
            body.decode(), signature, RAZORPAY_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.error(f"[subscription.webhook] Signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    if event == "payment.captured":
        payment = payload["payload"]["payment"]["entity"]
        # Update user_subscriptions.tier = 'paid'
        # Update payment_events.status = 'captured'
        # Log success
    elif event == "payment.failed":
        # Update payment_events.status = 'failed'
        # Log failure with reason
        pass

    return {"status": "ok"}
```

**New env vars to document**:
- `RAZORPAY_KEY_ID` — Razorpay API key
- `RAZORPAY_KEY_SECRET` — Razorpay API secret
- `RAZORPAY_WEBHOOK_SECRET` — Razorpay webhook signature secret

**Definition of done**: Order creation returns valid Razorpay order. Webhook verifies signature. Successful payment upgrades tier. Failed payment logs and returns 402.

---

### 🟡 NEXT: S1-DA-02 — Analytics Dashboard Completion

**File to review**: `backend/app/api/analytics.py`, `backend/app/api/dashboard.py`

**Target**: Ensure dashboard returns:
- Total worksheets generated (per user, per child, per month)
- Topic distribution (which topics used most)
- Mastery progression per child per skill
- Streak data from child_engagement

---

## Current Blockers
_S1-DA-02 depends on S1-DA-01 for payment status fields in dashboard. Update when S1-DA-01 completes._

---

## Data Operating Rules (extends global CLAUDE.md rules)

### Schema rules
- ALL new tables MUST have: UUID primary key via `gen_random_uuid()`, `created_at`, `updated_at` timestamps, RLS enabled
- NEVER modify existing column types — add new columns or new tables
- All migrations must be additive (no DROP COLUMN, no ALTER TYPE that breaks existing data)
- Schema changes go in `supabase_schema.sql` with `IF NOT EXISTS` guards
- After any schema change: verify RLS policies cover all CRUD operations

### RLS policy rules
- Default: deny all, then selectively allow
- Users always: SELECT own rows (`auth.uid() = user_id`)
- Service role: used for webhook writes and server-side operations
- NEVER expose service role key to frontend
- Test RLS with a non-owner user before marking done

### Mastery store rules
- `mastery_store.py` default is `memory` — Supabase store requires `PRACTICECRAFT_MASTERY_STORE=supabase`
- Supabase init failure MUST log warning (not silently fall back) — fixed in S1-BE-01
- `mastery_level` values: `unknown` → `learning` → `improving` → `mastered` — never deviate from this enum
- Streak resets to 0 on incorrect answer, not decremented

### Telemetry & audit rules
- Both gated by feature flags — don't enable by default in production
- `telemetry_events` writes: fire-and-forget (don't block worksheet generation)
- `attempt_events` writes: fire-and-forget (don't block grading)
- After S1-BE-01: both must log on write failure instead of passing silently

### Payment rules
- ALWAYS verify Razorpay webhook signature before processing
- NEVER trust client-side payment confirmation — only webhook
- Store full Razorpay payload in payment_events for audit trail
- Amount in paise (integer), never float — avoids rounding errors

---

## Specialist Agents Under Data Lead

### Schema Agent (activate when: new tables, migrations, RLS changes)
**Focus**: `supabase_schema.sql`, Supabase migrations, RLS policies
**Trigger phrase**: "You are the Schema Agent. Read DATA_LEAD.md and CLAUDE.md, then [task]."

### Analytics Agent (activate when: dashboard endpoints, engagement tracking, reporting)
**Focus**: `analytics.py`, `dashboard.py`, `engagement.py`
**Trigger phrase**: "You are the Analytics Agent. Read DATA_LEAD.md and CLAUDE.md, then [task]."

### Mastery Agent (activate when: mastery_state logic, attempt_events, skill progression)
**Focus**: `mastery_store.py`, `audit.py`, mastery_state table, `worksheets_v1.py` mastery endpoints
**Trigger phrase**: "You are the Mastery Agent. Read DATA_LEAD.md and CLAUDE.md, then [task]."

---

## Common Data Commands
```bash
# Check schema file
cat backend/supabase_schema.sql

# Verify env vars are set
echo $SUPABASE_URL && echo $SUPABASE_SERVICE_KEY && echo $RAZORPAY_KEY_ID

# Test mastery store (in-memory mode, no DB needed)
cd backend && python -c "from app.services.mastery_store import get_mastery_store; print(get_mastery_store())"

# Check for silent failures in data layer
grep -rn "except Exception: pass\|except Exception: return" backend/app/services/
```

---

## Update Log (Data)
- **2026-02-17**: Agent file created. Razorpay integration design documented. Schema gap (payment_events) identified. Sprint 1 tasks loaded.

-- 010_email_sequence.sql
-- Tracks per-user welcome email sequence state.
-- Run against Supabase with service_role key.
--
-- Post-deploy steps:
--   1. Set EMAIL_WEBHOOK_SECRET env var on Railway
--   2. Configure Supabase Auth webhook → POST /api/emails/webhook/signup
--   3. Set up hourly cron → POST /api/emails/process-sequence (with X-Webhook-Secret header)

CREATE TABLE IF NOT EXISTS email_sequence (
    user_id        UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    sequence_name  TEXT NOT NULL DEFAULT 'welcome',
    last_email_sent INT NOT NULL DEFAULT 0,        -- 0 = none, 1-5 = last sent
    next_send_at   TIMESTAMPTZ,                     -- when next email is due
    completed      BOOLEAN NOT NULL DEFAULT false,
    user_email     TEXT NOT NULL,                    -- cached from signup
    parent_name    TEXT NOT NULL DEFAULT '',
    child_name     TEXT NOT NULL DEFAULT '',
    child_grade    TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Efficient polling: only incomplete rows due for sending
CREATE INDEX IF NOT EXISTS idx_email_sequence_pending
    ON email_sequence (next_send_at)
    WHERE completed = false;

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_email_sequence_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_email_sequence_updated_at ON email_sequence;
CREATE TRIGGER trg_email_sequence_updated_at
    BEFORE UPDATE ON email_sequence
    FOR EACH ROW
    EXECUTE FUNCTION update_email_sequence_updated_at();

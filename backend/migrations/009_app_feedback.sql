-- 009_app_feedback.sql — General app feedback from parents and teachers
-- Run: psql $DATABASE_URL -f migrations/009_app_feedback.sql

CREATE TABLE IF NOT EXISTS app_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    categories TEXT[] DEFAULT '{}',
    comment TEXT,
    page TEXT,
    role TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_app_feedback_user
    ON app_feedback(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_app_feedback_rating
    ON app_feedback(rating, created_at DESC);

ALTER TABLE app_feedback ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Users can insert own feedback"
        ON app_feedback FOR INSERT WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Users can read own feedback"
        ON app_feedback FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

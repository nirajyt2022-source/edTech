-- Worksheet difficulty feedback from parents (post-grading)
CREATE TABLE IF NOT EXISTS worksheet_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    worksheet_id TEXT NOT NULL,
    child_id UUID REFERENCES children(id) ON DELETE SET NULL,
    user_id UUID NOT NULL,
    difficulty_rating TEXT NOT NULL
        CHECK (difficulty_rating IN ('too_easy', 'just_right', 'too_hard')),
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_worksheet_feedback_child
    ON worksheet_feedback(child_id, created_at DESC);

ALTER TABLE worksheet_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can insert own feedback"
    ON worksheet_feedback FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can read own feedback"
    ON worksheet_feedback FOR SELECT USING (auth.uid() = user_id);

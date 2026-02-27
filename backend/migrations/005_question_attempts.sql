-- D-03b: Question-level attempt tracking for diagnostic engine.
-- Stores per-question grading results with misconception classification.

CREATE TABLE IF NOT EXISTS question_attempts (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    child_id        UUID NOT NULL REFERENCES children(id),
    worksheet_id    UUID,
    session_id      UUID,
    question_index  SMALLINT NOT NULL,
    skill_tag       TEXT NOT NULL,
    question_format TEXT,
    difficulty      TEXT,
    role            TEXT,
    correct_answer  TEXT NOT NULL,
    student_answer  TEXT,
    is_correct      BOOLEAN NOT NULL DEFAULT FALSE,
    confidence      REAL,
    needs_review    BOOLEAN DEFAULT FALSE,
    misconception_id TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qa_child_skill
    ON question_attempts(child_id, skill_tag);
CREATE INDEX IF NOT EXISTS idx_qa_child_misconception
    ON question_attempts(child_id, misconception_id);
CREATE INDEX IF NOT EXISTS idx_qa_child_created
    ON question_attempts(child_id, created_at DESC);

-- RLS: parents can see their own children's attempts
ALTER TABLE question_attempts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_see_own_child_attempts" ON question_attempts
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM children
            WHERE children.id = question_attempts.child_id
              AND children.user_id = (select auth.uid())
        )
    );

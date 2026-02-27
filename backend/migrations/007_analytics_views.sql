-- D-04c: Analytics views referenced by backend/app/api/analytics.py.
-- These query question_attempts to power the analytics dashboard.

-- View 1: Per-skill accuracy breakdown
CREATE OR REPLACE VIEW v_skill_accuracy AS
SELECT
    child_id AS student_id,
    skill_tag,
    COUNT(*) AS total_attempts,
    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct_count,
    ROUND(
        SUM(CASE WHEN is_correct THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0),
        3
    ) AS accuracy,
    MAX(created_at) AS last_attempted_at
FROM question_attempts
GROUP BY child_id, skill_tag;

-- View 2: Error distribution by misconception type
CREATE OR REPLACE VIEW v_error_distribution AS
SELECT
    child_id AS student_id,
    skill_tag,
    misconception_id,
    COUNT(*) AS error_count,
    MIN(created_at) AS first_seen,
    MAX(created_at) AS last_seen
FROM question_attempts
WHERE is_correct = FALSE
  AND misconception_id IS NOT NULL
GROUP BY child_id, skill_tag, misconception_id;

-- View 3: Student skill progress over time (weekly buckets)
CREATE OR REPLACE VIEW v_student_skill_progress AS
SELECT
    child_id AS student_id,
    skill_tag,
    DATE_TRUNC('week', created_at) AS week_start,
    COUNT(*) AS attempts,
    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct,
    ROUND(
        SUM(CASE WHEN is_correct THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0),
        3
    ) AS weekly_accuracy
FROM question_attempts
GROUP BY child_id, skill_tag, DATE_TRUNC('week', created_at);

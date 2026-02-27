-- D-04b: Enrich topic_mastery with diagnostic columns.

ALTER TABLE topic_mastery
    ADD COLUMN IF NOT EXISTS misconception_pattern JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS systematic_errors TEXT[] DEFAULT '{}';

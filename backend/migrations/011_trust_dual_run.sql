-- Shadow dual-run parity logs for V2/V3 migration decisions.

CREATE TABLE IF NOT EXISTS trust_dual_run_results (
    id                      BIGSERIAL PRIMARY KEY,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id              TEXT NOT NULL,
    grade                   TEXT NOT NULL,
    subject                 TEXT NOT NULL,
    topic                   TEXT NOT NULL,
    primary_engine          TEXT NOT NULL,
    shadow_engine           TEXT NOT NULL,
    primary_verdict         TEXT NOT NULL,
    shadow_verdict          TEXT NOT NULL,
    verdict_match           BOOLEAN NOT NULL DEFAULT FALSE,
    primary_quality_score   DOUBLE PRECISION NULL,
    shadow_quality_score    DOUBLE PRECISION NULL,
    primary_latency_ms      INTEGER NULL,
    shadow_latency_ms       INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_trust_dual_run_created ON trust_dual_run_results (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trust_dual_run_match ON trust_dual_run_results (verdict_match);
CREATE INDEX IF NOT EXISTS idx_trust_dual_run_scope ON trust_dual_run_results (grade, subject, topic);

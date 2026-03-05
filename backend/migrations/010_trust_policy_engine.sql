-- Trust-first robustification: failure memory + policy registry.

CREATE TABLE IF NOT EXISTS trust_failures (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          TIMESTAMPTZ DEFAULT now(),
    request_id          TEXT NOT NULL,
    user_id             UUID,
    grade               TEXT NOT NULL,
    subject             TEXT NOT NULL,
    topic               TEXT NOT NULL,
    rule_id             TEXT NOT NULL,
    severity            TEXT NOT NULL CHECK (severity IN ('P0', 'P1', 'P2')),
    question_id         TEXT,
    fingerprint         TEXT NOT NULL,
    payload_json        JSONB DEFAULT '{}'::jsonb,
    prompt_hash         TEXT,
    profile_key         TEXT,
    model_version       TEXT,
    was_served          BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_trust_failures_created ON trust_failures (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trust_failures_fingerprint ON trust_failures (fingerprint);
CREATE INDEX IF NOT EXISTS idx_trust_failures_scope ON trust_failures (grade, subject, topic);
CREATE INDEX IF NOT EXISTS idx_trust_failures_rule ON trust_failures (rule_id, severity);


CREATE TABLE IF NOT EXISTS trust_policies (
    id                          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    policy_id                   TEXT UNIQUE NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT now(),
    updated_at                  TIMESTAMPTZ DEFAULT now(),
    scope_type                  TEXT NOT NULL CHECK (scope_type IN ('topic', 'grade_subject', 'global')),
    scope_key                   TEXT NOT NULL,
    action_type                 TEXT NOT NULL,
    action_payload_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                      TEXT NOT NULL CHECK (status IN ('active', 'canary', 'rolled_back')),
    created_by                  TEXT NOT NULL CHECK (created_by IN ('auto', 'manual')),
    source_failure_fingerprint  TEXT
);

CREATE INDEX IF NOT EXISTS idx_trust_policies_scope ON trust_policies (scope_type, scope_key, status);
CREATE INDEX IF NOT EXISTS idx_trust_policies_status ON trust_policies (status);


CREATE TABLE IF NOT EXISTS trust_policy_versions (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          TIMESTAMPTZ DEFAULT now(),
    policy_id           TEXT NOT NULL,
    version             INTEGER NOT NULL,
    status              TEXT NOT NULL,
    action_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes               TEXT,
    UNIQUE(policy_id, version)
);

CREATE INDEX IF NOT EXISTS idx_trust_policy_versions_policy ON trust_policy_versions (policy_id, version DESC);


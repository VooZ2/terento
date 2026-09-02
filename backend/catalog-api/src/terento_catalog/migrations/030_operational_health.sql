-- Retain bounded CI/deployment observations and the scheduler's own heartbeat.
-- /admin consumes this state but never executes repository tests.

CREATE TABLE operational_observation (
    id BIGSERIAL PRIMARY KEY,
    observation_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('WEEKLY_TEST', 'RELEASE_GATE', 'DEPLOYMENT')),
    component TEXT NOT NULL CHECK (component IN ('test-matrix', 'release', 'site', 'catalog-api')),
    status TEXT NOT NULL CHECK (status IN ('HEALTHY', 'WARNING', 'FAILED', 'UNKNOWN')),
    observed_at TIMESTAMPTZ NOT NULL,
    source_run_id TEXT NOT NULL,
    source_run_url TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    release_version TEXT,
    build_number TEXT,
    summary TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX operational_observation_latest_idx
    ON operational_observation (component, observed_at DESC);

CREATE TABLE scheduler_heartbeat (
    job_name TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('HEALTHY', 'WARNING', 'FAILED', 'UNKNOWN', 'RUNNING', 'WAITING')),
    next_run_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_summary TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


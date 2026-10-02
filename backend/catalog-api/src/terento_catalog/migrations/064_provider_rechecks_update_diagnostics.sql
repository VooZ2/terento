-- Additive operational evidence; never participates in installation statistics.
ALTER TABLE map_artifact ADD COLUMN IF NOT EXISTS last_check JSONB;
CREATE TABLE IF NOT EXISTS provider_recheck (
 id BIGSERIAL PRIMARY KEY,
 provider_id TEXT NOT NULL REFERENCES map_provider(id),
 package_id TEXT,
 admin_user_id BIGINT,
 state TEXT NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','INTERRUPTED')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 finished_at TIMESTAMPTZ,
 retry_not_before TIMESTAMPTZ,
 results JSONB NOT NULL DEFAULT '[]'
);
CREATE UNIQUE INDEX IF NOT EXISTS provider_recheck_active ON provider_recheck(provider_id) WHERE state IN ('QUEUED','RUNNING');
CREATE TABLE IF NOT EXISTS provider_artifact_check (
 id BIGSERIAL PRIMARY KEY, artifact_id TEXT NOT NULL,
 checked_at TIMESTAMPTZ NOT NULL DEFAULT now(), result JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS provider_artifact_check_latest ON provider_artifact_check(artifact_id, checked_at DESC);
CREATE TABLE IF NOT EXISTS map_update_diagnostic (
 event_id UUID PRIMARY KEY, operation_id UUID NOT NULL, occurred_at TIMESTAMPTZ NOT NULL,
 provider TEXT NOT NULL, region TEXT NOT NULL, outcome TEXT NOT NULL,
 is_local_test BOOLEAN NOT NULL DEFAULT FALSE,
 payload JSONB NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS map_update_diagnostic_operation ON map_update_diagnostic(operation_id);

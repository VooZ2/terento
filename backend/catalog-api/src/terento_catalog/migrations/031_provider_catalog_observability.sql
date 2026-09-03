-- Retain provider-specific catalog attempts and release-change evidence.
-- The catalog remains metadata-only; no provider map binary is stored here.

ALTER TABLE catalog_collection_run
    ADD COLUMN IF NOT EXISTS latest_release TEXT,
    ADD COLUMN IF NOT EXISTS catalog_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS release_change_detected BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS catalog_collection_run_provider_success_idx
    ON catalog_collection_run (provider_id, finished_at DESC, id DESC)
    WHERE status = 'SUCCEEDED';

CREATE INDEX IF NOT EXISTS catalog_collection_run_release_change_idx
    ON catalog_collection_run (finished_at DESC, provider_id)
    WHERE release_change_detected = TRUE;

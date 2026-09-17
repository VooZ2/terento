-- Preserve enough population identity to detect discontinuities in the
-- cumulative GitHub asset counters. Existing rows remain readable but are
-- treated as an unknown baseline until a fully identified observation exists.
ALTER TABLE github_download_snapshot
    ADD COLUMN IF NOT EXISTS asset_count INTEGER,
    ADD COLUMN IF NOT EXISTS population_fingerprint TEXT;

ALTER TABLE github_download_snapshot
    ADD CONSTRAINT github_download_snapshot_asset_count_check
    CHECK (asset_count IS NULL OR asset_count >= 0);

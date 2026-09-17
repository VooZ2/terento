-- Preserve enough population identity to detect discontinuities in the
-- cumulative GitHub asset counters. Existing rows remain readable; NULL means
-- population comparability is unconfirmed, not that the counter observation
-- or a nonnegative historical delta is invalid.
ALTER TABLE github_download_snapshot
    ADD COLUMN IF NOT EXISTS asset_count INTEGER,
    ADD COLUMN IF NOT EXISTS population_fingerprint TEXT;

ALTER TABLE github_download_snapshot
    ADD CONSTRAINT github_download_snapshot_asset_count_check
    CHECK (asset_count IS NULL OR asset_count >= 0);

-- Hourly cumulative GitHub release asset download snapshots.
-- Only aggregate counts are retained; release metadata and asset names are not.
CREATE TABLE github_download_snapshot (
    hour_start TIMESTAMPTZ PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dmg_total BIGINT NOT NULL CHECK (dmg_total >= 0),
    zip_total BIGINT NOT NULL CHECK (zip_total >= 0),
    release_count INTEGER NOT NULL CHECK (release_count >= 0)
);

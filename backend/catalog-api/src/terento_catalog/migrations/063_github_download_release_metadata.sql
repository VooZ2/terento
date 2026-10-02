-- Retain authoritative GitHub release identity independently of download snapshots.
-- Historical snapshot rows remain unchanged and may be backfilled from GitHub's
-- current release collection without inferring release dates from counters.
CREATE TABLE IF NOT EXISTS github_release_marker (
    release_id TEXT PRIMARY KEY,
    release_tag TEXT,
    release_label TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT github_release_marker_id_check CHECK (btrim(release_id) <> ''),
    CONSTRAINT github_release_marker_label_check CHECK (btrim(release_label) <> '')
);

CREATE INDEX IF NOT EXISTS github_release_marker_published_at_idx
    ON github_release_marker (published_at, release_id);

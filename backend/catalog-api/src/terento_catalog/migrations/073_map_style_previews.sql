-- Map style previews: an operator switch per provider plus render bookkeeping.
-- Additive only; earlier API/scheduler revisions ignore these objects.
ALTER TABLE map_provider ADD COLUMN preview_enabled boolean NOT NULL DEFAULT false;

CREATE TABLE map_preview_layer (
    area_id TEXT NOT NULL CHECK (area_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    style_id TEXT NOT NULL CHECK (style_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'NOT_COVERED', 'PENDING', 'FAILED')),
    package_id TEXT REFERENCES map_package(id) ON DELETE SET NULL,
    package_version TEXT,
    release TEXT,
    tile_count INTEGER CHECK (tile_count IS NULL OR tile_count >= 0),
    bytes BIGINT CHECK (bytes IS NULL OR bytes >= 0),
    rendered_at TIMESTAMPTZ,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    retry_not_before TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT,
    PRIMARY KEY (area_id, style_id)
);
CREATE INDEX map_preview_layer_provider_idx ON map_preview_layer(provider_id, status);

CREATE TABLE map_preview_package_bounds (
    package_id TEXT NOT NULL REFERENCES map_package(id) ON DELETE CASCADE,
    package_version TEXT NOT NULL,
    west DOUBLE PRECISION NOT NULL,
    south DOUBLE PRECISION NOT NULL,
    east DOUBLE PRECISION NOT NULL,
    north DOUBLE PRECISION NOT NULL,
    inspected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (package_id, package_version)
);

CREATE TABLE map_preview_area_score (
    area_id TEXT PRIMARY KEY CHECK (area_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    diff_score DOUBLE PRECISION CHECK (diff_score IS NULL OR (diff_score >= 0 AND diff_score <= 1)),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE map_preview_release (
    id TEXT PRIMARY KEY CHECK (id ~ '^[0-9]{8}T[0-9]{6}Z$'),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    layer_count INTEGER NOT NULL CHECK (layer_count >= 0),
    bytes BIGINT NOT NULL CHECK (bytes >= 0)
);

-- One renderer at a time across scheduler restarts and deploy overlap.
CREATE TABLE map_preview_lease (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    owner TEXT,
    lease_until TIMESTAMPTZ NOT NULL DEFAULT 'epoch'
);
INSERT INTO map_preview_lease (id) VALUES (1);

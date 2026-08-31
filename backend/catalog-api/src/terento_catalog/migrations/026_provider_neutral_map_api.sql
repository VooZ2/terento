-- Beta.8 provider-neutral map API foundation.
-- Keep the legacy map/map_version tables and public fields intact while the
-- new package/artifact model is rolled out additively.

ALTER TABLE map_provider
    ADD COLUMN IF NOT EXISTS adapter_id TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN IF NOT EXISTS last_catalog_sync TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS license TEXT;

UPDATE map_provider
SET license = license_information
WHERE license IS NULL OR btrim(license) = '';

ALTER TABLE map_provider
    ALTER COLUMN license SET NOT NULL;

UPDATE map_provider
SET adapter_id = id
WHERE adapter_id IS NULL OR btrim(adapter_id) = '';

ALTER TABLE map_provider
    ALTER COLUMN adapter_id SET NOT NULL;

-- Register the reviewed beta.8 adapters as metadata only. OpenTopoMap starts
-- paused because its source/package gate is not yet accepted for activation.
INSERT INTO map_provider (
    id, name, adapter_id, status, website, license, license_information,
    attribution, license_url
) VALUES (
    'opentopomap',
    'OpenTopoMap',
    'opentopomap',
    'PAUSED',
    'https://opentopomap.org/',
    'Map data © OpenStreetMap contributors (ODbL); map rendering © OpenTopoMap.',
    'Map data © OpenStreetMap contributors (ODbL); map rendering © OpenTopoMap.',
    'Map data © OpenStreetMap contributors; map rendering © OpenTopoMap',
    'https://opentopomap.org/about'
)
ON CONFLICT (id) DO NOTHING;

ALTER TABLE map_provider
    ADD CONSTRAINT map_provider_status_check
    CHECK (status IN ('ACTIVE', 'PAUSED', 'RETIRED'));

CREATE UNIQUE INDEX IF NOT EXISTS map_provider_adapter_id_idx
    ON map_provider(adapter_id);

CREATE TABLE provider_source (
    id BIGSERIAL PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('WEBSITE', 'CATALOG', 'LICENSE', 'DOWNLOAD')
    ),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider_id, source_type, source_url)
);

CREATE INDEX provider_source_provider_idx ON provider_source(provider_id);

CREATE TABLE map_package (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE RESTRICT,
    legacy_map_id TEXT UNIQUE REFERENCES map(id) ON DELETE SET NULL,
    provider_region_id TEXT NOT NULL,
    canonical_region_id TEXT NOT NULL,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    country TEXT,
    release TEXT NOT NULL,
    release_id TEXT,
    version_label TEXT,
    generated_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    availability TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (
        availability IN ('AVAILABLE', 'WITHHELD', 'UNAVAILABLE', 'RETIRED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX map_package_provider_idx ON map_package(provider_id);
CREATE INDEX map_package_region_idx ON map_package(provider_id, region);
CREATE INDEX map_package_updated_idx ON map_package(updated_at DESC);

CREATE TABLE map_artifact (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES map_package(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('main', 'contours')),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    -- size_bytes is the provider source/archive size. install_size_bytes is
    -- the final Garmin IMG size used by the native storage gate.
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    install_size_bytes BIGINT CHECK (install_size_bytes IS NULL OR install_size_bytes >= 0),
    checksum_sha256 TEXT CHECK (
        checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
    ),
    content_type TEXT,
    required BOOLEAN NOT NULL DEFAULT TRUE,
    validation_status TEXT NOT NULL DEFAULT 'NOT_VALIDATED' CHECK (
        validation_status IN ('NOT_VALIDATED', 'VALIDATING', 'VALIDATED', 'FAILED', 'UNAVAILABLE')
    ),
    install_payload_path TEXT,
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (package_id, kind)
);

CREATE INDEX map_artifact_package_idx ON map_artifact(package_id);
CREATE INDEX map_artifact_validation_idx ON map_artifact(validation_status);

CREATE TABLE provider_health_check (
    id BIGSERIAL PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE CASCADE,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL CHECK (status IN ('HEALTHY', 'DEGRADED', 'DOWN', 'UNKNOWN')),
    website_status TEXT,
    catalog_status TEXT,
    redirect_status TEXT,
    download_status TEXT,
    mime_status TEXT,
    magic_status TEXT,
    zip_status TEXT,
    img_status TEXT,
    last_update_status TEXT,
    http_status INTEGER,
    final_url TEXT CHECK (final_url IS NULL OR final_url LIKE 'https://%'),
    content_type TEXT,
    artifact_count INTEGER CHECK (artifact_count IS NULL OR artifact_count >= 0),
    source_updated_at TIMESTAMPTZ,
    error_code TEXT,
    error_detail TEXT,
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX provider_health_check_provider_idx
    ON provider_health_check(provider_id, checked_at DESC);

CREATE TABLE catalog_collection_run (
    id BIGSERIAL PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')),
    package_count INTEGER NOT NULL DEFAULT 0 CHECK (package_count >= 0),
    artifact_count INTEGER NOT NULL DEFAULT 0 CHECK (artifact_count >= 0),
    error_code TEXT,
    error_detail TEXT
);

CREATE INDEX catalog_collection_run_provider_idx
    ON catalog_collection_run(provider_id, started_at DESC);

CREATE TABLE map_download_event (
    event_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL,
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE RESTRICT,
    map_package_id TEXT REFERENCES map_package(id) ON DELETE SET NULL,
    region TEXT,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'DOWNLOAD_STARTED', 'DOWNLOAD_SUCCEEDED', 'DOWNLOAD_FAILED',
            'INSTALL_SUCCEEDED', 'INSTALL_FAILED'
        )
    ),
    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED', 'UNKNOWN')),
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    app_build TEXT,
    UNIQUE (operation_id, event_type, map_package_id)
);

CREATE INDEX map_download_event_provider_date_idx
    ON map_download_event(provider_id, occurred_at DESC);
CREATE INDEX map_download_event_package_date_idx
    ON map_download_event(map_package_id, occurred_at DESC);
CREATE INDEX map_download_event_type_date_idx
    ON map_download_event(event_type, occurred_at DESC);

CREATE TABLE admin_audit_log (
    id BIGSERIAL PRIMARY KEY,
    admin_user_id BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    provider_id TEXT REFERENCES map_provider(id) ON DELETE SET NULL,
    old_status TEXT,
    new_status TEXT,
    reason TEXT,
    target TEXT,
    request_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX admin_audit_log_provider_idx
    ON admin_audit_log(provider_id, occurred_at DESC);
CREATE INDEX admin_audit_log_action_idx
    ON admin_audit_log(action, occurred_at DESC);

-- Backfill the existing FZK registry and current package into the new model.
UPDATE map_provider AS p
SET last_catalog_sync = source.last_sync
FROM (
    SELECT m.provider_id, MAX(v.updated_at) AS last_sync
    FROM map AS m
    LEFT JOIN map_version AS v ON v.map_id = m.id
    GROUP BY m.provider_id
) AS source
WHERE p.id = source.provider_id
  AND source.last_sync IS NOT NULL;

INSERT INTO provider_source (provider_id, source_type, source_url)
SELECT id, 'WEBSITE', website FROM map_provider
ON CONFLICT (provider_id, source_type, source_url) DO NOTHING;

INSERT INTO provider_source (provider_id, source_type, source_url)
SELECT id, 'LICENSE', license_url FROM map_provider
ON CONFLICT (provider_id, source_type, source_url) DO NOTHING;

INSERT INTO provider_source (provider_id, source_type, source_url)
VALUES
    ('freizeitkarte', 'CATALOG', 'https://www.freizeitkarte-osm.de/garmin/en/release.html'),
    ('opentopomap', 'CATALOG', 'https://garmin.opentopomap.org/')
ON CONFLICT (provider_id, source_type, source_url) DO NOTHING;

INSERT INTO map_package (
    id, provider_id, legacy_map_id, provider_region_id, canonical_region_id,
    name, region, country, release, release_id, version_label,
    source_updated_at, availability
)
SELECT
    m.id,
    m.provider_id,
    m.id,
    m.identifier,
    m.region,
    m.name,
    m.region,
    m.country,
    COALESCE(v.raw_version, 'unknown'),
    v.raw_version,
    v.raw_version,
    v.release_date::timestamptz,
    CASE WHEN v.id IS NULL THEN 'UNAVAILABLE' ELSE 'AVAILABLE' END
FROM map AS m
LEFT JOIN LATERAL (
    SELECT mv.*
    FROM map_version AS mv
    WHERE mv.map_id = m.id
    ORDER BY mv.version_year DESC, mv.version_month DESC, mv.updated_at DESC
    LIMIT 1
) AS v ON TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO map_artifact (
    id, package_id, kind, source_url, size_bytes, install_size_bytes,
    checksum_sha256, content_type, required, validation_status,
    install_payload_path, source_updated_at
)
SELECT
    m.id || '-main',
    m.id,
    'main',
    v.source_url,
    COALESCE(v.download_size_bytes, v.file_size_bytes),
    v.install_size_bytes,
    v.checksum_sha256,
    'application/zip',
    TRUE,
    CASE WHEN v.install_size_bytes IS NOT NULL THEN 'VALIDATED' ELSE 'NOT_VALIDATED' END,
    v.install_payload_path,
    v.release_date::timestamptz
FROM map AS m
JOIN LATERAL (
    SELECT mv.*
    FROM map_version AS mv
    WHERE mv.map_id = m.id
      AND mv.source_url IS NOT NULL
      AND COALESCE(mv.download_size_bytes, mv.file_size_bytes) IS NOT NULL
    ORDER BY mv.version_year DESC, mv.version_month DESC, mv.updated_at DESC
    LIMIT 1
) AS v ON TRUE
ON CONFLICT (id) DO NOTHING;

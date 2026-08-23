CREATE TABLE map_provider (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT NOT NULL,
    license_information TEXT NOT NULL,
    attribution TEXT NOT NULL,
    license_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE map (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES map_provider(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    country TEXT NOT NULL,
    identifier TEXT NOT NULL,
    managed_by_terento BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE map_version (
    id BIGSERIAL PRIMARY KEY,
    map_id TEXT NOT NULL REFERENCES map(id) ON DELETE CASCADE,
    version_year SMALLINT NOT NULL CHECK (version_year BETWEEN 2000 AND 2100),
    version_month SMALLINT NOT NULL CHECK (version_month BETWEEN 1 AND 12),
    raw_version TEXT NOT NULL,
    file_size_bytes BIGINT CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    release_date DATE,
    checksum_sha256 TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (map_id, version_year, version_month)
);

CREATE INDEX map_provider_id_idx ON map(provider_id);
CREATE INDEX map_version_map_id_idx ON map_version(map_id);
CREATE INDEX map_version_detected_at_idx ON map_version(detected_at DESC);

INSERT INTO map_provider (
    id, name, website, license_information, attribution, license_url
) VALUES (
    'freizeitkarte',
    'Freizeitkarte',
    'https://www.freizeitkarte-osm.de/garmin/en/mitteleuropa.html',
    'Map data © OpenStreetMap contributors (ODbL); produced map © FZK project. Contour-line sources vary by region.',
    'Map data © OpenStreetMap contributors; produced map © FZK project',
    'https://www.freizeitkarte-osm.de/garmin/en/imprint.html'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO map (
    id, provider_id, name, region, country, identifier, managed_by_terento
) VALUES (
    'freizeitkarte-ltu',
    'freizeitkarte',
    'Lithuania',
    'LTU',
    'Lithuania',
    'LTU+',
    TRUE
)
ON CONFLICT (id) DO NOTHING;

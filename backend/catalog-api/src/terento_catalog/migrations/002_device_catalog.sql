CREATE TABLE device_family (
    id TEXT PRIMARY KEY,
    manufacturer TEXT NOT NULL,
    name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE device_model (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES device_family(id) ON DELETE RESTRICT,
    manufacturer TEXT NOT NULL,
    model TEXT NOT NULL,
    canonical_model TEXT NOT NULL,
    variant TEXT NOT NULL,
    case_size_mm SMALLINT CHECK (case_size_mm IS NULL OR case_size_mm BETWEEN 1 AND 200),
    display_type TEXT,
    part_number TEXT,
    product_url TEXT NOT NULL CHECK (product_url LIKE 'https://%'),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    consecutive_missed_collections SMALLINT NOT NULL DEFAULT 0
        CHECK (consecutive_missed_collections >= 0),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE device_usb_identity (
    device_model_id TEXT NOT NULL REFERENCES device_model(id) ON DELETE RESTRICT,
    vendor_id INTEGER NOT NULL CHECK (vendor_id BETWEEN 0 AND 65535),
    product_id INTEGER NOT NULL CHECK (product_id BETWEEN 0 AND 65535),
    source TEXT NOT NULL,
    confidence TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (device_model_id, vendor_id, product_id)
);

CREATE TABLE device_asset (
    id BIGSERIAL PRIMARY KEY,
    device_model_id TEXT NOT NULL REFERENCES device_model(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED')),
    url TEXT CHECK (url IS NULL OR url LIKE 'https://%'),
    sha256 TEXT,
    width INTEGER CHECK (width IS NULL OR width > 0),
    height INTEGER CHECK (height IS NULL OR height > 0),
    mime_type TEXT,
    source_url TEXT CHECK (source_url IS NULL OR source_url LIKE 'https://%'),
    license_information TEXT,
    attribution TEXT,
    asset_version INTEGER CHECK (asset_version IS NULL OR asset_version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (device_model_id, asset_type)
);

CREATE TABLE device_collection_run (
    id BIGSERIAL PRIMARY KEY,
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')),
    discovered_count INTEGER NOT NULL DEFAULT 0 CHECK (discovered_count >= 0),
    canonical_count INTEGER NOT NULL DEFAULT 0 CHECK (canonical_count >= 0),
    warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX device_model_family_id_idx ON device_model(family_id);
CREATE INDEX device_model_active_idx ON device_model(active);
CREATE INDEX device_model_last_seen_idx ON device_model(last_seen_at DESC);
CREATE INDEX device_asset_approved_idx ON device_asset(device_model_id, status);
CREATE INDEX device_collection_run_finished_idx ON device_collection_run(finished_at DESC);

-- This is the existing, narrowly validated read-only MTP evidence. It is not
-- a general Garmin compatibility claim and must not be copied to other models.
INSERT INTO device_family (
    id, manufacturer, name, canonical_name, source_url
) VALUES (
    'garmin-fenix',
    'Garmin',
    'fēnix',
    'fenix',
    'https://www.garmin.com/en-US/c/wearables-smartwatches/'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url
) VALUES (
    'garmin-fenix-8-47-amoled',
    'garmin-fenix',
    'Garmin',
    'fēnix 8',
    'fenix 8',
    '47 mm, AMOLED',
    47,
    'AMOLED',
    'https://www.garmin.com/en-US/p/1228429/',
    'https://www.garmin.com/en-US/c/wearables-smartwatches/'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO device_usb_identity (
    device_model_id, vendor_id, product_id, source, confidence
) VALUES (
    'garmin-fenix-8-47-amoled',
    2334,
    20920,
    'terento-hardware-evidence',
    'tested'
)
ON CONFLICT (device_model_id, vendor_id, product_id) DO NOTHING;

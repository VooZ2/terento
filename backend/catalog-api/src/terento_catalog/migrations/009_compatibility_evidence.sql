CREATE TABLE compatibility_evidence_event (
    event_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model TEXT NOT NULL,
    family TEXT,
    firmware_version TEXT,
    usb_vendor_id INTEGER NOT NULL CHECK (usb_vendor_id BETWEEN 0 AND 65535),
    usb_product_id INTEGER NOT NULL CHECK (usb_product_id BETWEEN 0 AND 65535),
    transport TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider = 'freizeitkarte'),
    region TEXT NOT NULL,
    map_release TEXT NOT NULL,
    terento_version TEXT NOT NULL,
    macos_version TEXT NOT NULL,
    phase_outcome TEXT NOT NULL CHECK (phase_outcome IN ('SUCCEEDED', 'FAILED')),
    automatic_finishing_result TEXT NOT NULL CHECK (automatic_finishing_result IN ('VERIFIED', 'FAILED', 'NOT_REACHED')),
    error_category TEXT,
    raw_event JSONB NOT NULL
);

CREATE TABLE compatibility_evidence_confirmation (
    event_id UUID PRIMARY KEY REFERENCES compatibility_evidence_event(event_id) ON DELETE RESTRICT,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE compatibility_model_review (
    model TEXT PRIMARY KEY,
    review_status TEXT NOT NULL DEFAULT 'PENDING',
    physical_device_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (physical_device_evidence_count >= 0),
    review_notes TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX compatibility_evidence_model_idx ON compatibility_evidence_event(model);
CREATE INDEX compatibility_evidence_occurred_idx ON compatibility_evidence_event(occurred_at DESC);

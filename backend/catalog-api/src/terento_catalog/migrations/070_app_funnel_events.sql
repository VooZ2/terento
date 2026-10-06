-- 070: privacy-minimised app first-run funnel events (contracts/APP_FUNNEL_CONTRACT.md).
--
-- Additive and rollback-compatible: one new table that the previous API
-- revision never reads or writes. It is a separate population and never feeds
-- install, update, download or compatibility counts. No serial, Unit ID,
-- account, path, IP or persistent user/device identifier is stored; session_id
-- is random per app launch.
CREATE TABLE app_funnel_event (
    event_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    app_build TEXT NOT NULL CHECK (length(app_build) BETWEEN 1 AND 80),
    release_label TEXT NOT NULL CHECK (length(release_label) BETWEEN 1 AND 80),
    is_local_test BOOLEAN NOT NULL DEFAULT false,
    stage TEXT NOT NULL CHECK (stage IN ('DEVICE_CONNECT', 'AUTHORIZATION', 'CATALOG', 'INSTALL_BLOCKED')),
    outcome TEXT NOT NULL CHECK (
        (stage = 'DEVICE_CONNECT' AND outcome IN (
            'CONNECTED', 'TIMEOUT_NO_USB', 'TIMEOUT_USB_PRESENT', 'BUSY',
            'MULTIPLE_DEVICES', 'NOT_MTP_MODE', 'DISCONNECTED', 'FAILED'))
        OR (stage = 'AUTHORIZATION' AND outcome IN (
            'APPROVED', 'PENDING', 'OUT_OF_SCOPE', 'UNKNOWN_MODEL', 'AMBIGUOUS',
            'CATALOG_UNAVAILABLE', 'UPDATE_REQUIRED'))
        OR (stage = 'CATALOG' AND outcome IN (
            'REMOTE', 'REMOTE_PARTIAL', 'BUNDLED_FALLBACK', 'UPDATE_REQUIRED'))
        OR (stage = 'INSTALL_BLOCKED' AND outcome IN (
            'AUTHORIZATION', 'DEVICE_STORAGE', 'MAC_STORAGE', 'CATALOG_UNVERIFIED',
            'LOCAL_CAPABILITY', 'OTHER'))
    ),
    base_model TEXT CHECK (
        base_model IS NULL
        OR (length(base_model) BETWEEN 1 AND 80
            AND (stage = 'AUTHORIZATION' OR (stage = 'DEVICE_CONNECT' AND outcome = 'CONNECTED')))
    ),
    dropped_package_count INTEGER CHECK (
        dropped_package_count IS NULL
        OR (dropped_package_count >= 0 AND stage = 'CATALOG' AND outcome = 'REMOTE_PARTIAL')
    )
);

CREATE INDEX app_funnel_event_occurred_idx ON app_funnel_event (occurred_at);
CREATE INDEX app_funnel_event_received_idx ON app_funnel_event (received_at);

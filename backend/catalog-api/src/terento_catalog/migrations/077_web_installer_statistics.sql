-- 077: web installer statistics (contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).
--
-- Additive and rollback-compatible: two new tables that the previous API
-- revision never reads or writes. A separate population that never feeds app
-- install, update, download, compatibility, funnel or watch counts. No serial,
-- Unit ID, account, IP, file name, path or persistent identifier is stored;
-- session_id is random per page load.
CREATE TABLE web_installer_event (
    event_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_test BOOLEAN NOT NULL DEFAULT false,
    stage TEXT NOT NULL CHECK (stage IN ('GATE', 'CONNECT', 'MAP_RESULT', 'REMOVE', 'RECOVERY')),
    outcome TEXT NOT NULL CHECK (length(outcome) BETWEEN 1 AND 40),
    os_family TEXT CHECK (length(os_family) BETWEEN 1 AND 20),
    os_major SMALLINT CHECK (os_major BETWEEN 0 AND 99),
    browser_family TEXT CHECK (length(browser_family) BETWEEN 1 AND 20),
    browser_major SMALLINT CHECK (browser_major BETWEEN 1 AND 999),
    model TEXT CHECK (length(model) BETWEEN 1 AND 80),
    firmware TEXT CHECK (length(firmware) BETWEEN 1 AND 12),
    base_model TEXT CHECK (length(base_model) BETWEEN 1 AND 80),
    operation TEXT CHECK (operation IN ('install', 'update')),
    provider TEXT CHECK (length(provider) BETWEEN 1 AND 40),
    package_id TEXT CHECK (length(package_id) BETWEEN 1 AND 120),
    size_bucket TEXT CHECK (length(size_bucket) BETWEEN 1 AND 12),
    failure_stage TEXT CHECK (failure_stage IN ('PREPARE', 'DOWNLOAD', 'WRITE', 'VERIFY')),
    reason TEXT CHECK (length(reason) BETWEEN 1 AND 40),
    write_started BOOLEAN,
    write_s INTEGER CHECK (write_s BETWEEN 0 AND 86400),
    verify_s INTEGER CHECK (verify_s BETWEEN 0 AND 86400),
    error_name TEXT CHECK (length(error_name) BETWEEN 1 AND 40),
    http_status SMALLINT CHECK (http_status BETWEEN 100 AND 599),
    mtp_response INTEGER CHECK (mtp_response BETWEEN 8192 AND 43263)
);

CREATE INDEX web_installer_event_occurred_idx ON web_installer_event (occurred_at);
CREATE INDEX web_installer_event_received_idx ON web_installer_event (received_at);

CREATE TABLE web_installer_relay_job (
    job_id TEXT PRIMARY KEY CHECK (job_id ~ '^[0-9a-f]{16,32}$'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_test BOOLEAN NOT NULL DEFAULT false,
    requested_at TIMESTAMPTZ NOT NULL,
    ready_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ NOT NULL CHECK (finished_at >= requested_at),
    provider TEXT NOT NULL CHECK (length(provider) BETWEEN 1 AND 40),
    package_id TEXT NOT NULL CHECK (length(package_id) BETWEEN 1 AND 120),
    region TEXT CHECK (length(region) BETWEEN 1 AND 120),
    release TEXT CHECK (length(release) BETWEEN 1 AND 40),
    size_bytes BIGINT CHECK (size_bytes >= 0),
    served_bytes BIGINT NOT NULL CHECK (served_bytes >= 0),
    outcome TEXT NOT NULL CHECK (outcome IN (
        'DELIVERED', 'NOT_DOWNLOADED', 'FAILED', 'CANCELLED', 'EXPIRED', 'REFUSED', 'INTERRUPTED')),
    reason TEXT CHECK (
        (reason IS NULL) = (outcome NOT IN ('FAILED', 'REFUSED', 'INTERRUPTED'))
        AND (reason IS NULL OR length(reason) BETWEEN 1 AND 40)
    ),
    provider_http_status SMALLINT CHECK (
        provider_http_status IS NULL
        OR (provider_http_status BETWEEN 100 AND 599 AND reason = 'PROVIDER_HTTP_ERROR')
    )
);

CREATE INDEX web_installer_relay_job_requested_idx ON web_installer_relay_job (requested_at);
CREATE INDEX web_installer_relay_job_received_idx ON web_installer_relay_job (received_at);

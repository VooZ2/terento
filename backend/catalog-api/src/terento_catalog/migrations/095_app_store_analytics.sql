-- App Store statistics for Admin (Apple Analytics Reports API, asc_stats.py).
-- Additive only: four new tables that the previous API revision never reads,
-- so it keeps working while this migration runs and after a rollback.
--
-- app_store_daily_metric: Apple's own population as daily aggregates. No
-- person, device or account identifier exists in these rows: date, report
-- level (Standard totals, Detailed campaign rows), metric, source type,
-- campaign token, App Store territory and device type, count.
CREATE TABLE IF NOT EXISTS app_store_daily_metric (
    day DATE NOT NULL,
    report_level TEXT NOT NULL CHECK (report_level IN ('standard', 'detailed')),
    metric TEXT NOT NULL CHECK (metric IN ('impressions', 'product_page_views', 'first_time_downloads', 'redownloads')),
    source_type TEXT NOT NULL DEFAULT '' CHECK (length(source_type) <= 80),
    campaign TEXT NOT NULL DEFAULT '' CHECK (length(campaign) <= 200),
    territory TEXT NOT NULL DEFAULT '' CHECK (length(territory) <= 64),
    device TEXT NOT NULL DEFAULT '' CHECK (length(device) <= 64),
    count BIGINT NOT NULL CHECK (count > 0),
    PRIMARY KEY (day, report_level, metric, source_type, campaign, territory, device)
);

CREATE INDEX IF NOT EXISTS app_store_daily_metric_level_day
    ON app_store_daily_metric (report_level, day);

-- Which processed instance owns each day of one report: a newer processing
-- date replaces the day (Apple: never merge a date across two instances).
CREATE TABLE IF NOT EXISTS app_store_report_day (
    report_kind TEXT NOT NULL CHECK (report_kind IN ('engagement', 'downloads')),
    report_level TEXT NOT NULL CHECK (report_level IN ('standard', 'detailed')),
    day DATE NOT NULL,
    processing_date DATE NOT NULL,
    instance_id TEXT NOT NULL,
    PRIMARY KEY (report_kind, report_level, day)
);

-- Every processed instance once, so a second run never doubles a count.
CREATE TABLE IF NOT EXISTS app_store_report_instance (
    instance_id TEXT PRIMARY KEY CHECK (length(instance_id) BETWEEN 1 AND 200),
    report_kind TEXT NOT NULL CHECK (report_kind IN ('engagement', 'downloads')),
    report_level TEXT NOT NULL CHECK (report_level IN ('standard', 'detailed')),
    processing_date DATE NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_store_report_instance_kind_processing
    ON app_store_report_instance (report_kind, report_level, processing_date);

-- The last read of Apple (one row). last_error holds a fixed reason only
-- (for example "HTTP 401" or "timeout"), never a key, token, URL or body.
CREATE TABLE IF NOT EXISTS app_store_sync_state (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error TEXT CHECK (last_error IS NULL OR length(last_error) <= 200),
    request_state TEXT CHECK (request_state IS NULL OR request_state IN ('active', 'stopped', 'missing')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

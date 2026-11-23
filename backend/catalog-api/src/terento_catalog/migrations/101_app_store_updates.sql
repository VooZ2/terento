-- App Store Updates for Admin (Apple's App Store Downloads Standard report,
-- Download Type "Manual update" and "Auto-update"; asc_stats.py).
-- Additive only, so the previous API revision keeps working while this runs
-- and after a rollback: it never reads the new table, and it never writes
-- parse_version, so the instances it processes keep the default 1 and are
-- read again by this revision.
--
-- app_store_daily_update: updates per Apple report date as daily aggregates,
-- Standard only, with no person, device or account identifier (source type,
-- App Store territory and device type, count). A separate table, not a new
-- metric value in app_store_daily_metric, because the previous revision
-- sums every metric value it finds there.
CREATE TABLE IF NOT EXISTS app_store_daily_update (
    day DATE NOT NULL,
    source_type TEXT NOT NULL DEFAULT '' CHECK (length(source_type) <= 80),
    territory TEXT NOT NULL DEFAULT '' CHECK (length(territory) <= 64),
    device TEXT NOT NULL DEFAULT '' CHECK (length(device) <= 64),
    count BIGINT NOT NULL CHECK (count > 0),
    PRIMARY KEY (day, source_type, territory, device)
);

-- Which parser read an instance. An instance read by an older parser is read
-- again while Apple still lists it (daily instances stay about 35 days), so
-- the App Store Downloads Standard days already stored gain their updates.
ALTER TABLE app_store_report_instance
    ADD COLUMN IF NOT EXISTS parse_version SMALLINT NOT NULL DEFAULT 1 CHECK (parse_version >= 1);

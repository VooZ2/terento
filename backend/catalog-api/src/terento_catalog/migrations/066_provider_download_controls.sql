-- Operator controls are independent of collector-owned metadata.
ALTER TABLE map_provider ADD COLUMN health_check_interval_hours integer NOT NULL DEFAULT 1
    CHECK (health_check_interval_hours IN (1, 6, 24));
ALTER TABLE map_package ADD COLUMN downloads_disabled boolean NOT NULL DEFAULT false;
ALTER TABLE map_package ADD COLUMN downloads_disabled_reason text;
ALTER TABLE map_provider ADD COLUMN health_retry_not_before timestamptz;

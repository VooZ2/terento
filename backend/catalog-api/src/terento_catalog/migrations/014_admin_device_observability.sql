-- Additive fields for the private Garmin device observability surface. These
-- values are intentionally separate from public catalog and evidence status.
ALTER TABLE device_model
    ADD COLUMN map_capable BOOLEAN,
    ADD COLUMN support_status TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
    ADD COLUMN first_seen_collection_run_id BIGINT REFERENCES device_collection_run(id) ON DELETE SET NULL,
    ADD COLUMN last_seen_collection_run_id BIGINT REFERENCES device_collection_run(id) ON DELETE SET NULL;

ALTER TABLE device_model
    ADD CONSTRAINT device_model_support_status_check
    CHECK (support_status IN ('SUPPORTED', 'UNSUPPORTED', 'NOT_EVALUATED'));

-- Carry forward the one exact write-capable device profile already validated
-- by the native client. Other discovered records remain NOT_EVALUATED and
-- map capability stays NULL until it has explicit evidence.
UPDATE device_model
SET map_capable = TRUE,
    support_status = 'SUPPORTED'
WHERE id = 'garmin-fenix-8-47-amoled';

ALTER TABLE device_collection_run
    ADD COLUMN records_total_before INTEGER CHECK (records_total_before IS NULL OR records_total_before >= 0),
    ADD COLUMN records_total_after INTEGER CHECK (records_total_after IS NULL OR records_total_after >= 0),
    ADD COLUMN records_added INTEGER CHECK (records_added IS NULL OR records_added >= 0),
    ADD COLUMN records_updated INTEGER CHECK (records_updated IS NULL OR records_updated >= 0);

CREATE INDEX device_model_first_seen_run_idx
    ON device_model(first_seen_collection_run_id);

CREATE INDEX device_model_last_seen_run_idx
    ON device_model(last_seen_collection_run_id);

-- 080: web installer results join the shared install statistics
-- (owner decision 2026-10-11; contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).
--
-- Additive and rollback-compatible: four nullable columns and one view that
-- the previous API revision never reads.
--
-- usb_vendor_id / usb_product_id: the USB model code the watch reports. It is
-- the same for every watch of one model, so it identifies the model, never a
-- watch. canonical_device_model_id: the catalog model the API resolved from the
-- model text and USB code with the same identity assessment as app reports;
-- NULL until it resolves (the scheduler retries unresolved rows).
ALTER TABLE web_installer_event
    ADD COLUMN usb_vendor_id INTEGER CHECK (usb_vendor_id BETWEEN 0 AND 65535),
    ADD COLUMN usb_product_id INTEGER CHECK (usb_product_id BETWEEN 0 AND 65535),
    ADD COLUMN canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE SET NULL,
    ADD COLUMN identity_resolution TEXT CHECK (identity_resolution IN ('EXACT', 'SINGLE_MATCH', 'UNRESOLVED'));

CREATE INDEX web_installer_event_model_idx ON web_installer_event (canonical_device_model_id)
    WHERE stage = 'MAP_RESULT' AND is_test IS NOT TRUE;

-- One row per counted web map result: every attempt, like app results. A
-- failure counts only after writing to the watch started; preparation and
-- download failures, cancellations and test records never count.
CREATE VIEW web_installer_map_result AS
SELECT
    event_id,
    session_id,
    is_test,
    occurred_at,
    operation,
    provider,
    package_id,
    model,
    canonical_device_model_id,
    outcome AS result
FROM web_installer_event
WHERE stage = 'MAP_RESULT'
  AND is_test IS NOT TRUE
  AND (outcome = 'SUCCEEDED' OR (outcome = 'FAILED' AND write_started IS TRUE));

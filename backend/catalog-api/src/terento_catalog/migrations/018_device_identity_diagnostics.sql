ALTER TABLE compatibility_evidence_event
    ADD COLUMN raw_mtp_model TEXT,
    ADD COLUMN identity_resolution_code TEXT CHECK (
        identity_resolution_code IS NULL
        OR identity_resolution_code IN ('MTP_SERIAL', 'GARMIN_UNIT_ID', 'UNAVAILABLE')
    );

-- The three legacy failures reported in issue #32 were emitted by a client
-- that collapsed every "fenix 8 ..." value to "fēnix 8" and did not retain
-- the raw MTP model.  Preserve them for diagnostics, but quarantine their
-- unprovable identity so they cannot lower or create a public base-model row.
UPDATE compatibility_evidence_event
SET
    model = 'Identity pending',
    compatibility_identity = 'Identity pending · issue #32 · fēnix 8 Pro 51 mm',
    variant = 'Reported fēnix 8 Pro, 51 mm',
    display_type = NULL,
    canonical_device_model_id = NULL
WHERE phase_outcome = 'FAILED'
  AND model IN ('fēnix 8', 'fenix 8')
  AND case_size_mm = 51
  AND firmware_version = '2326'
  AND region = 'CHE+'
  AND occurred_at >= TIMESTAMPTZ '2026-08-26 00:00:00+00'
  AND occurred_at < TIMESTAMPTZ '2026-08-27 00:00:00+00';

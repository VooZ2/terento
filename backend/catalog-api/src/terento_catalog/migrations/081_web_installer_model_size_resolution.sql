-- 081: web records without a USB model code resolve by model and case size
-- (owner decision 2026-10-11; contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).
--
-- Additive and rollback-compatible: identity_resolution also accepts
-- MODEL_AND_SIZE, which the previous API revision never writes and only reads
-- as text.
ALTER TABLE web_installer_event DROP CONSTRAINT web_installer_event_identity_resolution_check;
ALTER TABLE web_installer_event ADD CONSTRAINT web_installer_event_identity_resolution_check
    CHECK (identity_resolution IN ('EXACT', 'SINGLE_MATCH', 'MODEL_AND_SIZE', 'UNRESOLVED'));

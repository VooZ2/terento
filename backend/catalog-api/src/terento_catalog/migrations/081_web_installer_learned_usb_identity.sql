-- 081: a web record may resolve its catalog model from a learned USB model
-- code (owner decision 2026-10-13; contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).
--
-- Widens one CHECK with one value. Rollback-compatible: the previous API
-- revision never writes USB_LEARNED and only re-resolves rows with no model.
ALTER TABLE web_installer_event
    DROP CONSTRAINT IF EXISTS web_installer_event_identity_resolution_check,
    ADD CONSTRAINT web_installer_event_identity_resolution_check
        CHECK (identity_resolution IN ('EXACT', 'SINGLE_MATCH', 'USB_LEARNED', 'UNRESOLVED'));

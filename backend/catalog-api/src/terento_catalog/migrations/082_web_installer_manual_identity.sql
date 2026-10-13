-- 082: an administrator may assign the catalog model of a counted web result
-- in Identity review, like an app result (owner request 2026-10-13;
-- contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).
--
-- Additive: one CHECK widened with MANUAL and one new audit table. The
-- previous API revision never writes MANUAL and only re-resolves rows with no
-- model or a learned USB code, so it keeps every manual assignment. Rollback
-- limit: it does not read the audit table, so a record an administrator
-- unassigned (no model) is resolved again by the automatic rules, which can
-- assign a model only where they now name exactly one.
ALTER TABLE web_installer_event
    DROP CONSTRAINT IF EXISTS web_installer_event_identity_resolution_check,
    ADD CONSTRAINT web_installer_event_identity_resolution_check
        CHECK (identity_resolution IN ('EXACT', 'SINGLE_MATCH', 'USB_LEARNED', 'MANUAL', 'UNRESOLVED'));

-- Every administrator decision on a web result, newest last. A result with any
-- decision keeps it: the scheduler never resolves it again.
CREATE TABLE web_installer_identity_audit (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES web_installer_event(event_id) ON DELETE CASCADE,
    previous_canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE SET NULL,
    previous_resolution TEXT,
    new_canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE SET NULL,
    action TEXT NOT NULL CHECK (action IN ('ASSIGN', 'MANUAL_ASSIGN', 'LEAVE_UNRESOLVED')),
    reason TEXT NOT NULL,
    note TEXT,
    corrected_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    corrected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX web_installer_identity_audit_event_idx
    ON web_installer_identity_audit (event_id, id DESC);

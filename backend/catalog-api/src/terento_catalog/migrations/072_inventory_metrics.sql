-- 072: optional pre-/post-write inventory timing on installation reports
-- (contracts/compatibility-event.schema.json `inventoryMetrics`).
--
-- Additive and rollback-compatible: one nullable JSONB column the previous
-- API revision never reads or writes. Diagnostics only: it never feeds any
-- install, update, download or compatibility count. Update reports keep the
-- same object inside map_update_diagnostic.payload.
ALTER TABLE compatibility_evidence_event
    ADD COLUMN inventory_metrics JSONB CHECK (
        inventory_metrics IS NULL OR jsonb_typeof(inventory_metrics) = 'object'
    );

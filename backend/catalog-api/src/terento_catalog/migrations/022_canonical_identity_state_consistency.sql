-- Align internal identity review state with an already validated canonical
-- device link. This migration is additive, audited, and does not alter event
-- outcomes, diagnostic lifecycle, timestamps, or compatibility counts.

INSERT INTO compatibility_identity_resolution_audit (
    event_id, previous_identity, previous_canonical_device_model_id,
    new_identity, new_canonical_device_model_id,
    action, reason, note, corrected_by
)
SELECT
    e.event_id, e.compatibility_identity, e.canonical_device_model_id,
    e.compatibility_identity, e.canonical_device_model_id,
    'ASSIGN', 'Canonical identity-state consistency backfill',
    'Migration 022 marked an existing validated canonical link as resolved.',
    NULL
FROM compatibility_evidence_event e
WHERE e.canonical_device_model_id IS NOT NULL
  AND e.identity_resolution_state = 'UNRESOLVED'
  AND NOT EXISTS (
      SELECT 1
      FROM compatibility_identity_resolution_audit a
      WHERE a.event_id = e.event_id
        AND a.reason = 'Canonical identity-state consistency backfill'
  );

UPDATE compatibility_evidence_event
SET identity_resolution_state = 'RESOLVED'
WHERE canonical_device_model_id IS NOT NULL
  AND identity_resolution_state = 'UNRESOLVED';

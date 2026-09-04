-- Accept privacy-safe evidence for a local custom IMG without treating the
-- source as a registered map provider or enabling it in map statistics.

ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;

ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap', 'custom'));

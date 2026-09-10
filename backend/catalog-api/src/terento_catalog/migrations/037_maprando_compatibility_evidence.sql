-- Add evidence acceptance; no public support claim or provider activation.
ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;
ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap', 'maprando', 'custom'));

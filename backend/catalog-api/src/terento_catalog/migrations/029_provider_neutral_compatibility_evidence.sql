-- Allow compatibility evidence for the reviewed beta.8 provider set.
-- This remains an explicit allowlist: adding a catalog row or arbitrary
-- adapter does not make a new provider eligible for watch evidence.

ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;

ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap'));

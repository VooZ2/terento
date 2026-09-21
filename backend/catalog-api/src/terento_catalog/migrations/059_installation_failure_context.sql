-- Validated observations only; historical events remain unknown (SQL NULL).
ALTER TABLE compatibility_evidence_event
    ADD COLUMN failure_context JSONB CHECK (jsonb_typeof(failure_context) = 'object'),
    ADD COLUMN original_failure_context JSONB CHECK (jsonb_typeof(original_failure_context) = 'object');

-- Update diagnostic administration is independent of compatibility evidence.
-- Historical payload IDs are not sufficient authority for model assignment.
ALTER TABLE map_update_diagnostic
 ADD COLUMN canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE SET NULL,
 ADD COLUMN identity_assessment JSONB,
 ADD COLUMN diagnostic_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (diagnostic_status IN ('ACTIVE','RESOLVED')),
 ADD COLUMN diagnostic_workflow_status TEXT NOT NULL DEFAULT 'OPEN' CHECK (diagnostic_workflow_status IN ('OPEN','IN_PROGRESS','UNDER_REVIEW')),
 ADD COLUMN linked_github_issue TEXT CHECK (linked_github_issue IS NULL OR linked_github_issue ~ '^#[1-9][0-9]{0,9}$'),
 ADD COLUMN resolution_code TEXT,
 ADD COLUMN resolution_note TEXT,
 ADD COLUMN resolved_at TIMESTAMPTZ,
 ADD COLUMN resolved_by BIGINT;
CREATE INDEX map_update_diagnostic_model_history ON map_update_diagnostic(canonical_device_model_id,occurred_at DESC,event_id) WHERE is_local_test IS FALSE;
CREATE INDEX map_update_diagnostic_linked_issue ON map_update_diagnostic(linked_github_issue) WHERE diagnostic_status='ACTIVE' AND is_local_test IS FALSE;
CREATE TABLE map_update_diagnostic_audit (
 id BIGSERIAL PRIMARY KEY,
 event_id UUID NOT NULL REFERENCES map_update_diagnostic(event_id) ON DELETE CASCADE,
 action TEXT NOT NULL,
 previous_state JSONB NOT NULL,
 next_state JSONB NOT NULL,
 changed_by BIGINT,
 changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX map_update_diagnostic_audit_event ON map_update_diagnostic_audit(event_id,id DESC);

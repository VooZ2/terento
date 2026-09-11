-- Keep unresolved diagnostics active while giving linked GitHub issues their
-- own operator workflow state. Diagnostic lifecycle remains ACTIVE/RESOLVED.
ALTER TABLE compatibility_evidence_event
    ADD COLUMN diagnostic_workflow_status TEXT NOT NULL DEFAULT 'OPEN';

ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_workflow_status_check
    CHECK (diagnostic_workflow_status IN ('OPEN', 'IN_PROGRESS', 'UNDER_REVIEW'));

ALTER TABLE compatibility_diagnostic_lifecycle_audit
    ADD COLUMN previous_workflow_status TEXT,
    ADD COLUMN new_workflow_status TEXT;

-- Existing linked issues were already being tracked as active diagnostics;
-- make their operator state explicit without changing outcomes or history.
UPDATE compatibility_evidence_event
SET diagnostic_workflow_status = 'IN_PROGRESS'
WHERE diagnostic_status = 'ACTIVE'
  AND linked_github_issue IS NOT NULL
  AND btrim(linked_github_issue) <> '';

CREATE INDEX compatibility_evidence_event_issue_workflow_idx
    ON compatibility_evidence_event (diagnostic_workflow_status, linked_github_issue)
    WHERE diagnostic_status = 'ACTIVE' AND linked_github_issue IS NOT NULL;

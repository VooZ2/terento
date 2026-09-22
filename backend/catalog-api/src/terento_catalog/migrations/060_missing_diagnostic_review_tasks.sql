-- Operator-only lifecycle for map-operation review gaps.
-- This table deliberately does not alter map_download_event or compatibility
-- telemetry. A missing row is an open task; a dismissed row is still retained
-- for audit and can be reopened by the operator.
CREATE TABLE admin_map_review_task (
    event_id UUID PRIMARY KEY REFERENCES map_download_event(event_id) ON DELETE CASCADE,
    task_type TEXT NOT NULL DEFAULT 'MISSING_DIAGNOSTIC'
        CHECK (task_type = 'MISSING_DIAGNOSTIC'),
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'DISMISSED')),
    dismissed_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    dismissed_at TIMESTAMPTZ,
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (status = 'OPEN' AND dismissed_at IS NULL)
        OR (status = 'DISMISSED' AND dismissed_at IS NOT NULL)
    )
);
CREATE INDEX admin_map_review_task_status_idx ON admin_map_review_task(status, updated_at DESC);

CREATE TABLE admin_map_review_task_audit (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES map_download_event(event_id) ON DELETE CASCADE,
    task_type TEXT NOT NULL CHECK (task_type = 'MISSING_DIAGNOSTIC'),
    previous_status TEXT NOT NULL CHECK (previous_status IN ('OPEN', 'DISMISSED')),
    new_status TEXT NOT NULL CHECK (new_status IN ('OPEN', 'DISMISSED')),
    note TEXT,
    changed_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX admin_map_review_task_audit_event_idx ON admin_map_review_task_audit(event_id, changed_at DESC, id DESC);

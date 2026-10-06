-- 071: user-sent support reports (contracts/SUPPORT_REPORT_CONTRACT.md).
--
-- Additive and rollback-compatible: two new tables that the previous API
-- revision never reads or writes. A support report is a sanitised issue report
-- the user explicitly chose to send; it is never statistics and never feeds
-- install, update, download, compatibility or funnel counts. No serial, Unit
-- ID, account, local path, raw log, file content or IP address is stored.
-- Rows are pruned 12 months after receipt by the scheduled retention job.
CREATE TABLE support_report (
    id UUID PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE CHECK (reference ~ '^TR-[A-Z2-7]{6}$'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL,
    app_build TEXT NOT NULL CHECK (length(app_build) BETWEEN 1 AND 80),
    release_label TEXT NOT NULL CHECK (length(release_label) BETWEEN 1 AND 80),
    is_local_test BOOLEAN NOT NULL DEFAULT false,
    category TEXT NOT NULL CHECK (category IN (
        'INSTALL_FAILED', 'UPDATE_FAILED', 'REMOVE_FAILED', 'CONNECTION', 'OTHER'
    )),
    operation_id UUID,
    user_message TEXT CHECK (user_message IS NULL OR length(user_message) BETWEEN 1 AND 2000),
    report JSONB NOT NULL CHECK (jsonb_typeof(report) = 'object'),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'HANDLED')),
    handled_at TIMESTAMPTZ,
    handled_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    linked_github_issue TEXT CHECK (
        linked_github_issue IS NULL OR linked_github_issue ~ '^#[1-9][0-9]{0,9}$'
    ),
    note TEXT CHECK (note IS NULL OR length(note) BETWEEN 1 AND 2000),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((status = 'HANDLED') = (handled_at IS NOT NULL))
);

CREATE INDEX support_report_open_idx
    ON support_report (status, received_at DESC)
    WHERE is_local_test IS FALSE;
CREATE INDEX support_report_received_idx ON support_report (received_at);
CREATE INDEX support_report_operation_idx
    ON support_report (operation_id)
    WHERE operation_id IS NOT NULL;

CREATE TABLE support_report_audit (
    id BIGSERIAL PRIMARY KEY,
    support_report_id UUID NOT NULL REFERENCES support_report(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('HANDLED', 'REOPENED', 'ISSUE_LINKED', 'ISSUE_UNLINKED')),
    previous_status TEXT NOT NULL CHECK (previous_status IN ('OPEN', 'HANDLED')),
    new_status TEXT NOT NULL CHECK (new_status IN ('OPEN', 'HANDLED')),
    previous_github_issue TEXT,
    new_github_issue TEXT,
    note TEXT,
    changed_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX support_report_audit_report_idx ON support_report_audit (support_report_id, id DESC);

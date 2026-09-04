-- Private operator workflow metadata; installation outcomes remain immutable.
CREATE TABLE admin_github_issue_sync (
    issue_number BIGINT PRIMARY KEY CHECK (issue_number > 0),
    state TEXT CHECK (state IN ('open', 'closed')),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error TEXT
);

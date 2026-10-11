-- 079: owner-authorized one-time cleanup of the web installer statistics, so
-- the Admin Web installer page starts empty before public testing.
--
-- Gediminas (owner) asked on 2026-10-11 to delete his fake/test installs from
-- the production Admin Web installer page and, after reviewing the read-only
-- per-day, system, browser and model listing (33 events, 3 relay jobs received
-- up to 2026-10-11T15:39:48.365772Z), answered "Trink viska is statistikos"
-- (delete everything from the statistics), then set the boundary: records up
-- to 2026-10-11 18:50 Europe/Vilnius (15:50:00Z) are removed, later ones stay.
-- His tests between the check and 18:50 go too. A data-only backup of
-- both tables was taken at the check, and the deploy helper writes a full
-- pre-migration snapshot.
--
-- Fails closed: a non-empty database must still hold exactly the reviewed
-- counts up to the check cutoff, otherwise the migration (and the deploy)
-- stops before any row is removed. A pristine CI database is a safe no-op.

CREATE TEMP TABLE _web_installer_cleanup_guard (
    matches_reviewed_counts BOOLEAN NOT NULL CHECK (matches_reviewed_counts)
) ON COMMIT DROP;

INSERT INTO _web_installer_cleanup_guard (matches_reviewed_counts)
SELECT
    (
        (SELECT count(*) FROM web_installer_event
         WHERE received_at <= TIMESTAMPTZ '2026-10-11T15:39:48.365772Z') = 33
        AND (SELECT count(*) FROM web_installer_relay_job
             WHERE received_at <= TIMESTAMPTZ '2026-10-11T15:39:48.365772Z') = 3
    )
    OR (
        NOT EXISTS (SELECT 1 FROM web_installer_event)
        AND NOT EXISTS (SELECT 1 FROM web_installer_relay_job)
    );

WITH deleted AS (
    DELETE FROM web_installer_event
    WHERE received_at < TIMESTAMPTZ '2026-10-11T15:50:00Z'
    RETURNING received_at
)
SELECT
    count(*) AS row_count,
    count(*) FILTER (WHERE received_at > TIMESTAMPTZ '2026-10-11T15:39:48.365772Z') AS after_check
INTO TEMP TABLE _web_installer_deleted_events
FROM deleted;

WITH deleted AS (
    DELETE FROM web_installer_relay_job
    WHERE received_at < TIMESTAMPTZ '2026-10-11T15:50:00Z'
    RETURNING received_at
)
SELECT
    count(*) AS row_count,
    count(*) FILTER (WHERE received_at > TIMESTAMPTZ '2026-10-11T15:39:48.365772Z') AS after_check
INTO TEMP TABLE _web_installer_deleted_relay_jobs
FROM deleted;

INSERT INTO admin_audit_log (admin_user_id, action, target, reason, details)
SELECT
    NULL,
    'web_installer.owner_test_records_purged',
    'web-installer-records-before-2026-10-11T15:50:00Z',
    'Owner-authorized removal of web installer test records before public testing',
    jsonb_build_object(
        'checkCutoff', '2026-10-11T15:39:48.365772Z',
        'receivedBefore', '2026-10-11T15:50:00Z',
        'eventCount', e.row_count,
        'eventsAfterCheck', e.after_check,
        'relayJobCount', j.row_count,
        'relayJobsAfterCheck', j.after_check
    )
FROM _web_installer_deleted_events AS e, _web_installer_deleted_relay_jobs AS j
WHERE e.row_count + j.row_count > 0;

DROP TABLE _web_installer_deleted_events;
DROP TABLE _web_installer_deleted_relay_jobs;

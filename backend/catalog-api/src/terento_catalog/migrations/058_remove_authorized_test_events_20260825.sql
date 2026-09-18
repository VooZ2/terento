-- User-authorized one-time cleanup of five test installations.
--
-- The owner supplied the displayed Europe/Vilnius minute and the old 1.0.0
-- app label. Resolve the exact rows in each telemetry stream first, then
-- remove only their operation lifecycles and linked evidence.

CREATE TEMP TABLE _authorized_test_event_specs (
    local_occurred_at TIMESTAMP NOT NULL,
    region TEXT NOT NULL,
    phase_outcome TEXT NOT NULL,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _authorized_test_event_specs (
    local_occurred_at, region, phase_outcome, event_type, outcome
)
VALUES
    (TIMESTAMP '2026-08-26 11:18', 'AND', 'FAILED', 'INSTALL_FAILED', 'FAILED'),
    (TIMESTAMP '2026-08-25 19:04', 'LTU+', 'SUCCEEDED', 'INSTALL_SUCCEEDED', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 14:47', 'LTU+', 'SUCCEEDED', 'INSTALL_SUCCEEDED', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 14:32', 'BALEARICS', 'SUCCEEDED', 'INSTALL_SUCCEEDED', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 13:38', 'AZORES', 'SUCCEEDED', 'INSTALL_SUCCEEDED', 'SUCCEEDED');

CREATE TEMP TABLE _authorized_test_compat_targets ON COMMIT DROP AS
SELECT
    e.event_id,
    e.operation_id,
    e.occurred_at AT TIME ZONE 'Europe/Vilnius' AS local_occurred_at
FROM compatibility_evidence_event AS e
JOIN _authorized_test_event_specs AS s
  ON date_trunc('minute', e.occurred_at AT TIME ZONE 'Europe/Vilnius') = s.local_occurred_at
 AND upper(COALESCE(e.region, '')) = upper(s.region)
 AND e.phase_outcome = s.phase_outcome
WHERE COALESCE(NULLIF(e.release_label, ''), e.terento_version) = '1.0.0';

CREATE TEMP TABLE _authorized_test_map_targets ON COMMIT DROP AS
SELECT
    m.event_id,
    m.operation_id,
    m.occurred_at AT TIME ZONE 'Europe/Vilnius' AS local_occurred_at
FROM map_download_event AS m
JOIN _authorized_test_event_specs AS s
  ON date_trunc('minute', m.occurred_at AT TIME ZONE 'Europe/Vilnius') = s.local_occurred_at
 AND upper(COALESCE(m.region, '')) = upper(s.region)
 AND m.event_type = s.event_type
 AND m.outcome = s.outcome
WHERE m.provider_id = 'freizeitkarte'
  AND COALESCE(NULLIF(m.release_label, ''), '') = '1.0.0';

CREATE TEMP TABLE _authorized_test_operation_targets ON COMMIT DROP AS
SELECT DISTINCT operation_id
FROM (
    SELECT operation_id FROM _authorized_test_compat_targets WHERE operation_id IS NOT NULL
    UNION ALL
    SELECT operation_id FROM _authorized_test_map_targets
) AS target_operations;

-- The temporary CHECK constraint makes the migration fail closed without a
-- dollar-quoted PL/pgSQL block (the migration runner intentionally splits
-- ordinary SQL statements on semicolons). A pristine CI database is a safe
-- no-op. A non-empty database must contain all five requested rows in one
-- stream, or the same five operation IDs in both streams.
CREATE TEMP TABLE _authorized_test_event_guard (
    matches_requested_shape BOOLEAN NOT NULL CHECK (matches_requested_shape)
) ON COMMIT DROP;

INSERT INTO _authorized_test_event_guard (matches_requested_shape)
WITH counts AS (
    SELECT
        (SELECT count(*) FROM _authorized_test_compat_targets) AS compat_count,
        (SELECT count(DISTINCT event_id) FROM _authorized_test_compat_targets) AS compat_events,
        (SELECT count(DISTINCT operation_id) FROM _authorized_test_compat_targets WHERE operation_id IS NOT NULL) AS compat_operations,
        (SELECT count(DISTINCT date_trunc('minute', local_occurred_at)) FROM _authorized_test_compat_targets) AS compat_minutes,
        (SELECT count(*) FROM _authorized_test_map_targets) AS map_count,
        (SELECT count(DISTINCT event_id) FROM _authorized_test_map_targets) AS map_events,
        (SELECT count(DISTINCT operation_id) FROM _authorized_test_map_targets) AS map_operations,
        (SELECT count(DISTINCT date_trunc('minute', local_occurred_at)) FROM _authorized_test_map_targets) AS map_minutes
), same_operations AS (
    SELECT NOT EXISTS (
        (SELECT operation_id FROM _authorized_test_compat_targets WHERE operation_id IS NOT NULL)
        EXCEPT
        (SELECT operation_id FROM _authorized_test_map_targets)
        UNION ALL
        (SELECT operation_id FROM _authorized_test_map_targets)
        EXCEPT
        (SELECT operation_id FROM _authorized_test_compat_targets WHERE operation_id IS NOT NULL)
    ) AS value
)
SELECT
    (
        (
            compat_count = 5 AND compat_events = 5 AND compat_minutes = 5
            AND map_count = 0
        )
        OR (
            map_count = 5 AND map_events = 5 AND map_operations = 5 AND map_minutes = 5
            AND compat_count = 0
        )
        OR (
            compat_count = 5 AND compat_events = 5 AND compat_operations = 5 AND compat_minutes = 5
            AND map_count = 5 AND map_events = 5 AND map_operations = 5 AND map_minutes = 5
            AND same_operations.value
        )
        OR (
            compat_count = 0 AND map_count = 0
            AND NOT EXISTS (SELECT 1 FROM map_download_event)
            AND NOT EXISTS (SELECT 1 FROM compatibility_evidence_event)
        )
    )
FROM counts, same_operations;

-- Map lifecycle rows are keyed by operation UUID. Compatibility rows are
-- removed by exact event ID as well as operation ID to support legacy rows
-- without an operation UUID, while preserving operation-level cleanup when
-- the UUID is present.
WITH deleted AS (
    DELETE FROM map_download_event AS m
    USING _authorized_test_operation_targets AS t
    WHERE m.operation_id = t.operation_id
    RETURNING m.event_id
)
SELECT count(*) AS event_count INTO TEMP TABLE _authorized_deleted_map_events
FROM deleted;

WITH deleted AS (
    DELETE FROM compatibility_evidence_event AS e
    WHERE e.event_id IN (SELECT event_id FROM _authorized_test_compat_targets)
       OR e.operation_id IN (SELECT operation_id FROM _authorized_test_operation_targets)
    RETURNING e.event_id
)
SELECT count(*) AS event_count INTO TEMP TABLE _authorized_deleted_compatibility_events
FROM deleted;

INSERT INTO admin_audit_log (admin_user_id, action, target, reason, details)
SELECT
    NULL,
    'telemetry.authorized_test_events_purged',
    'exact-test-event-minutes',
    'Owner-authorized removal of five test installations',
    jsonb_build_object(
        'timeZone', 'Europe/Vilnius',
        'releaseLabel', '1.0.0',
        'requestedMinutes', ARRAY[
            '2026-08-26 11:18', '2026-08-25 19:04',
            '2026-08-25 14:47', '2026-08-25 14:32',
            '2026-08-25 13:38'
        ],
        'mapEventCount', (SELECT event_count FROM _authorized_deleted_map_events),
        'compatibilityEventCount', (SELECT event_count FROM _authorized_deleted_compatibility_events)
    );

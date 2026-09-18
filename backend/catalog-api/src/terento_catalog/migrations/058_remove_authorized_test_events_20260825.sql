-- User-authorized one-time cleanup of five test installations.
--
-- The owner supplied the displayed Europe/Vilnius minute and the old 1.0.0
-- app label. These rows are map-installation events, so resolve the exact
-- INSTALL_* rows first, then remove only their operation lifecycles and any
-- compatibility evidence linked to those same operations.

CREATE TEMP TABLE _authorized_test_event_specs (
    local_occurred_at TIMESTAMP NOT NULL,
    region TEXT NOT NULL,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _authorized_test_event_specs (local_occurred_at, region, event_type, outcome)
VALUES
    (TIMESTAMP '2026-08-26 11:18', 'AND', 'INSTALL_FAILED', 'FAILED'),
    (TIMESTAMP '2026-08-25 19:04', 'LTU+', 'INSTALL_SUCCEEDED', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 14:47', 'LTU+', 'INSTALL_SUCCEEDED', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 14:32', 'BALEARICS', 'INSTALL_SUCCEEDED', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 13:38', 'AZORES', 'INSTALL_SUCCEEDED', 'SUCCEEDED');

CREATE TEMP TABLE _authorized_test_map_targets ON COMMIT DROP AS
SELECT
    m.event_id,
    m.operation_id,
    m.occurred_at AT TIME ZONE 'Europe/Vilnius' AS local_occurred_at,
    m.region,
    m.event_type,
    m.outcome
FROM map_download_event AS m
JOIN _authorized_test_event_specs AS s
  ON date_trunc('minute', m.occurred_at AT TIME ZONE 'Europe/Vilnius') = s.local_occurred_at
 AND upper(COALESCE(m.region, '')) = upper(s.region)
 AND m.event_type = s.event_type
 AND m.outcome = s.outcome
WHERE m.provider_id = 'freizeitkarte'
  AND COALESCE(NULLIF(m.release_label, ''), '') = '1.0.0';

-- The temporary CHECK constraint makes the migration fail closed without a
-- dollar-quoted PL/pgSQL block (the migration runner intentionally splits
-- ordinary SQL statements on semicolons). A pristine CI database is a safe
-- no-op; any non-empty database must contain exactly the five requested map
-- rows before deletion can begin.
CREATE TEMP TABLE _authorized_test_event_guard (
    matches_requested_shape BOOLEAN NOT NULL CHECK (matches_requested_shape)
) ON COMMIT DROP;

INSERT INTO _authorized_test_event_guard (matches_requested_shape)
SELECT (
        count(*) = 5
        AND count(DISTINCT event_id) = 5
        AND count(DISTINCT operation_id) = 5
        AND count(DISTINCT date_trunc('minute', local_occurred_at)) = 5
    )
    OR (
        NOT EXISTS (SELECT 1 FROM map_download_event)
        AND NOT EXISTS (SELECT 1 FROM compatibility_evidence_event)
    )
FROM _authorized_test_map_targets;

-- Map lifecycle rows are keyed by operation UUID. This removes all lifecycle
-- phases belonging to the five exact operations, and nothing selected by a
-- timestamp-only predicate in the map stream.
WITH deleted AS (
    DELETE FROM map_download_event AS m
    USING (SELECT DISTINCT operation_id FROM _authorized_test_map_targets) AS t
    WHERE m.operation_id = t.operation_id
    RETURNING m.event_id
)
SELECT count(*) AS event_count INTO TEMP TABLE _authorized_deleted_map_events
FROM deleted;

WITH deleted AS (
    DELETE FROM compatibility_evidence_event AS e
    USING (SELECT DISTINCT operation_id FROM _authorized_test_map_targets) AS t
    WHERE e.operation_id = t.operation_id
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

-- User-authorized one-time cleanup of five test installations.
--
-- The owner supplied the displayed Europe/Vilnius minute and the old 1.0.0
-- app label. Resolve those exact compatibility operations first, then remove
-- only their dependent lifecycle rows and event rows. The guard stops
-- the migration if the five requested minutes are not all present, so a
-- timezone or release-label mismatch cannot silently delete another event.

CREATE TEMP TABLE _authorized_test_event_specs (
    local_occurred_at TIMESTAMP NOT NULL,
    region TEXT NOT NULL,
    phase_outcome TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _authorized_test_event_specs (local_occurred_at, region, phase_outcome)
VALUES
    (TIMESTAMP '2026-08-26 11:18', 'AND', 'FAILED'),
    (TIMESTAMP '2026-08-25 19:04', 'LTU+', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 14:47', 'LTU+', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 14:32', 'BALEARICS', 'SUCCEEDED'),
    (TIMESTAMP '2026-08-25 13:38', 'AZORES', 'SUCCEEDED');

CREATE TEMP TABLE _authorized_test_event_targets ON COMMIT DROP AS
SELECT
    e.event_id,
    e.operation_id,
    e.occurred_at AT TIME ZONE 'Europe/Vilnius' AS local_occurred_at,
    e.region,
    e.phase_outcome
FROM compatibility_evidence_event AS e
JOIN _authorized_test_event_specs AS s
  ON date_trunc('minute', e.occurred_at AT TIME ZONE 'Europe/Vilnius') = s.local_occurred_at
 AND upper(e.region) = upper(s.region)
 AND e.phase_outcome = s.phase_outcome
WHERE COALESCE(NULLIF(e.release_label, ''), e.terento_version) = '1.0.0';

-- The temporary CHECK constraint makes the migration fail closed without a
-- dollar-quoted PL/pgSQL block (the migration runner intentionally splits
-- ordinary SQL statements on semicolons).
CREATE TEMP TABLE _authorized_test_event_guard (
    matches_requested_shape BOOLEAN NOT NULL CHECK (matches_requested_shape)
) ON COMMIT DROP;

INSERT INTO _authorized_test_event_guard (matches_requested_shape)
SELECT (
        count(DISTINCT date_trunc('minute', local_occurred_at)) = 5
        AND count(DISTINCT operation_id) FILTER (WHERE operation_id IS NOT NULL) = 5
    )
    OR (
        count(*) = 0
        AND NOT EXISTS (SELECT 1 FROM compatibility_evidence_event)
    )
FROM _authorized_test_event_targets;

-- Map lifecycle rows are keyed by operation UUID. This removes all lifecycle
-- phases belonging to the five exact compatibility operations, and nothing
-- selected by a timestamp-only predicate in the map stream.
WITH deleted AS (
    DELETE FROM map_download_event AS m
    USING _authorized_test_event_targets AS t
    WHERE t.operation_id IS NOT NULL
      AND m.operation_id = t.operation_id
    RETURNING m.event_id
)
SELECT count(*) AS event_count INTO TEMP TABLE _authorized_deleted_map_events
FROM deleted;

WITH deleted AS (
    DELETE FROM compatibility_evidence_event AS e
    USING _authorized_test_event_targets AS t
    WHERE e.event_id = t.event_id
       OR (t.operation_id IS NOT NULL AND e.operation_id = t.operation_id)
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
        'compatibilityEventCount', (SELECT event_count FROM _authorized_deleted_compatibility_events),
        'mapEventCount', (SELECT event_count FROM _authorized_deleted_map_events)
    );

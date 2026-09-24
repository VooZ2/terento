-- SELECT-only verification after an approved, successful 062 runner invocation.
-- Run inside BEGIN READ ONLY ... ROLLBACK against the same target database.
-- Before use, replace the two NULL baseline values below with the exact counts
-- retained from installation-statistics-062-live-precheck.sql. A NULL baseline
-- deliberately yields ABORT POSTCHECK.
WITH baseline(compatibility_rows, map_rows) AS (VALUES
    (NULL::bigint, NULL::bigint)
), expected_versions(version) AS (
    SELECT lpad(value::text, 3, '0')
    FROM generate_series(1, 62) AS versions(value)
),
expected_columns(table_name, column_name, data_type) AS (VALUES
    ('compatibility_evidence_event', 'statistics_exclusion_code', 'text'),
    ('compatibility_evidence_event', 'statistics_exclusion_reason', 'text'),
    ('compatibility_evidence_event', 'security_issue_code', 'text'),
    ('map_download_event', 'map_result_index', 'integer'),
    ('map_download_event', 'statistics_exclusion_code', 'text'),
    ('map_download_event', 'statistics_exclusion_reason', 'text'),
    ('map_download_event', 'security_issue_code', 'text')
), expected_audit_columns(ordinal_position, column_name, data_type, is_nullable, default_kind) AS (VALUES
    (1, 'id', 'bigint', 'NO', 'sequence'),
    (2, 'stream', 'text', 'NO', 'none'),
    (3, 'event_id', 'uuid', 'NO', 'none'),
    (4, 'exclusion_code', 'text', 'NO', 'none'),
    (5, 'reason', 'text', 'NO', 'none'),
    (6, 'security_issue_code', 'text', 'YES', 'none'),
    (7, 'source', 'text', 'NO', 'none'),
    (8, 'created_at', 'timestamp with time zone', 'NO', 'now')
),
expected_view_columns(ordinal_position, column_name, data_type) AS (VALUES
    (1, 'compatibility_identity', 'text'),
    (2, 'model', 'text'),
    (3, 'variant', 'text'),
    (4, 'case_size_mm', 'integer'),
    (5, 'display_type', 'text'),
    (6, 'canonical_device_model_id', 'text'),
    (7, 'firmware_versions', 'text'),
    (8, 'attempted_install_count', 'bigint'),
    (9, 'successful_install_count', 'bigint'),
    (10, 'reconnect_verified_install_count', 'bigint'),
    (11, 'failed_install_count', 'bigint'),
    (12, 'firmware_version_count', 'bigint'),
    (13, 'success_rate', 'numeric'),
    (14, 'last_success', 'timestamp with time zone'),
    (15, 'last_failure', 'timestamp with time zone'),
    (16, 'last_evidence', 'timestamp with time zone'),
    (17, 'map_result_count', 'numeric'),
    (18, 'successful_map_result_count', 'numeric'),
    (19, 'failed_map_result_count', 'numeric'),
    (20, 'not_started_map_result_count', 'numeric'),
    (21, 'prewrite_failure_count', 'bigint'),
    (22, 'error_categories', 'jsonb'),
    (23, 'calculated_status', 'text'),
    (24, 'recognized_map_capable_evidence', 'boolean'),
    (25, 'physical_device_evidence_count', 'integer'),
    (26, 'review_notes', 'text'),
    (27, 'review_status', 'text'),
    (28, 'public_statistics_enabled', 'boolean'),
    (29, 'public_display_name', 'text')
), live_view AS (
    SELECT c.oid, c.relkind, pg_get_viewdef(c.oid, true) AS definition
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema()
      AND c.relname = 'compatibility_model_statistics'
), live_view_columns AS (
    SELECT ordinal_position, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'compatibility_model_statistics'
), view_signature AS (
    SELECT count(*) FILTER (
        WHERE expected.column_name IS NULL
           OR live.column_name IS NULL
           OR expected.column_name IS DISTINCT FROM live.column_name
           OR expected.data_type IS DISTINCT FROM live.data_type
    ) AS mismatch_count,
    count(live.column_name) AS live_column_count
    FROM expected_view_columns expected
    FULL OUTER JOIN live_view_columns live
      ON live.ordinal_position = expected.ordinal_position
), column_state AS (
    SELECT count(*) AS expected_column_count,
           count(*) FILTER (
               WHERE live.column_name IS NULL
                  OR live.data_type IS DISTINCT FROM expected.data_type
                  OR live.is_nullable IS DISTINCT FROM 'YES'
                  OR live.column_default IS NOT NULL
           ) AS mismatch_count
    FROM expected_columns expected
    LEFT JOIN information_schema.columns live
      ON live.table_schema = current_schema()
     AND live.table_name = expected.table_name
     AND live.column_name = expected.column_name
), live_audit_table AS (
    SELECT c.oid, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema()
      AND c.relname = 'statistics_exclusion_audit'
), live_audit_columns AS (
    SELECT ordinal_position, column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'statistics_exclusion_audit'
), audit_column_signature AS (
    SELECT count(*) AS expected_column_count,
           count(*) FILTER (
               WHERE expected.column_name IS NULL
                  OR live.column_name IS NULL
                  OR live.column_name IS DISTINCT FROM expected.column_name
                  OR live.data_type IS DISTINCT FROM expected.data_type
                  OR live.is_nullable IS DISTINCT FROM expected.is_nullable
                  OR CASE expected.default_kind
                         WHEN 'sequence' THEN NOT coalesce(position('nextval(' IN lower(live.column_default)) = 1, false)
                         WHEN 'now' THEN NOT coalesce(
                             regexp_replace(lower(live.column_default), '[[:space:]()]', '', 'g') = 'now', false
                         )
                         ELSE live.column_default IS NOT NULL
                     END
           ) AS mismatch_count
    FROM expected_audit_columns expected
    FULL OUTER JOIN live_audit_columns live
      ON live.ordinal_position = expected.ordinal_position
), audit_constraints AS (
    SELECT
        count(*) FILTER (WHERE contype IN ('p', 'u', 'c')) AS key_check_count,
        bool_or(conname = 'statistics_exclusion_audit_pkey' AND contype = 'p' AND convalidated
                AND regexp_replace(lower(pg_get_constraintdef(oid, true)), '[[:space:]()]', '', 'g')
                    = 'primarykeyid') AS has_pk,
        bool_or(conname = 'statistics_exclusion_audit_stream_check' AND contype = 'c'
                AND convalidated
                AND regexp_replace(lower(pg_get_constraintdef(oid, true)), '[[:space:]()]', '', 'g')
                    = 'checkstream=anyarray[''compatibility''::text,''map''::text]') AS has_stream_check,
        bool_or(conname = 'statistics_exclusion_audit_stream_event_id_exclusion_code_key'
                AND contype = 'u' AND convalidated
                AND regexp_replace(lower(pg_get_constraintdef(oid, true)), '[[:space:]()]', '', 'g')
                    = 'uniquestream,event_id,exclusion_code') AS has_unique
    FROM pg_constraint
    WHERE conrelid = to_regclass(format('%I.statistics_exclusion_audit', current_schema()))
), required_indexes AS (
    SELECT required.index_name,
           i.oid IS NOT NULL AND x.indisvalid AND x.indisready AS present_valid
    FROM (VALUES
        ('compatibility_statistics_exclusion_idx'),
        ('map_statistics_exclusion_idx'),
        ('statistics_exclusion_audit_pkey'),
        ('statistics_exclusion_audit_stream_event_id_exclusion_code_key'),
        ('statistics_exclusion_audit_event_idx')
    ) AS required(index_name)
    LEFT JOIN pg_namespace n ON n.nspname = current_schema()
    LEFT JOIN pg_class i ON i.relnamespace = n.oid AND i.relname = required.index_name AND i.relkind = 'i'
    LEFT JOIN pg_index x ON x.indexrelid = i.oid
), event_counts AS (
    SELECT (SELECT count(*) FROM compatibility_evidence_event) AS compatibility_rows,
           (SELECT count(*) FROM map_download_event) AS map_rows,
           (SELECT count(*) FROM map_download_event WHERE map_result_index IS NULL) AS null_map_index_rows,
           (SELECT count(*) FROM map_download_event WHERE map_result_index IS NOT NULL) AS nonnull_map_index_rows,
           (SELECT count(*) FROM statistics_exclusion_audit) AS audit_rows
), checks AS (
    SELECT 'target database/schema/read-only transaction' AS check_name,
           current_database() = 'terento_catalog'
           AND current_schema() = 'public'
           AND current_setting('transaction_read_only') = 'on' AS passed,
           format('database=%s schema=%s read_only=%s', current_database(),
                  current_schema(), current_setting('transaction_read_only')) AS detail
    UNION ALL
    SELECT 'migration 062 applied exactly once and no later version was applied',
           (SELECT count(*) = 1 FROM schema_migrations WHERE version = '062')
           AND (SELECT count(*) = 62 FROM schema_migrations)
           AND NOT EXISTS (
               SELECT 1 FROM expected_versions expected
               WHERE NOT EXISTS (
                   SELECT 1 FROM schema_migrations applied
                   WHERE applied.version = expected.version
               )
           )
           AND NOT EXISTS (
               SELECT 1 FROM schema_migrations
               WHERE version !~ '^[0-9]{3}$'
                  OR CASE WHEN version ~ '^[0-9]{3}$'
                          THEN version::integer NOT BETWEEN 1 AND 62 ELSE true END
           ),
           format('062_rows=%s max_version=%s',
                  (SELECT count(*) FROM schema_migrations WHERE version = '062'),
                  (SELECT max(version) FROM schema_migrations))
    UNION ALL
    SELECT 'all seven columns have nullable/no-default expected types',
           (SELECT expected_column_count = 7 AND mismatch_count = 0 FROM column_state),
           format('expected_columns=%s mismatches=%s',
                  (SELECT expected_column_count FROM column_state),
                  (SELECT mismatch_count FROM column_state))
    UNION ALL
    SELECT 'audit table shape, constraints and indexes are present and valid',
           coalesce((SELECT relkind = 'r' FROM live_audit_table), false)
           AND (SELECT expected_column_count = 8 AND mismatch_count = 0 FROM audit_column_signature)
           AND coalesce((SELECT has_pk AND has_stream_check AND has_unique FROM audit_constraints), false)
           AND (SELECT key_check_count = 3 FROM audit_constraints)
           AND (SELECT count(*) = 5 AND bool_and(present_valid) FROM required_indexes),
           format('plain_table=%s audit_columns=%s column_mismatches=%s pk=%s stream_check=%s unique=%s valid_indexes=%s/5',
                  coalesce((SELECT relkind = 'r' FROM live_audit_table), false),
                  (SELECT expected_column_count FROM audit_column_signature),
                  (SELECT mismatch_count FROM audit_column_signature),
                  coalesce((SELECT has_pk FROM audit_constraints), false),
                  coalesce((SELECT has_stream_check FROM audit_constraints), false),
                  coalesce((SELECT has_unique FROM audit_constraints), false),
                  (SELECT count(*) FROM required_indexes WHERE present_valid))
    UNION ALL
    SELECT 'statistics view retains the exact 29-column contract and exclusion filter',
           coalesce((SELECT relkind = 'v' FROM live_view), false)
           AND (SELECT mismatch_count = 0 AND live_column_count = 29 FROM view_signature)
           AND position('statistics_exclusion_code IS NULL' IN
                        coalesce((SELECT definition FROM live_view), '')) > 0
           AND position('map_result_index' IN coalesce((SELECT definition FROM live_view), '')) > 0,
           format('view_columns=%s signature_mismatches=%s exclusion_filter=%s map_result_index=%s',
                  (SELECT live_column_count FROM view_signature),
                  (SELECT mismatch_count FROM view_signature),
                  position('statistics_exclusion_code IS NULL' IN coalesce((SELECT definition FROM live_view), '')) > 0,
                  position('map_result_index' IN coalesce((SELECT definition FROM live_view), '')) > 0)
    UNION ALL
    SELECT 'event row counts and historical map index match the saved baseline',
           (SELECT compatibility_rows IS NOT NULL AND map_rows IS NOT NULL
                   AND compatibility_rows = (SELECT compatibility_rows FROM baseline)
                   AND map_rows = (SELECT map_rows FROM baseline)
                   AND null_map_index_rows = (SELECT map_rows FROM baseline)
                   AND nonnull_map_index_rows = 0
            FROM event_counts),
           format('compatibility_rows=%s map_rows=%s map_index_null=%s map_index_nonnull=%s',
                  (SELECT compatibility_rows FROM event_counts),
                  (SELECT map_rows FROM event_counts),
                  (SELECT null_map_index_rows FROM event_counts),
                  (SELECT nonnull_map_index_rows FROM event_counts))
    UNION ALL
    SELECT 'new audit table contains no rows',
           (SELECT audit_rows = 0 FROM event_counts),
           format('audit_rows=%s', (SELECT audit_rows FROM event_counts))
)
SELECT CASE WHEN bool_and(passed) THEN 'POSTCHECK PASS 062' ELSE 'ABORT POSTCHECK' END AS gate,
       string_agg(check_name || ': ' || detail, E'\n' ORDER BY check_name) AS checks,
       string_agg(check_name || ': ' || detail, E'\n' ORDER BY check_name)
           FILTER (WHERE NOT passed) AS abort_reasons
FROM checks;

-- Emit the full post-migration view signature for the retained operator record.
SELECT ordinal_position, column_name, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'compatibility_model_statistics'
ORDER BY ordinal_position;

-- SELECT-only gate for a future, separately approved 062 migration.
-- Run inside BEGIN READ ONLY ... ROLLBACK against the exact target database.
-- READY FOR 062 describes schema state only; it does not authorize execution
-- or prove that the selected image/runner will apply only version 062.
WITH expected_versions(version) AS (
    SELECT lpad(value::text, 3, '0')
    FROM generate_series(1, 61) AS versions(value)
),
expected_absent_columns(table_name, column_name) AS (VALUES
    ('compatibility_evidence_event', 'statistics_exclusion_code'),
    ('compatibility_evidence_event', 'statistics_exclusion_reason'),
    ('compatibility_evidence_event', 'security_issue_code'),
    ('map_download_event', 'map_result_index'),
    ('map_download_event', 'statistics_exclusion_code'),
    ('map_download_event', 'statistics_exclusion_reason'),
    ('map_download_event', 'security_issue_code')
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
), checks AS (
    SELECT 'target database/schema/read-only transaction' AS check_name,
           current_database() = 'terento_catalog'
           AND current_schema() = 'public'
           AND current_setting('transaction_read_only') = 'on' AS passed,
           format('database=%s schema=%s read_only=%s', current_database(),
                  current_schema(), current_setting('transaction_read_only')) AS detail
    UNION ALL
    SELECT 'migration ledger has exactly 001-061 and not 062',
           NOT EXISTS (
               SELECT 1 FROM expected_versions expected
               WHERE NOT EXISTS (
                   SELECT 1 FROM schema_migrations applied
                   WHERE applied.version = expected.version
               )
           )
           AND EXISTS (SELECT 1 FROM schema_migrations WHERE version = '060')
           AND EXISTS (SELECT 1 FROM schema_migrations WHERE version = '061')
           AND NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '062')
           AND (SELECT count(*) = 61 FROM schema_migrations)
           AND NOT EXISTS (
               SELECT 1 FROM schema_migrations
               WHERE version !~ '^[0-9]{3}$'
                  OR CASE WHEN version ~ '^[0-9]{3}$'
                          THEN version::integer NOT BETWEEN 1 AND 61 ELSE true END
           ),
           format('applied_count=%s max_version=%s 062_rows=%s',
                  (SELECT count(*) FROM schema_migrations),
                  (SELECT max(version) FROM schema_migrations),
                  (SELECT count(*) FROM schema_migrations WHERE version = '062'))
    UNION ALL
    SELECT 'event tables are ordinary tables',
           coalesce((SELECT relkind = 'r' FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = 'compatibility_evidence_event'), false)
           AND
           coalesce((SELECT relkind = 'r' FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = 'map_download_event'), false),
           'compatibility_evidence_event and map_download_event must exist as tables'
    UNION ALL
    SELECT 'all seven expected-before columns are absent',
           NOT EXISTS (
               SELECT 1
               FROM expected_absent_columns expected
               JOIN information_schema.columns live
                 ON live.table_schema = current_schema()
                AND live.table_name = expected.table_name
                AND live.column_name = expected.column_name
           ),
           'any present column is unexpected drift; stop instead of relying on IF NOT EXISTS'
    UNION ALL
    SELECT 'audit relation name is free',
           NOT EXISTS (
               SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = current_schema() AND c.relname = 'statistics_exclusion_audit'
           ),
           'statistics_exclusion_audit must not exist as any relation kind'
    UNION ALL
    SELECT 'audit composite type name is free',
           NOT EXISTS (
               SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
               WHERE n.nspname = current_schema() AND t.typname = 'statistics_exclusion_audit'
           ),
           'an orphan type with the target table name could conflict with CREATE TABLE'
    UNION ALL
    SELECT 'five expected index names are free',
           NOT EXISTS (
               SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = current_schema()
                 AND c.relname IN (
                     'compatibility_statistics_exclusion_idx',
                     'map_statistics_exclusion_idx',
                     'statistics_exclusion_audit_pkey',
                     'statistics_exclusion_audit_stream_event_id_exclusion_code_key',
                     'statistics_exclusion_audit_event_idx'
                 )
           ),
           'same-named indexes/relations can cause CREATE INDEX IF NOT EXISTS to skip; all must be absent'
    UNION ALL
    SELECT 'current statistics view is the expected pre-062 view',
           coalesce((SELECT relkind = 'v' FROM live_view), false)
           AND (SELECT mismatch_count = 0 AND live_column_count = 29 FROM view_signature)
           AND position('map_result_index' IN coalesce((SELECT definition FROM live_view), '')) > 0
           AND position('statistics_exclusion_code' IN coalesce((SELECT definition FROM live_view), '')) = 0,
           format('view_columns=%s signature_mismatches=%s result_marker=%s exclusion_marker=%s',
                  (SELECT live_column_count FROM view_signature),
                  (SELECT mismatch_count FROM view_signature),
                  position('map_result_index' IN coalesce((SELECT definition FROM live_view), '')) > 0,
                  position('statistics_exclusion_code' IN coalesce((SELECT definition FROM live_view), '')) > 0)
)
SELECT CASE WHEN bool_and(passed) THEN 'READY FOR 062' ELSE 'ABORT 062' END AS gate,
       string_agg(check_name || ': ' || detail, E'\n' ORDER BY check_name) AS checks,
       string_agg(check_name || ': ' || detail, E'\n' ORDER BY check_name)
           FILTER (WHERE NOT passed) AS abort_reasons
FROM checks;

-- Record exact event counts before the migration. Since the precheck above
-- requires map_result_index to be absent, every current map row is expected to
-- receive NULL when that nullable/no-default column is added. Exact equality
-- with postcheck counts also requires no event ingestion/retention writes in
-- the measurement window; otherwise explain and reconcile the delta.
SELECT current_database() AS database_name,
       current_schema() AS schema_name,
       (SELECT count(*) FROM compatibility_evidence_event) AS compatibility_event_rows_before,
       (SELECT count(*) FROM map_download_event) AS map_event_rows_before,
       (SELECT count(*) FROM map_download_event) AS historical_map_rows_expected_null,
       (SELECT md5(pg_get_viewdef(c.oid, true))
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relname = 'compatibility_model_statistics') AS view_definition_md5_before,
       current_setting('server_version') AS server_version,
       current_setting('server_version_num') AS server_version_num,
       current_setting('search_path') AS search_path,
       current_setting('transaction_read_only') AS transaction_read_only;

-- Emit the complete view output contract to retain as the pre-migration
-- snapshot. The first SELECT's gate already checks these 29 names/order/types.
SELECT ordinal_position, column_name, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'compatibility_model_statistics'
ORDER BY ordinal_position;

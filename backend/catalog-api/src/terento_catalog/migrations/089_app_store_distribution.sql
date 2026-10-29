-- 089: tell App Store builds apart from the directly downloaded app.
--
-- The Mac App Store build sends its SemVer release label with the `appstore`
-- build-metadata identifier (`1.1.0+appstore`); the directly downloaded app
-- never does, and the app keeps a `-local` test label without it, so local
-- tests stay local tests. This one IMMUTABLE function is the App Store rule of
-- every Admin read model (contracts/STATISTICS_CONTRACT.md, App and App Store).
--
-- Additive and rollback-compatible: a new function and a CREATE OR REPLACE of
-- compatibility_model_statistics that keeps the 29 columns of 069 unchanged
-- and in order and appends the App Store part and the per-part latest times.
-- The previous API revision selects the old columns and ignores the new ones.
CREATE OR REPLACE FUNCTION terento_is_app_store_release(release_label TEXT)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS 'SELECT COALESCE(
    release_label ~ ''^[^+]+[+]([0-9A-Za-z-]+[.])*appstore([.][0-9A-Za-z-]+)*$'', false)';

-- Same population as 069; result_stats marks an App Store map result, and the
-- appended columns count that part. The directly downloaded app part is the
-- total minus the App Store part.
CREATE OR REPLACE VIEW compatibility_model_statistics AS
WITH normalized_events AS (
    SELECT
        e.*,
        CASE WHEN e.identity_assessment IS NOT NULL AND e.canonical_device_model_id IS NULL
             THEN 'unresolved:' || e.compatibility_identity
             ELSE COALESCE(e.canonical_device_model_id, 'identity:' || e.compatibility_identity) END AS aggregate_key,
        CASE
            WHEN e.operation_id IS NOT NULL AND e.map_result_index IS NOT NULL
                THEN e.operation_id::text || ':' || e.map_result_index::text
            ELSE 'event:' || e.event_id::text
        END AS result_key,
        terento_fresh_result_classification(
            e.phase_outcome, e.automatic_finishing_result, e.write_started,
            e.schema_version, e.app_build, e.release_label
        ) AS result_classification
    FROM compatibility_evidence_event e
    WHERE TRUE
      AND e.is_local_test IS NOT TRUE
      AND e.statistics_exclusion_code IS NULL
), logical_conflicts AS (
    SELECT result_key,
           count(DISTINCT (aggregate_key, provider, region, result_classification)) > 1 AS conflicting
    FROM normalized_events GROUP BY result_key
), result_stats AS (
    SELECT
        e.aggregate_key,
        e.result_key,
        min(e.compatibility_identity) AS compatibility_identity,
        min(e.model) AS model,
        min(e.variant) FILTER (WHERE e.variant IS NOT NULL AND btrim(e.variant) <> '') AS variant,
        min(e.case_size_mm) FILTER (WHERE e.case_size_mm IS NOT NULL) AS case_size_mm,
        min(e.display_type) FILTER (WHERE e.display_type IS NOT NULL AND btrim(e.display_type) <> '') AS display_type,
        min(e.canonical_device_model_id) FILTER (WHERE e.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        bool_and(e.identity_assessment IS NULL) AS legacy_allowed,
        bool_or(e.result_classification = 'SUCCESS') AS result_succeeded,
        bool_or(e.result_classification = 'FAILURE') AS result_failed,
        bool_or(c.conflicting) AS result_conflict,
        bool_or(e.reconnect_verified) FILTER (WHERE e.result_classification = 'SUCCESS') AS reconnect_verified,
        min(NULLIF(e.firmware_version, '')) FILTER (WHERE e.result_classification = 'SUCCESS') AS successful_firmware_version,
        min(e.occurred_at) AS occurred_at,
        1::numeric AS map_result_count,
        CASE WHEN bool_or(e.result_classification = 'SUCCESS') THEN 1::numeric ELSE 0::numeric END AS successful_map_result_count,
        CASE WHEN bool_or(e.result_classification = 'FAILURE') THEN 1::numeric ELSE 0::numeric END AS failed_map_result_count,
        CASE WHEN bool_or(e.result_classification = 'NOT_STARTED') THEN 1::numeric ELSE 0::numeric END AS not_started_map_result_count,
        CASE WHEN bool_or(e.phase_outcome = 'FAILED' AND e.result_classification <> 'FAILURE') THEN 1::numeric ELSE 0::numeric END AS prewrite_failure_count,
        bool_or(terento_is_app_store_release(e.release_label)) AS app_store_result
    FROM normalized_events e
    JOIN logical_conflicts c USING (result_key)
    GROUP BY e.aggregate_key, e.result_key
), event_stats AS (
    SELECT
        o.aggregate_key,
        bool_and(o.legacy_allowed) AS legacy_allowed,
        min(o.compatibility_identity) AS compatibility_identity,
        min(o.model) AS model,
        min(o.variant) FILTER (WHERE o.variant IS NOT NULL) AS variant,
        min(o.case_size_mm) FILTER (WHERE o.case_size_mm IS NOT NULL) AS case_size_mm,
        min(o.display_type) FILTER (WHERE o.display_type IS NOT NULL) AS display_type,
        min(o.canonical_device_model_id) FILTER (WHERE o.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        string_agg(DISTINCT COALESCE(o.successful_firmware_version, 'unknown'), ', ' ORDER BY COALESCE(o.successful_firmware_version, 'unknown')) AS firmware_versions,
        count(*) FILTER (WHERE (o.result_succeeded OR o.result_failed) AND NOT o.result_conflict) AS attempted_install_count,
        count(*) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict) AS successful_install_count,
        count(*) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict AND o.reconnect_verified) AS reconnect_verified_install_count,
        count(*) FILTER (WHERE o.result_failed AND NOT o.result_conflict) AS failed_install_count,
        count(DISTINCT o.successful_firmware_version) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict) AS firmware_version_count,
        round(100.0 * count(*) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict)
            / NULLIF(count(*) FILTER (WHERE (o.result_succeeded OR o.result_failed) AND NOT o.result_conflict), 0), 1) AS success_rate,
        max(o.occurred_at) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict) AS last_success,
        max(o.occurred_at) FILTER (WHERE o.result_failed AND NOT o.result_conflict) AS last_failure,
        max(o.occurred_at) AS last_evidence,
        sum(o.map_result_count) AS map_result_count,
        sum(o.successful_map_result_count) AS successful_map_result_count,
        sum(o.failed_map_result_count) AS failed_map_result_count,
        sum(o.not_started_map_result_count) AS not_started_map_result_count,
        sum(o.prewrite_failure_count)::bigint AS prewrite_failure_count,
        count(*) FILTER (WHERE (o.result_succeeded OR o.result_failed) AND NOT o.result_conflict AND o.app_store_result) AS app_store_attempted_install_count,
        count(*) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict AND o.app_store_result) AS app_store_successful_install_count,
        count(*) FILTER (WHERE o.result_failed AND NOT o.result_conflict AND o.app_store_result) AS app_store_failed_install_count,
        COALESCE(sum(o.prewrite_failure_count) FILTER (WHERE o.app_store_result), 0)::bigint AS app_store_prewrite_failure_count,
        max(o.occurred_at) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict AND o.app_store_result) AS app_store_last_success,
        max(o.occurred_at) FILTER (WHERE o.result_failed AND NOT o.result_conflict AND o.app_store_result) AS app_store_last_failure,
        max(o.occurred_at) FILTER (WHERE o.app_store_result) AS app_store_last_evidence,
        max(o.occurred_at) FILTER (WHERE o.result_succeeded AND NOT o.result_conflict AND NOT o.app_store_result) AS direct_last_success,
        max(o.occurred_at) FILTER (WHERE o.result_failed AND NOT o.result_conflict AND NOT o.app_store_result) AS direct_last_failure,
        max(o.occurred_at) FILTER (WHERE NOT o.app_store_result) AS direct_last_evidence
    FROM result_stats o
    GROUP BY o.aggregate_key
), error_stats AS (
    SELECT
        e.aggregate_key,
        jsonb_object_agg(e.error_key, e.error_count) AS error_categories
    FROM (
        SELECT
            n.aggregate_key,
            COALESCE(n.failure_stage || ':' || n.failure_code, n.error_category, 'unknown') AS error_key,
            count(*) AS error_count
        FROM normalized_events n
        WHERE n.phase_outcome = 'FAILED'
        GROUP BY n.aggregate_key, COALESCE(n.failure_stage || ':' || n.failure_code, n.error_category, 'unknown')
    ) e
    GROUP BY e.aggregate_key
)
SELECT
    COALESCE(NULLIF(r.identity_key, ''), e.compatibility_identity) AS compatibility_identity,
    e.model, e.variant, e.case_size_mm, e.display_type, e.canonical_device_model_id,
    e.firmware_versions, e.attempted_install_count, e.successful_install_count,
    e.reconnect_verified_install_count, e.failed_install_count, e.firmware_version_count,
    e.success_rate, e.last_success, e.last_failure, e.last_evidence,
    e.map_result_count, e.successful_map_result_count, e.failed_map_result_count,
    e.not_started_map_result_count, e.prewrite_failure_count,
    COALESCE(errors.error_categories, '{}'::jsonb) AS error_categories,
    terento_compatibility_status(e.successful_install_count, dm.map_capable IS TRUE) AS calculated_status,
    (dm.map_capable IS TRUE) AS recognized_map_capable_evidence,
    COALESCE(r.physical_device_evidence_count, 0) AS physical_device_evidence_count,
    COALESCE(r.review_notes, '') AS review_notes,
    COALESCE(r.review_status, 'PENDING') AS review_status,
    (COALESCE(r.public_statistics_enabled, false) AND (e.canonical_device_model_id IS NOT NULL OR e.legacy_allowed)) AS public_statistics_enabled,
    COALESCE(NULLIF(r.public_display_name, ''), NULLIF(r.identity_key, ''), e.compatibility_identity) AS public_display_name,
    e.app_store_attempted_install_count, e.app_store_successful_install_count,
    e.app_store_failed_install_count, e.app_store_prewrite_failure_count,
    e.app_store_last_success, e.app_store_last_failure, e.app_store_last_evidence,
    e.direct_last_success, e.direct_last_failure, e.direct_last_evidence
FROM event_stats e
LEFT JOIN error_stats errors ON errors.aggregate_key = e.aggregate_key
LEFT JOIN device_model dm ON dm.id = e.canonical_device_model_id
LEFT JOIN LATERAL (
    SELECT review.*
    FROM compatibility_model_review review
    WHERE COALESCE(NULLIF(review.identity_key, ''), review.model) = e.compatibility_identity
       OR (
            e.canonical_device_model_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM compatibility_evidence_event linked_event
                WHERE linked_event.canonical_device_model_id = e.canonical_device_model_id
                  AND linked_event.compatibility_identity = COALESCE(NULLIF(review.identity_key, ''), review.model)
                  AND linked_event.is_local_test IS NOT TRUE
                  AND linked_event.statistics_exclusion_code IS NULL
            )
       )
    ORDER BY
        (COALESCE(NULLIF(review.identity_key, ''), review.model) = e.compatibility_identity) DESC,
        (review.review_status = 'APPROVED') DESC,
        review.updated_at DESC
    LIMIT 1
) r ON true;

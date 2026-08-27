-- Keep diagnostic lifecycle separate from installation statistics. Resolved
-- and legacy evidence remains part of the aggregate history; lifecycle state
-- only controls whether an item needs operator attention.

UPDATE compatibility_evidence_event
SET resolution_note = 'Historical pre-beta.6 failure; retained in all compatibility counts and rates.'
WHERE resolution_code = 'LEGACY_PRE_BETA6'
  AND resolution_note = 'Historical pre-beta.6 failure; excluded from current compatibility statistics.';

DROP VIEW compatibility_model_statistics;

CREATE VIEW compatibility_model_statistics AS
WITH normalized_events AS (
    SELECT
        e.*,
        COALESCE(e.canonical_device_model_id, 'identity:' || e.compatibility_identity) AS aggregate_key,
        COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text) AS operation_key,
        COALESCE(e.write_started, true) AS compatibility_write_started
    FROM compatibility_evidence_event e
),
operation_stats AS (
    SELECT
        e.aggregate_key,
        e.operation_key,
        min(e.compatibility_identity) AS compatibility_identity,
        min(e.model) AS model,
        min(e.variant) FILTER (WHERE e.variant IS NOT NULL AND btrim(e.variant) <> '') AS variant,
        min(e.case_size_mm) FILTER (WHERE e.case_size_mm IS NOT NULL) AS case_size_mm,
        min(e.display_type) FILTER (WHERE e.display_type IS NOT NULL AND btrim(e.display_type) <> '') AS display_type,
        min(e.canonical_device_model_id) FILTER (WHERE e.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        bool_or(e.compatibility_write_started) AS write_started,
        bool_and(e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED')
            AND count(*) = max(COALESCE(e.selected_map_count, 1)) AS operation_succeeded,
        bool_or(e.reconnect_verified) AS reconnect_verified,
        min(NULLIF(e.firmware_version, '')) AS successful_firmware_version,
        min(e.occurred_at) AS occurred_at,
        count(*) AS map_result_count,
        count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS successful_map_result_count,
        count(*) FILTER (WHERE e.phase_outcome = 'FAILED') AS failed_map_result_count,
        count(*) FILTER (WHERE e.phase_outcome = 'NOT_STARTED') AS not_started_map_result_count
    FROM normalized_events e
    GROUP BY e.aggregate_key, e.operation_key
),
event_stats AS (
    SELECT
        o.aggregate_key,
        min(o.compatibility_identity) AS compatibility_identity,
        min(o.model) AS model,
        min(o.variant) FILTER (WHERE o.variant IS NOT NULL) AS variant,
        min(o.case_size_mm) FILTER (WHERE o.case_size_mm IS NOT NULL) AS case_size_mm,
        min(o.display_type) FILTER (WHERE o.display_type IS NOT NULL) AS display_type,
        min(o.canonical_device_model_id) FILTER (WHERE o.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        string_agg(DISTINCT COALESCE(o.successful_firmware_version, 'unknown'), ', ' ORDER BY COALESCE(o.successful_firmware_version, 'unknown')) AS firmware_versions,
        count(*) AS attempted_install_count,
        count(*) FILTER (WHERE o.operation_succeeded) AS successful_install_count,
        count(*) FILTER (WHERE o.operation_succeeded AND o.reconnect_verified) AS reconnect_verified_install_count,
        count(*) FILTER (WHERE NOT o.operation_succeeded) AS failed_install_count,
        count(DISTINCT o.successful_firmware_version) FILTER (WHERE o.operation_succeeded) AS firmware_version_count,
        round(100.0 * count(*) FILTER (WHERE o.operation_succeeded)
            / NULLIF(count(*), 0), 1) AS success_rate,
        max(o.occurred_at) FILTER (WHERE o.operation_succeeded) AS last_success,
        max(o.occurred_at) FILTER (WHERE NOT o.operation_succeeded) AS last_failure,
        max(o.occurred_at) AS last_evidence,
        sum(o.map_result_count) AS map_result_count,
        sum(o.successful_map_result_count) AS successful_map_result_count,
        sum(o.failed_map_result_count) AS failed_map_result_count,
        sum(o.not_started_map_result_count) AS not_started_map_result_count,
        count(*) FILTER (WHERE NOT o.write_started) AS prewrite_failure_count
    FROM operation_stats o
    GROUP BY o.aggregate_key
),
error_stats AS (
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
    COALESCE(r.public_statistics_enabled, false) AS public_statistics_enabled,
    COALESCE(NULLIF(r.public_display_name, ''), NULLIF(r.identity_key, ''), e.compatibility_identity) AS public_display_name
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
            )
       )
    ORDER BY
        (COALESCE(NULLIF(review.identity_key, ''), review.model) = e.compatibility_identity) DESC,
        (review.review_status = 'APPROVED') DESC,
        review.updated_at DESC
    LIMIT 1
) r ON true;

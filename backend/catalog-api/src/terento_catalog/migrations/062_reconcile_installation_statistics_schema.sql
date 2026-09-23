-- Reconcile the schema drift confirmed by the complete read-only live audit.
-- Versions 060 and 061 are recorded in production, but their original SQL is
-- unavailable; do not replay or rewrite them. Keep all event rows untouched.
-- In particular, adding map_result_index without a default leaves historical
-- map-download events NULL rather than guessing their result correlation.
ALTER TABLE compatibility_evidence_event
    ADD COLUMN IF NOT EXISTS statistics_exclusion_code TEXT,
    ADD COLUMN IF NOT EXISTS statistics_exclusion_reason TEXT,
    ADD COLUMN IF NOT EXISTS security_issue_code TEXT;

ALTER TABLE map_download_event
    ADD COLUMN IF NOT EXISTS statistics_exclusion_code TEXT,
    ADD COLUMN IF NOT EXISTS statistics_exclusion_reason TEXT,
    ADD COLUMN IF NOT EXISTS security_issue_code TEXT,
    ADD COLUMN IF NOT EXISTS map_result_index INTEGER;

CREATE TABLE IF NOT EXISTS statistics_exclusion_audit (
    id BIGSERIAL PRIMARY KEY,
    stream TEXT NOT NULL CHECK (stream IN ('compatibility', 'map')),
    event_id UUID NOT NULL,
    exclusion_code TEXT NOT NULL,
    reason TEXT NOT NULL,
    security_issue_code TEXT,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (stream, event_id, exclusion_code)
);

CREATE INDEX IF NOT EXISTS compatibility_statistics_exclusion_idx
    ON compatibility_evidence_event(statistics_exclusion_code, occurred_at DESC);
CREATE INDEX IF NOT EXISTS map_statistics_exclusion_idx
    ON map_download_event(statistics_exclusion_code, occurred_at DESC);
CREATE INDEX IF NOT EXISTS statistics_exclusion_audit_event_idx
    ON statistics_exclusion_audit(stream, event_id, created_at DESC);

-- Keep the public/admin projection's established output names, order, and
-- PostgreSQL types. This is the complete local 060 definition, including its
-- result-index and local-test semantics, with exclusion filtering applied.
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
        CASE
            WHEN e.phase_outcome = 'SUCCEEDED'
                 AND e.automatic_finishing_result = 'VERIFIED'
                THEN 'SUCCESS'
            WHEN e.phase_outcome = 'FAILED'
                 AND (e.write_started IS TRUE OR (
                     e.write_started IS NULL
                     AND e.app_build IS NULL
                     AND e.release_label IS NULL
                 ))
                THEN 'FAILURE'
            WHEN e.phase_outcome IN ('FAILED', 'NOT_STARTED')
                 AND e.write_started IS FALSE
                THEN 'NOT_STARTED'
            ELSE 'UNKNOWN'
        END AS result_classification
    FROM compatibility_evidence_event e
    WHERE (e.diagnostic_status = 'ACTIVE' OR e.phase_outcome = 'FAILED')
      AND e.is_local_test IS NOT TRUE
      AND e.statistics_exclusion_code IS NULL
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
        count(DISTINCT e.result_classification) > 1 AS result_conflict,
        bool_or(e.reconnect_verified) FILTER (WHERE e.result_classification = 'SUCCESS') AS reconnect_verified,
        min(NULLIF(e.firmware_version, '')) FILTER (WHERE e.result_classification = 'SUCCESS') AS successful_firmware_version,
        max(e.occurred_at) AS occurred_at,
        1::numeric AS map_result_count,
        CASE WHEN bool_or(e.result_classification = 'SUCCESS') THEN 1::numeric ELSE 0::numeric END AS successful_map_result_count,
        CASE WHEN bool_or(e.result_classification = 'FAILURE') THEN 1::numeric ELSE 0::numeric END AS failed_map_result_count,
        CASE WHEN bool_or(e.result_classification = 'NOT_STARTED') THEN 1::numeric ELSE 0::numeric END AS not_started_map_result_count,
        CASE WHEN bool_or(e.phase_outcome = 'FAILED' AND e.result_classification <> 'FAILURE') THEN 1::numeric ELSE 0::numeric END AS prewrite_failure_count
    FROM normalized_events e
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
        sum(o.prewrite_failure_count)::bigint AS prewrite_failure_count
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

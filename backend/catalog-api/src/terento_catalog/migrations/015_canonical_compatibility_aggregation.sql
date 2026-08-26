-- Aggregate compatibility evidence by the exact canonical Garmin catalog
-- record whenever the client supplied one. Textual compatibilityIdentity is
-- retained only as the backward-compatible key for older uncanonicalized
-- events. This prevents formatting changes between app versions from creating
-- duplicate rows for the same physical model variant.

-- Correct the exact beta.6 payload shape observed during the owner test. The
-- map-capable 47 mm AMOLED identity, size, VID and PID make this deterministic;
-- 51 mm and any future Solar record cannot satisfy the predicate.
UPDATE compatibility_evidence_event
SET
    compatibility_identity = 'fēnix 8 · 47 mm AMOLED',
    display_type = 'AMOLED',
    canonical_device_model_id = 'garmin-fenix-8-47-amoled'
WHERE canonical_device_model_id IS NULL
  AND model = 'fēnix 8'
  AND compatibility_identity = 'fēnix 8 · 47 mm, AMOLED'
  AND variant = '47 mm, AMOLED'
  AND case_size_mm = 47
  AND usb_vendor_id = 2334
  AND usb_product_id = 20920;

DROP VIEW compatibility_model_statistics;

CREATE VIEW compatibility_model_statistics AS
WITH normalized_events AS (
    SELECT
        e.*,
        COALESCE(
            e.canonical_device_model_id,
            'identity:' || e.compatibility_identity
        ) AS aggregate_key
    FROM compatibility_evidence_event e
),
event_stats AS (
    SELECT
        e.aggregate_key,
        min(e.compatibility_identity) AS compatibility_identity,
        min(e.model) AS model,
        min(e.variant) FILTER (WHERE e.variant IS NOT NULL AND btrim(e.variant) <> '') AS variant,
        min(e.case_size_mm) FILTER (WHERE e.case_size_mm IS NOT NULL) AS case_size_mm,
        min(e.display_type) FILTER (WHERE e.display_type IS NOT NULL AND btrim(e.display_type) <> '') AS display_type,
        min(e.canonical_device_model_id) FILTER (WHERE e.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        string_agg(DISTINCT COALESCE(NULLIF(e.firmware_version, ''), 'unknown'), ', ' ORDER BY COALESCE(NULLIF(e.firmware_version, ''), 'unknown')) AS firmware_versions,
        count(*) AS attempted_install_count,
        count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS successful_install_count,
        count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED' AND e.reconnect_verified) AS reconnect_verified_install_count,
        count(*) FILTER (WHERE e.phase_outcome = 'FAILED') AS failed_install_count,
        count(DISTINCT NULLIF(e.firmware_version, '')) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS firmware_version_count,
        round(100.0 * count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') / NULLIF(count(*), 0), 1) AS success_rate,
        max(e.occurred_at) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS last_success,
        max(e.occurred_at) FILTER (WHERE e.phase_outcome = 'FAILED') AS last_failure,
        max(e.occurred_at) AS last_evidence
    FROM normalized_events e
    GROUP BY e.aggregate_key
),
error_stats AS (
    SELECT
        category_counts.aggregate_key,
        jsonb_object_agg(
            COALESCE(category_counts.error_category, 'unknown'),
            category_counts.category_count
        ) AS error_categories
    FROM (
        SELECT
            e.aggregate_key,
            e.error_category,
            count(*) AS category_count
        FROM normalized_events e
        WHERE e.phase_outcome = 'FAILED'
        GROUP BY e.aggregate_key, e.error_category
    ) category_counts
    GROUP BY category_counts.aggregate_key
)
SELECT
    COALESCE(NULLIF(r.identity_key, ''), e.compatibility_identity) AS compatibility_identity,
    e.model,
    e.variant,
    e.case_size_mm,
    e.display_type,
    e.canonical_device_model_id,
    e.firmware_versions,
    e.attempted_install_count,
    e.successful_install_count,
    e.reconnect_verified_install_count,
    e.failed_install_count,
    e.firmware_version_count,
    e.success_rate,
    e.last_success,
    e.last_failure,
    e.last_evidence,
    COALESCE(errors.error_categories, '{}'::jsonb) AS error_categories,
    CASE
        WHEN e.successful_install_count = 0 THEN 'TESTING'
        WHEN e.successful_install_count < 3 THEN 'TESTED'
        WHEN e.successful_install_count < 5 THEN 'SUPPORTED'
        ELSE 'VERIFIED'
    END AS calculated_status,
    true AS recognized_map_capable_evidence,
    COALESCE(r.physical_device_evidence_count, 0) AS physical_device_evidence_count,
    COALESCE(r.review_notes, '') AS review_notes,
    COALESCE(r.review_status, 'PENDING') AS review_status,
    COALESCE(r.public_statistics_enabled, false) AS public_statistics_enabled,
    COALESCE(NULLIF(r.public_display_name, ''), NULLIF(r.identity_key, ''), e.compatibility_identity) AS public_display_name
FROM event_stats e
LEFT JOIN error_stats errors
    ON errors.aggregate_key = e.aggregate_key
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
                  AND linked_event.compatibility_identity = COALESCE(
                      NULLIF(review.identity_key, ''),
                      review.model
                  )
            )
       )
    ORDER BY
        (COALESCE(NULLIF(review.identity_key, ''), review.model) = e.compatibility_identity) DESC,
        (review.review_status = 'APPROVED') DESC,
        review.updated_at DESC
    LIMIT 1
) r ON true;

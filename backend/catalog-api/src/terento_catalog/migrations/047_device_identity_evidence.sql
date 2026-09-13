-- Additive only: historical assignments and catalog IDs remain unchanged.
ALTER TABLE device_model
    ADD COLUMN screen_technology TEXT CHECK (screen_technology IN ('AMOLED', 'MicroLED', 'MIP')),
    ADD COLUMN solar BOOLEAN,
    ADD COLUMN inreach BOOLEAN,
    ADD COLUMN specification_source TEXT,
    ADD COLUMN specification_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN specification_checked_at TIMESTAMPTZ;

CREATE TABLE device_identity_mapping (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('XML_PART_NUMBER', 'USB', 'RETAIL_SKU')),
    value TEXT NOT NULL,
    device_model_id TEXT NOT NULL REFERENCES device_model(id) ON DELETE RESTRICT,
    source_url TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    reviewed_by BIGINT REFERENCES admin_user(id),
    review_reason TEXT,
    reviewed_at TIMESTAMPTZ,
    UNIQUE (kind, value, device_model_id, source_url, source_version)
);

CREATE TABLE device_identity_mapping_audit (
    id BIGSERIAL PRIMARY KEY,
    mapping_id BIGINT NOT NULL REFERENCES device_identity_mapping(id),
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    reviewed_by BIGINT REFERENCES admin_user(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE compatibility_evidence_event
    ADD COLUMN garmin_model_description TEXT,
    ADD COLUMN garmin_model_part_number TEXT,
    ADD COLUMN identity_assessment JSONB;

-- Corrections are append-only overlays. Original reported data stays intact.
CREATE TABLE device_identity_source_correction (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES compatibility_evidence_event(event_id) ON DELETE CASCADE,
    field TEXT NOT NULL CHECK (field IN ('model','variant','rawMTPModel','garminModelDescription',
        'garminModelPartNumber','caseSizeMm','displayType','usbVendorID','usbProductID')),
    previous_value JSONB,
    corrected_value JSONB,
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000),
    corrected_by BIGINT NOT NULL REFERENCES admin_user(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX device_identity_source_correction_event ON device_identity_source_correction(event_id, id);

-- This is an existing reviewed association, not an inferred new mapping.
INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, status, review_reason, reviewed_at)
SELECT 'USB', lpad(to_hex(vendor_id), 4, '0') || ':' || lpad(to_hex(product_id), 4, '0'),
       device_model_id, 'https://github.com/VooZ2/terento', source, 'APPROVED',
       'Existing reviewed Terento hardware association', now()
FROM device_usb_identity
WHERE source = 'terento-hardware-evidence' AND confidence = 'tested';

INSERT INTO device_identity_mapping_audit (mapping_id,previous_status,new_status,reason)
SELECT id,'PENDING','APPROVED',review_reason FROM device_identity_mapping WHERE status='APPROVED';

-- Preserve every historical aggregate. New unresolved reports remain visible
-- to reviewers but cannot inherit an old text-label publication approval.
CREATE OR REPLACE VIEW compatibility_model_statistics AS
WITH normalized_events AS (
    SELECT
        e.*,
        CASE WHEN e.identity_assessment IS NOT NULL AND e.canonical_device_model_id IS NULL
             THEN 'unresolved:' || e.compatibility_identity
             ELSE COALESCE(e.canonical_device_model_id, 'identity:' || e.compatibility_identity) END AS aggregate_key,
        e.event_id::text AS operation_key,
        (COALESCE(e.write_started, true) OR e.phase_outcome IN ('SUCCEEDED', 'FAILED')) AS compatibility_write_started
    FROM compatibility_evidence_event e
    WHERE (e.diagnostic_status = 'ACTIVE' OR e.phase_outcome = 'FAILED')
      AND e.is_local_test IS NOT TRUE
),
operation_stats AS (
    SELECT
        e.aggregate_key,
        e.operation_key,
        bool_and(e.identity_assessment IS NULL) AS legacy_allowed,
        min(e.compatibility_identity) AS compatibility_identity,
        min(e.model) AS model,
        min(e.variant) FILTER (WHERE e.variant IS NOT NULL AND btrim(e.variant) <> '') AS variant,
        min(e.case_size_mm) FILTER (WHERE e.case_size_mm IS NOT NULL) AS case_size_mm,
        min(e.display_type) FILTER (WHERE e.display_type IS NOT NULL AND btrim(e.display_type) <> '') AS display_type,
        min(e.canonical_device_model_id) FILTER (WHERE e.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        bool_or(e.compatibility_write_started) AS write_started,
        bool_and(e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS operation_succeeded,
        bool_or(e.phase_outcome = 'FAILED') AS result_failed,
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
        bool_and(o.legacy_allowed) AS legacy_allowed,
        min(o.compatibility_identity) AS compatibility_identity,
        min(o.model) AS model,
        min(o.variant) FILTER (WHERE o.variant IS NOT NULL) AS variant,
        min(o.case_size_mm) FILTER (WHERE o.case_size_mm IS NOT NULL) AS case_size_mm,
        min(o.display_type) FILTER (WHERE o.display_type IS NOT NULL) AS display_type,
        min(o.canonical_device_model_id) FILTER (WHERE o.canonical_device_model_id IS NOT NULL) AS canonical_device_model_id,
        string_agg(DISTINCT COALESCE(o.successful_firmware_version, 'unknown'), ', ' ORDER BY COALESCE(o.successful_firmware_version, 'unknown')) AS firmware_versions,
        count(*) FILTER (WHERE o.write_started) AS attempted_install_count,
        count(*) FILTER (WHERE o.write_started AND o.operation_succeeded) AS successful_install_count,
        count(*) FILTER (WHERE o.write_started AND o.operation_succeeded AND o.reconnect_verified) AS reconnect_verified_install_count,
        count(*) FILTER (WHERE o.write_started AND o.result_failed) AS failed_install_count,
        count(DISTINCT o.successful_firmware_version) FILTER (WHERE o.write_started AND o.operation_succeeded) AS firmware_version_count,
        round(100.0 * count(*) FILTER (WHERE o.write_started AND o.operation_succeeded)
            / NULLIF(count(*) FILTER (WHERE o.write_started), 0), 1) AS success_rate,
        max(o.occurred_at) FILTER (WHERE o.write_started AND o.operation_succeeded) AS last_success,
        max(o.occurred_at) FILTER (WHERE o.result_failed) AS last_failure,
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
            )
       )
    ORDER BY
        (COALESCE(NULLIF(review.identity_key, ''), review.model) = e.compatibility_identity) DESC,
        (review.review_status = 'APPROVED') DESC,
        review.updated_at DESC
    LIMIT 1
) r ON true;

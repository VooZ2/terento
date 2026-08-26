-- Canonical admin semantics. This migration is additive to the data model and
-- replaces only the derived compatibility view; public catalog JSON is not
-- changed.

ALTER TABLE compatibility_evidence_event
    ADD COLUMN resolved_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    ADD COLUMN resolution_reason TEXT,
    ADD COLUMN linked_github_issue TEXT;

UPDATE compatibility_evidence_event
SET resolution_reason = resolution_code
WHERE resolution_reason IS NULL
  AND resolution_code IS NOT NULL;

ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_resolution_reason_check
    CHECK (
        resolution_reason IS NULL
        OR resolution_reason IN (
            'FIXED', 'HISTORICAL_SUPERSEDED', 'DUPLICATE',
            'IDENTITY_CORRECTED', 'NOT_TERENTO_ISSUE', 'OTHER',
            'LEGACY_PRE_BETA6'
        )
    );

ALTER TABLE compatibility_evidence_event
    ADD COLUMN identity_resolution_state TEXT NOT NULL DEFAULT 'UNRESOLVED';

ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_identity_state_check
    CHECK (identity_resolution_state IN ('UNRESOLVED', 'RESOLVED', 'NOT_IDENTIFIABLE'));

CREATE TABLE compatibility_diagnostic_lifecycle_audit (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES compatibility_evidence_event(event_id) ON DELETE CASCADE,
    previous_status TEXT NOT NULL CHECK (previous_status IN ('ACTIVE', 'RESOLVED')),
    new_status TEXT NOT NULL CHECK (new_status IN ('ACTIVE', 'RESOLVED')),
    resolution_reason TEXT,
    resolution_note TEXT,
    linked_github_issue TEXT,
    changed_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX compatibility_diagnostic_lifecycle_audit_event_idx
    ON compatibility_diagnostic_lifecycle_audit(event_id, changed_at DESC);

CREATE TABLE compatibility_identity_resolution_audit (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES compatibility_evidence_event(event_id) ON DELETE CASCADE,
    previous_identity TEXT NOT NULL,
    previous_canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE SET NULL,
    new_identity TEXT NOT NULL,
    new_canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE SET NULL,
    action TEXT NOT NULL CHECK (action IN ('ASSIGN', 'LEAVE_UNRESOLVED', 'NOT_IDENTIFIABLE')),
    reason TEXT,
    note TEXT,
    corrected_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    corrected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX compatibility_identity_resolution_audit_event_idx
    ON compatibility_identity_resolution_audit(event_id, corrected_at DESC);

CREATE TABLE device_authorization_audit (
    id BIGSERIAL PRIMARY KEY,
    device_model_id TEXT NOT NULL REFERENCES device_model(id) ON DELETE CASCADE,
    previous_status TEXT NOT NULL CHECK (previous_status IN ('SUPPORTED', 'UNSUPPORTED', 'NOT_EVALUATED')),
    new_status TEXT NOT NULL CHECK (new_status IN ('SUPPORTED', 'UNSUPPORTED', 'NOT_EVALUATED')),
    reason TEXT,
    note TEXT,
    changed_by BIGINT REFERENCES admin_user(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX device_authorization_audit_device_idx
    ON device_authorization_audit(device_model_id, changed_at DESC);

-- Backfill the stored capability for existing catalog rows using the same
-- reviewed prefix families as the native Map Manager registry. New collector
-- rows continue to receive this value from classify_map_capable().
UPDATE device_model
SET map_capable = CASE
    WHEN lower(canonical_model) LIKE ANY (ARRAY[
        'd2 mach 1%', 'd2 mach 2%', 'descent mk1%', 'descent mk2%',
        'descent mk3%', 'enduro 2%', 'enduro 3%', 'epix gen 2%',
        'epix pro gen 2%', 'fenix 5x%', 'fenix 5 plus%', 'fenix 6%',
        'fenix 7%', 'fenix 8%', 'fenix e%', 'forerunner 945%',
        'forerunner 955%', 'forerunner 965%', 'forerunner 970%',
        'marq%', 'quatix 6%', 'quatix 7%', 'quatix 8%',
        'tactix charlie%', 'tactix delta%', 'tactix 7%', 'tactix 8%',
        'venu x1%'
    ]) THEN TRUE
    WHEN lower(canonical_model) LIKE ANY (ARRAY[
        'approach%', 'descent g1%', 'descent g2%', 'forerunner 55%',
        'forerunner 165%', 'forerunner 255%', 'forerunner 265%',
        'forerunner 570%', 'instinct%', 'lily%', 'venu%', 'vivoactive%',
        'vivomove%'
    ]) THEN FALSE
    ELSE map_capable
END
WHERE map_capable IS NULL;

-- PostgreSQL count(*) is BIGINT. Keep the function parameter aligned with the
-- aggregate type so the view can call it without an implicit narrowing cast.
CREATE OR REPLACE FUNCTION terento_compatibility_status(successful_count BIGINT, recognized BOOLEAN)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS 'SELECT CASE
    WHEN recognized IS NOT TRUE THEN NULL
    WHEN successful_count IS NULL THEN NULL
    WHEN successful_count = 0 THEN ''TESTING''
    WHEN successful_count < 3 THEN ''TESTED''
    WHEN successful_count < 5 THEN ''SUPPORTED''
    ELSE ''VERIFIED''
END';

DROP VIEW compatibility_model_statistics;

CREATE VIEW compatibility_model_statistics AS
WITH normalized_events AS (
    SELECT
        e.*,
        COALESCE(e.canonical_device_model_id, 'identity:' || e.compatibility_identity) AS aggregate_key,
        COALESCE(e.operation_id::text, 'legacy:' || e.event_id::text) AS operation_key,
        COALESCE(e.write_started, true) AS compatibility_write_started
    FROM compatibility_evidence_event e
    WHERE e.diagnostic_status = 'ACTIVE'
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
        count(*) FILTER (WHERE o.write_started) AS attempted_install_count,
        count(*) FILTER (WHERE o.write_started AND o.operation_succeeded) AS successful_install_count,
        count(*) FILTER (WHERE o.write_started AND o.operation_succeeded AND o.reconnect_verified) AS reconnect_verified_install_count,
        count(*) FILTER (WHERE o.write_started AND NOT o.operation_succeeded) AS failed_install_count,
        count(DISTINCT o.successful_firmware_version) FILTER (WHERE o.write_started AND o.operation_succeeded) AS firmware_version_count,
        round(100.0 * count(*) FILTER (WHERE o.write_started AND o.operation_succeeded)
            / NULLIF(count(*) FILTER (WHERE o.write_started), 0), 1) AS success_rate,
        max(o.occurred_at) FILTER (WHERE o.write_started AND o.operation_succeeded) AS last_success,
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

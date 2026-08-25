-- Canonical compatibility evidence fields.  Existing events remain valid and
-- deliberately do not gain reconnect evidence retroactively.
ALTER TABLE compatibility_evidence_event
    ADD COLUMN compatibility_identity TEXT,
    ADD COLUMN variant TEXT,
    ADD COLUMN case_size_mm INTEGER CHECK (case_size_mm IS NULL OR case_size_mm BETWEEN 1 AND 999),
    ADD COLUMN reconnect_verified BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN map_visible_after_reconnect BOOLEAN NOT NULL DEFAULT false;

UPDATE compatibility_evidence_event
SET compatibility_identity = model
WHERE compatibility_identity IS NULL OR btrim(compatibility_identity) = '';

ALTER TABLE compatibility_evidence_event
    ALTER COLUMN compatibility_identity SET NOT NULL;

CREATE INDEX compatibility_evidence_identity_idx
    ON compatibility_evidence_event(compatibility_identity);

-- Reviews remain operator-controlled and privacy-safe.  The optional exact
-- identity lets a 47 mm and 51 mm row have independent review evidence while
-- preserving compatibility with older model-only review inserts.
ALTER TABLE compatibility_model_review
    ADD COLUMN identity_key TEXT;

UPDATE compatibility_model_review
SET identity_key = model
WHERE identity_key IS NULL OR btrim(identity_key) = '';

CREATE UNIQUE INDEX compatibility_model_review_identity_idx
    ON compatibility_model_review(identity_key)
    WHERE identity_key IS NOT NULL;

DROP VIEW compatibility_model_statistics;

CREATE VIEW compatibility_model_statistics AS
WITH event_stats AS (
    SELECT
        e.compatibility_identity,
        min(e.model) AS model,
        min(e.variant) FILTER (WHERE e.variant IS NOT NULL AND btrim(e.variant) <> '') AS variant,
        min(e.case_size_mm) FILTER (WHERE e.case_size_mm IS NOT NULL) AS case_size_mm,
        string_agg(DISTINCT COALESCE(NULLIF(e.firmware_version, ''), 'unknown'), ', ' ORDER BY COALESCE(NULLIF(e.firmware_version, ''), 'unknown')) AS firmware_versions,
        count(*) AS attempted_install_count,
        count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS successful_install_count,
        count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED' AND e.reconnect_verified) AS reconnect_verified_install_count,
        count(*) FILTER (WHERE e.phase_outcome = 'FAILED') AS failed_install_count,
        count(DISTINCT NULLIF(e.firmware_version, '')) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS firmware_version_count,
        round(100.0 * count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') / NULLIF(count(*), 0), 1) AS success_rate,
        max(e.occurred_at) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS last_success,
        max(e.occurred_at) FILTER (WHERE e.phase_outcome = 'FAILED') AS last_failure,
        COALESCE((
            SELECT jsonb_object_agg(COALESCE(category, 'unknown'), category_count)
            FROM (
                SELECT x.error_category AS category, count(*) AS category_count
                FROM compatibility_evidence_event x
                WHERE x.compatibility_identity = e.compatibility_identity
                  AND x.phase_outcome = 'FAILED'
                GROUP BY x.error_category
            ) category_counts
        ), '{}'::jsonb) AS error_categories
    FROM compatibility_evidence_event e
    GROUP BY e.compatibility_identity
)
SELECT
    e.compatibility_identity,
    e.model,
    e.variant,
    e.case_size_mm,
    e.firmware_versions,
    e.attempted_install_count,
    e.successful_install_count,
    e.reconnect_verified_install_count,
    e.failed_install_count,
    e.firmware_version_count,
    e.success_rate,
    e.last_success,
    e.last_failure,
    e.error_categories,
    CASE
        WHEN e.successful_install_count > 0
             AND COALESCE(r.physical_device_evidence_count, 0) >= 2
             AND e.firmware_version_count >= 2 THEN 'VERIFIED'
        WHEN e.successful_install_count > 0 THEN 'SUPPORTED'
        ELSE 'TESTING'
    END AS calculated_status,
    COALESCE(r.physical_device_evidence_count, 0) AS physical_device_evidence_count,
    COALESCE(r.review_notes, '') AS review_notes,
    COALESCE(r.review_status, 'PENDING') AS review_status,
    COALESCE(r.public_statistics_enabled, false) AS public_statistics_enabled,
    COALESCE(NULLIF(r.public_display_name, ''), e.compatibility_identity) AS public_display_name
FROM event_stats e
LEFT JOIN compatibility_model_review r
    ON COALESCE(NULLIF(r.identity_key, ''), r.model) = e.compatibility_identity;

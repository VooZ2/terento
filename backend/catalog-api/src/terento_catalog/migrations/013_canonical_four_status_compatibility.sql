-- Canonical compatibility identity and status rollout.
--
-- The four event IDs below are the complete historical production evidence
-- set confirmed by the operator on 2026-08-25. This is an auditable one-time
-- data correction, not model matching or classifier behavior. Original
-- identity values remain in compatibility_evidence_identity_correction.

ALTER TABLE compatibility_evidence_event
    ADD COLUMN canonical_device_model_id TEXT REFERENCES device_model(id) ON DELETE RESTRICT,
    ADD COLUMN display_type TEXT;

CREATE TABLE compatibility_evidence_identity_correction (
    event_id UUID PRIMARY KEY REFERENCES compatibility_evidence_event(event_id) ON DELETE CASCADE,
    corrected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    correction_reason TEXT NOT NULL CHECK (
        correction_reason = 'operator-confirmed historical evidence correction'
    ),
    original_model TEXT NOT NULL,
    original_compatibility_identity TEXT NOT NULL,
    original_variant TEXT,
    original_case_size_mm INTEGER,
    corrected_model TEXT NOT NULL,
    corrected_compatibility_identity TEXT NOT NULL,
    corrected_variant TEXT NOT NULL,
    corrected_case_size_mm INTEGER NOT NULL,
    corrected_display_type TEXT NOT NULL,
    canonical_device_model_id TEXT NOT NULL REFERENCES device_model(id) ON DELETE RESTRICT
);

INSERT INTO compatibility_evidence_identity_correction (
    event_id,
    correction_reason,
    original_model,
    original_compatibility_identity,
    original_variant,
    original_case_size_mm,
    corrected_model,
    corrected_compatibility_identity,
    corrected_variant,
    corrected_case_size_mm,
    corrected_display_type,
    canonical_device_model_id
)
SELECT
    e.event_id,
    'operator-confirmed historical evidence correction',
    e.model,
    e.compatibility_identity,
    e.variant,
    e.case_size_mm,
    correction.corrected_model,
    correction.corrected_compatibility_identity,
    correction.corrected_variant,
    correction.corrected_case_size_mm,
    correction.corrected_display_type,
    correction.canonical_device_model_id
FROM compatibility_evidence_event AS e
JOIN (
    VALUES
        ('a3585d10-07b6-4c07-85f3-6c35d83c553d'::uuid, 'fēnix 8', 'fēnix 8 · 47 mm AMOLED', 'AMOLED', 47, 'AMOLED', 'garmin-fenix-8-47-amoled'),
        ('3c6f116e-5b72-49e8-8e13-e7fe1f63ae4f'::uuid, 'fēnix 8', 'fēnix 8 · 47 mm AMOLED', 'AMOLED', 47, 'AMOLED', 'garmin-fenix-8-47-amoled'),
        ('aab03f02-5294-42e9-822d-0d7de878cdb1'::uuid, 'fēnix 8', 'fēnix 8 · 47 mm AMOLED', 'AMOLED', 47, 'AMOLED', 'garmin-fenix-8-47-amoled'),
        ('a41a4b6b-cfb9-487d-beeb-339cacedbd30'::uuid, 'fēnix 8', 'fēnix 8 · 51 mm AMOLED', 'AMOLED', 51, 'AMOLED', 'garmin-fenix-8-51-amoled')
) AS correction(
    event_id,
    corrected_model,
    corrected_compatibility_identity,
    corrected_variant,
    corrected_case_size_mm,
    corrected_display_type,
    canonical_device_model_id
) ON correction.event_id = e.event_id
WHERE e.phase_outcome = 'SUCCEEDED'
  AND e.automatic_finishing_result = 'VERIFIED'
  AND e.variant IS NULL
  AND e.case_size_mm IS NULL
  AND (
      (
          e.event_id IN (
              'a3585d10-07b6-4c07-85f3-6c35d83c553d'::uuid,
              '3c6f116e-5b72-49e8-8e13-e7fe1f63ae4f'::uuid,
              'aab03f02-5294-42e9-822d-0d7de878cdb1'::uuid
          )
          AND e.model = 'fēnix 8'
          AND e.compatibility_identity = 'fēnix 8'
      )
      OR (
          e.event_id = 'a41a4b6b-cfb9-487d-beeb-339cacedbd30'::uuid
          AND e.model = 'fenix 8 - 51mm'
          AND e.compatibility_identity = 'fenix 8 - 51mm'
      )
  );

-- A CHECK violation aborts the transaction if the production rows no longer
-- match the operator-confirmed three-plus-one set.
CREATE TEMP TABLE compatibility_identity_correction_guard (
    corrected_47_count INTEGER NOT NULL CHECK (corrected_47_count = 3),
    corrected_51_count INTEGER NOT NULL CHECK (corrected_51_count = 1)
) ON COMMIT DROP;

INSERT INTO compatibility_identity_correction_guard (
    corrected_47_count,
    corrected_51_count
)
SELECT
    count(*) FILTER (WHERE corrected_case_size_mm = 47),
    count(*) FILTER (WHERE corrected_case_size_mm = 51)
FROM compatibility_evidence_identity_correction
WHERE correction_reason = 'operator-confirmed historical evidence correction';

UPDATE compatibility_evidence_event AS e
SET
    model = correction.corrected_model,
    compatibility_identity = correction.corrected_compatibility_identity,
    variant = correction.corrected_variant,
    case_size_mm = correction.corrected_case_size_mm,
    display_type = correction.corrected_display_type,
    canonical_device_model_id = correction.canonical_device_model_id
FROM compatibility_evidence_identity_correction AS correction
WHERE correction.event_id = e.event_id;

UPDATE compatibility_model_review
SET
    identity_key = 'fēnix 8 · 47 mm AMOLED',
    public_display_name = 'fēnix 8 · 47 mm AMOLED',
    updated_at = now()
WHERE model = 'fēnix 8'
  AND identity_key = 'fēnix 8';

UPDATE compatibility_model_review
SET
    identity_key = 'fēnix 8 · 51 mm AMOLED',
    public_display_name = 'fēnix 8 · 51 mm AMOLED',
    updated_at = now()
WHERE model = 'fenix 8 - 51mm'
  AND identity_key = 'fenix 8 - 51mm';

-- Canonical compatibility status thresholds.
-- Every aggregate originates from opt-in map installation evidence. Reconnect,
-- map visibility, firmware variation, physical-device count, and review state
-- remain diagnostics and never promote compatibility status.
DROP VIEW compatibility_model_statistics;

CREATE VIEW compatibility_model_statistics AS
WITH event_stats AS (
    SELECT
        e.compatibility_identity,
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
        max(e.occurred_at) AS last_evidence,
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
    e.error_categories,
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
    COALESCE(NULLIF(r.public_display_name, ''), e.compatibility_identity) AS public_display_name
FROM event_stats e
LEFT JOIN compatibility_model_review r
    ON COALESCE(NULLIF(r.identity_key, ''), r.model) = e.compatibility_identity;

CREATE TABLE admin_user (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Bootstrap creates exactly one owner account. Additional roles/users require
-- a later explicit authorization model instead of an accidental setup race.
CREATE UNIQUE INDEX admin_single_owner_idx ON admin_user ((true));

CREATE TABLE admin_session (
    token_hash TEXT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL REFERENCES admin_user(id) ON DELETE CASCADE,
    csrf_token_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX admin_session_expiry_idx ON admin_session(expires_at);

ALTER TABLE compatibility_model_review
    ADD COLUMN public_statistics_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN public_display_name TEXT;

CREATE VIEW compatibility_model_statistics AS
SELECT e.model,
    string_agg(DISTINCT COALESCE(e.firmware_version, 'unknown'), ', ' ORDER BY COALESCE(e.firmware_version, 'unknown')) AS firmware_versions,
    count(*) AS attempted_install_count,
    count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS successful_install_count,
    count(*) FILTER (WHERE e.phase_outcome = 'FAILED') AS failed_install_count,
    round(100.0 * count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') / NULLIF(count(*), 0), 1) AS success_rate,
    max(e.occurred_at) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') AS last_success,
    max(e.occurred_at) FILTER (WHERE e.phase_outcome = 'FAILED') AS last_failure,
    COALESCE((
        SELECT jsonb_object_agg(COALESCE(category, 'unknown'), category_count)
        FROM (
            SELECT x.error_category AS category, count(*) AS category_count
            FROM compatibility_evidence_event x
            WHERE x.model = e.model AND x.phase_outcome = 'FAILED'
            GROUP BY x.error_category
        ) category_counts
    ), '{}'::jsonb) AS error_categories,
    CASE
        WHEN count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') >= 3
             AND count(DISTINCT e.firmware_version) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED') >= 2
             AND COALESCE(r.physical_device_evidence_count, 0) >= 2 THEN 'VERIFIED'
        WHEN EXISTS (
            SELECT 1 FROM compatibility_evidence_event same_firmware
            WHERE same_firmware.model = e.model
              AND same_firmware.phase_outcome = 'SUCCEEDED'
              AND same_firmware.automatic_finishing_result = 'VERIFIED'
              AND NULLIF(same_firmware.firmware_version, '') IS NOT NULL
            GROUP BY same_firmware.firmware_version
            HAVING count(*) >= 3
        ) THEN 'SUPPORTED'
        WHEN count(*) FILTER (WHERE e.phase_outcome = 'SUCCEEDED' AND e.automatic_finishing_result = 'VERIFIED' AND NULLIF(e.firmware_version, '') IS NOT NULL) >= 1 THEN 'TESTED'
        ELSE 'UNKNOWN' END AS calculated_status,
    COALESCE(r.physical_device_evidence_count, 0) AS physical_device_evidence_count,
    COALESCE(r.review_notes, '') AS review_notes,
    COALESCE(r.review_status, 'PENDING') AS review_status,
    COALESCE(r.public_statistics_enabled, false) AS public_statistics_enabled,
    COALESCE(NULLIF(r.public_display_name, ''), e.model) AS public_display_name
FROM compatibility_evidence_event e
LEFT JOIN compatibility_model_review r ON r.model = e.model
GROUP BY e.model, r.physical_device_evidence_count, r.review_notes, r.review_status,
         r.public_statistics_enabled, r.public_display_name;

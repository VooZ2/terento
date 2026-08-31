-- Keep OpenTopoMap paused for the beta.8 testing release.
-- This is a one-time operator-authorized state correction after an older
-- deployment left the known adapter ACTIVE. It changes provider lifecycle
-- state only; packages and provider metadata remain intact.

WITH repaired AS (
    UPDATE map_provider AS p
    SET status = 'PAUSED', updated_at = now()
    WHERE p.id = 'opentopomap'
      AND p.status = 'ACTIVE'
    RETURNING p.id
)
INSERT INTO admin_audit_log (
    admin_user_id, action, provider_id, old_status, new_status,
    reason, target, request_id, details
)
SELECT
    NULL,
    'provider.status_repaired',
    repaired.id,
    'ACTIVE',
    'PAUSED',
    'Kept OpenTopoMap PAUSED for beta.8 testing until explicit activation.',
    'PAUSED',
    'migration-028',
    '{"beta8Testing":true,"explicitActivationRequired":true}'::jsonb
FROM repaired;

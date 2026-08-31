-- Restore the beta.8 OpenTopoMap safety state if an older deployment left the
-- metadata-only provider active without any available catalog packages.
-- Preserve an explicitly audited activation; only repair an unaudited,
-- unusable ACTIVE state and record the repair in the provider audit history.

WITH repaired AS (
    UPDATE map_provider AS p
    SET status = 'PAUSED', updated_at = now()
    WHERE p.id = 'opentopomap'
      AND p.status = 'ACTIVE'
      AND NOT EXISTS (
          SELECT 1
          FROM map_package AS package
          WHERE package.provider_id = p.id
            AND package.availability = 'AVAILABLE'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM admin_audit_log AS audit
          WHERE audit.provider_id = p.id
            AND audit.action = 'provider.status_changed'
            AND audit.new_status = 'ACTIVE'
      )
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
    'Restored OpenTopoMap to PAUSED because activation evidence was not present.',
    'PAUSED',
    'migration-027',
    '{"activationRequired":true,"availablePackageCount":0}'::jsonb
FROM repaired;

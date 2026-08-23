ALTER TABLE device_asset
    ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'MODEL'
        CHECK (scope IN ('FAMILY', 'MODEL', 'MODEL_SIZE', 'EXACT_VARIANT'));

-- A candidate Garmin image reference is never a public production asset.
-- Keep the row for review/audit, but make it non-approved before applying the
-- controlled-origin constraint.
UPDATE device_asset
SET status = 'REJECTED'
WHERE url IS NOT NULL
  AND url NOT LIKE 'https://api.terento.app/assets/devices/%';

ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_url_check;

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_controlled_url_check
        CHECK (url IS NULL OR url LIKE 'https://api.terento.app/assets/devices/%');

ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_device_model_id_asset_type_key;

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_model_type_scope_key
        UNIQUE (device_model_id, asset_type, scope);

CREATE INDEX IF NOT EXISTS device_asset_approved_scope_idx
    ON device_asset(device_model_id, scope, status, updated_at DESC);

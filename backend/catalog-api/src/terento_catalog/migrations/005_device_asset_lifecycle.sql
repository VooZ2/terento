ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_status_check;

ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_controlled_url_check;

ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_model_type_scope_key;

ALTER TABLE device_asset
    ADD COLUMN IF NOT EXISTS storage_key TEXT;

ALTER TABLE device_asset
    ALTER COLUMN device_model_id DROP NOT NULL;

UPDATE device_asset
SET
    status = CASE status
        WHEN 'NONE' THEN 'MISSING'
        WHEN 'PENDING' THEN 'PENDING_REVIEW'
        WHEN 'APPROVED' THEN 'AVAILABLE'
        WHEN 'REJECTED' THEN 'DEPRECATED'
        ELSE status
    END,
    url = CASE
        WHEN url LIKE 'https://api.terento.app/assets/devices/%' THEN url
        ELSE NULL
    END,
    storage_key = CASE
        WHEN url LIKE 'https://api.terento.app/assets/devices/%'
            THEN replace(url, 'https://api.terento.app/assets/', '')
        ELSE storage_key
    END;

UPDATE device_asset
SET status = 'DEPRECATED'
WHERE status = 'AVAILABLE'
  AND (url IS NULL OR storage_key IS NULL);

ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_scope_check;

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_status_check
        CHECK (status IN ('MISSING', 'PENDING_REVIEW', 'AVAILABLE', 'DEPRECATED'));

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_scope_check
        CHECK (scope IN ('FAMILY', 'MODEL', 'MODEL_SIZE', 'EXACT_VARIANT', 'GENERIC'));

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_controlled_url_check
        CHECK (url IS NULL OR url LIKE 'https://api.terento.app/assets/devices/%');

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_storage_key_check
        CHECK (storage_key IS NULL OR storage_key LIKE 'devices/%.webp');

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_scope_owner_check
        CHECK (
            (scope = 'GENERIC' AND device_model_id IS NULL)
            OR (scope <> 'GENERIC' AND device_model_id IS NOT NULL)
        );

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_model_type_scope_key
        UNIQUE (device_model_id, asset_type, scope);

CREATE UNIQUE INDEX device_asset_generic_scope_unique_idx
    ON device_asset (asset_type, scope)
    WHERE device_model_id IS NULL;

CREATE INDEX IF NOT EXISTS device_asset_lifecycle_idx
    ON device_asset(status, updated_at DESC);

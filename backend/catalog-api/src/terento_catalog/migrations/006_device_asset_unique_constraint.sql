DROP INDEX IF EXISTS device_asset_model_type_scope_unique_idx;

ALTER TABLE device_asset
    DROP CONSTRAINT IF EXISTS device_asset_model_type_scope_key;

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_model_type_scope_key
        UNIQUE (device_model_id, asset_type, scope);

CREATE UNIQUE INDEX IF NOT EXISTS device_asset_generic_scope_unique_idx
    ON device_asset (asset_type, scope)
    WHERE device_model_id IS NULL;

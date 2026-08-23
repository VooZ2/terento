ALTER TABLE device_asset
    ADD COLUMN IF NOT EXISTS source_type TEXT,
    ADD COLUMN IF NOT EXISTS source_brand TEXT,
    ADD COLUMN IF NOT EXISTS attribution_required BOOLEAN;

-- Existing available rows predate the explicit source contract. Keep their
-- audit record but fail closed until an operator re-prepares and approves the
-- asset with source metadata.
UPDATE device_asset
SET status = 'DEPRECATED', updated_at = now()
WHERE status = 'AVAILABLE'
  AND (
      source_type IS NULL
      OR source_brand IS NULL
      OR attribution_required IS NULL
  );

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_source_type_check
        CHECK (
            source_type IS NULL
            OR source_type IN (
                'OFFICIAL_PRODUCT_MEDIA',
                'TERENTO_RENDER',
                'GENERIC_FALLBACK'
            )
        );

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_source_metadata_check
        CHECK (
            (
                source_type IS NULL
                AND source_brand IS NULL
                AND attribution_required IS NULL
            )
            OR (
                source_type IS NOT NULL
                AND source_brand IS NOT NULL
                AND btrim(source_brand) <> ''
                AND attribution_required IS NOT NULL
            )
        );

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_source_policy_check
        CHECK (
            source_type IS NULL
            OR (
                source_type = 'OFFICIAL_PRODUCT_MEDIA'
                AND source_brand = 'Garmin'
                AND attribution_required = TRUE
            )
            OR (
                source_type IN ('TERENTO_RENDER', 'GENERIC_FALLBACK')
                AND source_brand = 'Terento'
                AND attribution_required = FALSE
            )
        );

ALTER TABLE device_asset
    ADD CONSTRAINT device_asset_available_source_check
        CHECK (
            status <> 'AVAILABLE'
            OR (
                source_type IS NOT NULL
                AND source_brand IS NOT NULL
                AND attribution_required IS NOT NULL
            )
        );

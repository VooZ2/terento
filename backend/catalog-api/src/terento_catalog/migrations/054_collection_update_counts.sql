-- Unknown historical counts stay NULL; never infer zero from a fingerprint.
ALTER TABLE catalog_collection_run
    ADD COLUMN IF NOT EXISTS new_package_count INTEGER CHECK (new_package_count >= 0),
    ADD COLUMN IF NOT EXISTS updated_package_count INTEGER CHECK (updated_package_count >= 0);

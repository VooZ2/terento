ALTER TABLE map_version
    ADD COLUMN IF NOT EXISTS download_size_bytes BIGINT
        CHECK (download_size_bytes IS NULL OR download_size_bytes >= 0),
    ADD COLUMN IF NOT EXISTS install_size_bytes BIGINT
        CHECK (install_size_bytes IS NULL OR install_size_bytes >= 0),
    ADD COLUMN IF NOT EXISTS install_payload_path TEXT,
    ADD COLUMN IF NOT EXISTS size_measurement_method TEXT,
    ADD COLUMN IF NOT EXISTS size_measured_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS size_measurement_warning TEXT;

-- file_size_bytes is the existing provider package/download-size field. It is
-- copied only into the explicit download field; install size remains unknown
-- until a final payload has been measured.
UPDATE map_version
SET
    download_size_bytes = file_size_bytes,
    updated_at = now()
WHERE download_size_bytes IS NULL
  AND file_size_bytes IS NOT NULL;

CREATE INDEX IF NOT EXISTS map_version_install_size_idx
    ON map_version(install_size_bytes);

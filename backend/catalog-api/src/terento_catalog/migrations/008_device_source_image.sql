ALTER TABLE device_model
    ADD COLUMN IF NOT EXISTS source_image_url TEXT;

ALTER TABLE device_model
    DROP CONSTRAINT IF EXISTS device_model_source_image_url_check;

ALTER TABLE device_model
    ADD CONSTRAINT device_model_source_image_url_check
        CHECK (
            source_image_url IS NULL
            OR source_image_url LIKE 'https://res.garmin.com/%'
        );

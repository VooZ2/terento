-- Reviewed historical device identities are additive records.  They are not
-- collector-owned retail inventory and therefore are never deactivated by a
-- current Garmin retail collection.
ALTER TABLE device_model
    ADD COLUMN IF NOT EXISTS record_source TEXT NOT NULL DEFAULT 'CURRENT_RETAIL',
    ADD COLUMN IF NOT EXISTS collector_managed BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE device_model
    ADD CONSTRAINT device_model_record_source_check
    CHECK (record_source IN ('CURRENT_RETAIL', 'HISTORICAL_REVIEWED', 'EVIDENCE_DISCOVERED'));

CREATE INDEX device_model_record_source_idx
    ON device_model(record_source, active);

CREATE INDEX device_model_collector_managed_idx
    ON device_model(collector_managed, active);

INSERT INTO device_family (id, manufacturer, name, canonical_name, source_url)
VALUES
    ('garmin-fenix', 'Garmin', 'fēnix', 'fenix', 'https://developer.garmin.com/connect-iq/compatible-devices/'),
    ('garmin-epix', 'Garmin', 'epix', 'epix', 'https://developer.garmin.com/connect-iq/compatible-devices/'),
    ('garmin-forerunner', 'Garmin', 'Forerunner', 'forerunner', 'https://developer.garmin.com/connect-iq/compatible-devices/')
ON CONFLICT (id) DO NOTHING;

INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url,
    source_image_url, active, map_capable, support_status,
    record_source, collector_managed
)
VALUES
    ('garmin-fenix-7-47', 'garmin-fenix', 'Garmin', 'fēnix 7', 'fenix 7', '47 mm', 47, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-7s-42', 'garmin-fenix', 'Garmin', 'fēnix 7S', 'fenix 7s', '42 mm', 42, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-7x-51', 'garmin-fenix', 'Garmin', 'fēnix 7X', 'fenix 7x', '51 mm', 51, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-6-47', 'garmin-fenix', 'Garmin', 'fēnix 6', 'fenix 6', '47 mm', 47, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-6s-42', 'garmin-fenix', 'Garmin', 'fēnix 6S', 'fenix 6s', '42 mm', 42, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-6x-51', 'garmin-fenix', 'Garmin', 'fēnix 6X', 'fenix 6x', '51 mm', 51, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-epix-gen-2-47', 'garmin-epix', 'Garmin', 'epix (Gen 2)', 'epix gen 2', '47 mm', 47, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-forerunner-955', 'garmin-forerunner', 'Garmin', 'Forerunner 955', 'forerunner 955', 'Standard', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE)
ON CONFLICT (id) DO NOTHING;

-- A historical record is intentionally not made write-capable by this seed.
-- map_capable means only that the native Map Manager registry recognizes the
-- family; device writes still require the native write profile and safety gate.

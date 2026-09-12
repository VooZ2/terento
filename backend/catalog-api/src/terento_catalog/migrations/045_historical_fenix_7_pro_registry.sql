-- Reviewed historical fēnix 7 Pro identities from Garmin's Connect IQ
-- compatible-device references. These rows preserve evidence identity only;
-- they never authorize a device write and are not retail-collector records.
INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url,
    source_image_url, active, map_capable, support_status,
    record_source, collector_managed
)
VALUES
    ('garmin-fenix-7-pro', 'garmin-fenix', 'Garmin', 'fēnix 7 Pro', 'fenix 7 pro', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-7-pro-solar-no-wifi', 'garmin-fenix', 'Garmin', 'fēnix 7 Pro', 'fenix 7 pro solar no wifi', 'Solar (no Wi-Fi)', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-7s-pro', 'garmin-fenix', 'Garmin', 'fēnix 7S Pro', 'fenix 7s pro', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-7x-pro', 'garmin-fenix', 'Garmin', 'fēnix 7X Pro', 'fenix 7x pro', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-7x-pro-solar-no-wifi', 'garmin-fenix', 'Garmin', 'fēnix 7X Pro', 'fenix 7x pro solar no wifi', 'Solar (no Wi-Fi)', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE)
ON CONFLICT (id) DO NOTHING;

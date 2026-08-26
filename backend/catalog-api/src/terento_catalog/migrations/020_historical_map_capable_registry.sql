-- Historical Garmin identities recognized by the shared native/server Map
-- Manager capability registry. These records preserve evidence identity only;
-- they never authorize a device write and are not collector-managed retail
-- inventory.
INSERT INTO device_family (id, manufacturer, name, canonical_name, source_url)
VALUES
    ('garmin-d2', 'Garmin', 'D2', 'd2', 'https://developer.garmin.com/connect-iq/compatible-devices/'),
    ('garmin-descent', 'Garmin', 'Descent', 'descent', 'https://developer.garmin.com/connect-iq/compatible-devices/'),
    ('garmin-enduro', 'Garmin', 'Enduro', 'enduro', 'https://developer.garmin.com/connect-iq/compatible-devices/'),
    ('garmin-quatix', 'Garmin', 'quatix', 'quatix', 'https://developer.garmin.com/connect-iq/compatible-devices/'),
    ('garmin-tactix', 'Garmin', 'tactix', 'tactix', 'https://developer.garmin.com/connect-iq/compatible-devices/')
ON CONFLICT (id) DO NOTHING;

INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url,
    source_image_url, active, map_capable, support_status,
    record_source, collector_managed
)
VALUES
    ('garmin-d2-mach-1', 'garmin-d2', 'Garmin', 'D2 Mach 1', 'd2 mach 1', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-descent-mk1', 'garmin-descent', 'Garmin', 'Descent Mk1', 'descent mk1', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-descent-mk2', 'garmin-descent', 'Garmin', 'Descent Mk2', 'descent mk2', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-enduro-2', 'garmin-enduro', 'Garmin', 'Enduro 2', 'enduro 2', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-epix-pro-gen-2', 'garmin-epix', 'Garmin', 'epix Pro (Gen 2)', 'epix pro gen 2', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-5x', 'garmin-fenix', 'Garmin', 'fēnix 5X', 'fenix 5x', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-fenix-5-plus', 'garmin-fenix', 'Garmin', 'fēnix 5 Plus', 'fenix 5 plus', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-forerunner-945', 'garmin-forerunner', 'Garmin', 'Forerunner 945', 'forerunner 945', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-forerunner-965', 'garmin-forerunner', 'Garmin', 'Forerunner 965', 'forerunner 965', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-quatix-6', 'garmin-quatix', 'Garmin', 'quatix 6', 'quatix 6', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-quatix-7', 'garmin-quatix', 'Garmin', 'quatix 7', 'quatix 7', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-tactix-charlie', 'garmin-tactix', 'Garmin', 'tactix Charlie', 'tactix charlie', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-tactix-delta', 'garmin-tactix', 'Garmin', 'tactix Delta', 'tactix delta', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-tactix-7', 'garmin-tactix', 'Garmin', 'tactix 7', 'tactix 7', 'Historical', NULL, NULL,
     'https://www.garmin.com/en-US/c/wearables-smartwatches/', 'https://developer.garmin.com/connect-iq/compatible-devices/',
     NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE)
ON CONFLICT (id) DO NOTHING;

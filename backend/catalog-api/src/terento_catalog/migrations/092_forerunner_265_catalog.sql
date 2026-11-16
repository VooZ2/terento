-- Forerunner 265 and 265S as reviewed historical catalog rows, checked
-- 2026-11-16 (contracts/INSTALLATION_AUTHORIZATION.md).
-- Both watches reached the app's permission check on 2026-11-16 and were
-- PENDING ("Not yet enabled for this model", Admin First run "Waiting models")
-- only because Garmin's watch category no longer lists them, so the collector
-- never created a row. Each `model` is chosen so its policy base model equals
-- the normalized name the watch reports ("Forerunner 265", "Forerunner 265S";
-- Garmin device list and libmtp).
-- Maps No: Garmin's Forerunner 265 / 265S specifications (products 886785 and
-- 886689, all six SKUs) list course guidance and point-to-point navigation
-- but no mapping row, while the same generation's Forerunner 965 lists
-- built-in mapping; Terento's reviewed Map Manager list
-- (map_capability.KNOWN_NON_MAP_PREFIXES, native GarminMapCapabilityRegistry)
-- already names Forerunner 265 as not map-capable, the same evidence that set
-- Forerunner 570, 255 and 165 to No in migration 021. No change to any report,
-- assignment, statistic or other row. A watch that reports one of these names
-- moves from PENDING to "Not available for this model"; neither writes.
INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url, source_image_url,
    active, map_capable, support_status, record_source, collector_managed,
    screen_technology, inreach, specification_source, specification_evidence,
    specification_checked_at
) VALUES
    ('garmin-forerunner-265', 'garmin-forerunner', 'Garmin', 'Forerunner 265', 'forerunner 265', 'Historical', NULL, 'AMOLED', 'https://www.garmin.com/en-US/p/886785/', 'https://www.garmin.com/en-US/p/886785/', 'https://res.garmin.com/en/products/010-02810-00/v/cf-lg.jpg', TRUE, FALSE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'AMOLED', NULL, 'https://www.garmin.com/en-US/p/886785/',
     '{"map_capable": {"value": false, "source": "https://www.garmin.com/en-US/p/886785/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Specifications list course guidance and point-to-point navigation but no mapping row (Forerunner 965: built-in mapping); reviewed Map Manager list names Forerunner 265 as not map-capable"}, "screen_technology": {"value": "AMOLED", "source": "https://www.garmin.com/en-US/p/886785/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Display type"}}'::jsonb, '2026-11-16T00:00:00Z'),
    ('garmin-forerunner-265s', 'garmin-forerunner', 'Garmin', 'Forerunner 265S', 'forerunner 265s', 'Historical', NULL, 'AMOLED', 'https://www.garmin.com/en-US/p/886689/', 'https://www.garmin.com/en-US/p/886689/', 'https://res.garmin.com/en/products/010-02810-03/v/cf-lg.jpg', TRUE, FALSE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'AMOLED', NULL, 'https://www.garmin.com/en-US/p/886689/',
     '{"map_capable": {"value": false, "source": "https://www.garmin.com/en-US/p/886689/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Specifications list course guidance and point-to-point navigation but no mapping row (Forerunner 965: built-in mapping); reviewed Map Manager list names Forerunner 265 as not map-capable"}, "screen_technology": {"value": "AMOLED", "source": "https://www.garmin.com/en-US/p/886689/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Display type"}}'::jsonb, '2026-11-16T00:00:00Z')
ON CONFLICT (id) DO NOTHING;

-- Model codes for Identity review. Garmin's device list names XML part numbers
-- 006-B4257-00 "Forerunner 265" and 006-B4258-00 "Forerunner 265S"; libmtp
-- names USB 091e:50a1 and 091e:50a2 the same. New links start PENDING: an
-- administrator reviews them in Admin.
CREATE TEMP TABLE forerunner_265_code_seed (facts jsonb) ON COMMIT DROP;
INSERT INTO forerunner_265_code_seed (facts) VALUES
('{"kind":"XML_PART_NUMBER","value":"006-B4257-00","device_model_id":"garmin-forerunner-265","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"e95ec0abd0cfeb8d6bccdd428ef6e45fe7bec501dfd419a89aa6548efccc6efc","source_names":["Forerunner® 265"]}'::jsonb),
('{"kind":"XML_PART_NUMBER","value":"006-B4258-00","device_model_id":"garmin-forerunner-265s","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"e95ec0abd0cfeb8d6bccdd428ef6e45fe7bec501dfd419a89aa6548efccc6efc","source_names":["Forerunner® 265S"]}'::jsonb),
('{"kind":"USB","value":"091e:50a1","device_model_id":"garmin-forerunner-265","source_url":"https://github.com/libmtp/libmtp/blob/master/src/music-players.h","source_version":"e864335c8f9b21e1c799d5d02d45120df83acf00b28c3c3c31c7c0cd749b8828","source_names":["Forerunner 265"]}'::jsonb),
('{"kind":"USB","value":"091e:50a2","device_model_id":"garmin-forerunner-265s","source_url":"https://github.com/libmtp/libmtp/blob/master/src/music-players.h","source_version":"e864335c8f9b21e1c799d5d02d45120df83acf00b28c3c3c31c7c0cd749b8828","source_names":["Forerunner 265S"]}'::jsonb);
INSERT INTO device_identity_mapping (kind,value,device_model_id,source_url,source_version,source_names)
SELECT s.facts->>'kind',s.facts->>'value',d.id,s.facts->>'source_url',s.facts->>'source_version',s.facts->'source_names'
FROM forerunner_265_code_seed s JOIN device_model d ON d.id=s.facts->>'device_model_id'
ON CONFLICT DO NOTHING;

-- Owner decision 2026-11-02 ("Edge devices must have their real status, real
-- devices, real photos, the manufacturer's model names, and every model"):
-- the Edge rows of migration 090 become ordinary Garmin catalog rows, and
-- every other Edge model Garmin has sold is added.
--
-- Source, checked 2026-11-02: Garmin's cycling category (the same official
-- category API the collector reads; from this revision the collector reads
-- it too and keeps only Edge products), each product page's specifications,
-- Garmin's Connect IQ device list and, for models with no page left,
-- Garmin's owner's manuals. Images are Garmin's own product media.
--
--   * Current retail (in the category today): Edge 1060, 850, 550, MTB,
--     1040 Solar, Explore 3, Explore 3 Plus. Collector rows, missed count 0.
--   * Retired from retail (the opened MTP generation, no longer in the
--     category): Edge 540, 540 Solar, 840, 840 Solar, 1040, 1050, Explore 2.
--     Collector rows with the missed count at the retirement threshold (3),
--     exactly how a watch that left the category is stored.
--   * Older generations: reviewed historical rows with Maps Unknown (NULL,
--     PENDING). Garmin's pages list "ability to add maps" for several of
--     them (1030 Plus, 1030, 830, 530, 520 Plus, 1000, Touring, Touring Plus,
--     810, 800, 705, 605), but no Terento install was verified on them and
--     many connect over USB mass storage, so installs stay closed.
--
-- Maps: every model of the generation opened by 090 is Maps=Yes from its
-- Garmin specification ("ability to add maps": yes). Solar editions must
-- match their base row: the policy approves a base model only when all of
-- its rows are Maps=Yes, so a NULL Solar row would close Edge 540/840/1040.
-- Edge MTB, Explore 3 and Explore 3 Plus are the same current generation;
-- the collector would store the same value from the same specification.
--
-- No public Compatibility review, publication or support status is written.
-- Rollback: the previous revision reads every row unchanged; its collector
-- would only count the current Edge rows as missed (Admin label), with no
-- change to Maps or authorization.

-- 090 rows still sold: current retail.
UPDATE device_model AS dm
SET record_source = 'CURRENT_RETAIL',
    collector_managed = TRUE,
    consecutive_missed_collections = 0,
    product_url = v.product_url,
    source_url = 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/',
    source_image_url = v.source_image_url,
    part_number = COALESCE(dm.part_number, v.part_number),
    updated_at = now()
FROM (VALUES
    ('garmin-edge-1060', 'https://res.garmin.com/en/products/010-04598-00/g/cf-lg.jpg', '010-04598-00', 'https://www.garmin.com/en-US/p/1967830/'),
    ('garmin-edge-850', 'https://res.garmin.com/en/products/010-03023-01/g/cf-lg.jpg', '010-03023-00', 'https://www.garmin.com/en-US/p/1630197/'),
    ('garmin-edge-550', 'https://res.garmin.com/en/products/010-03022-00/g/cf-lg.jpg', '010-03022-00', 'https://www.garmin.com/en-US/p/1630737/')
) AS v (id, source_image_url, part_number, product_url)
WHERE dm.id = v.id AND dm.collector_managed = FALSE;

-- 090 rows no longer in the category: retired from retail.
UPDATE device_model AS dm
SET record_source = 'CURRENT_RETAIL',
    collector_managed = TRUE,
    consecutive_missed_collections = 3,
    product_url = v.product_url,
    source_url = 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/',
    source_image_url = v.source_image_url,
    part_number = COALESCE(dm.part_number, v.part_number),
    updated_at = now()
FROM (VALUES
    ('garmin-edge-540', 'https://res.garmin.com/en/products/010-02694-00/v/cf-lg.jpg', '010-02694-00', 'https://www.garmin.com/en-US/p/798938/'),
    ('garmin-edge-840', 'https://res.garmin.com/en/products/010-02695-00/v/cf-lg.jpg', '010-02695-00', 'https://www.garmin.com/en-US/p/798777/'),
    ('garmin-edge-1040', 'https://res.garmin.com/en/products/010-02503-00/v/cf-lg.jpg', '010-02503-00', 'https://www.garmin.com/en-US/p/731139/'),
    ('garmin-edge-1050', 'https://res.garmin.com/en/products/010-02890-01/g/cf-lg.jpg', '010-02890-00', 'https://www.garmin.com/en-US/p/1196129/'),
    ('garmin-edge-explore-2', 'https://res.garmin.com/en/products/010-02703-00/g/cf-lg.jpg', '010-02703-00', 'https://www.garmin.com/en-US/p/802162/')
) AS v (id, source_image_url, part_number, product_url)
WHERE dm.id = v.id AND dm.collector_managed = FALSE;

-- New current and retired Edge rows (collector rows, Maps from Garmin specifications).
INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, part_number, product_url, source_url, source_image_url,
    active, map_capable, support_status, record_source, collector_managed,
    consecutive_missed_collections, specification_source, specification_evidence,
    specification_checked_at
) VALUES
    ('garmin-edge-mtb', 'garmin-edge', 'Garmin', 'Edge MTB', 'edge mtb', '', NULL, NULL, '010-02993-00', 'https://www.garmin.com/en-US/p/1600117/', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/', 'https://res.garmin.com/en/products/010-02993-00/g/cf-lg.jpg',
     TRUE, TRUE, 'NOT_EVALUATED', 'CURRENT_RETAIL', TRUE, 0, 'https://www.garmin.com/en-US/p/1600117/', '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1600117/", "version": "official-product-specifications", "checkedAt": "2026-11-02T22:40:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T22:40:00Z'),
    ('garmin-edge-1040-solar-solar', 'garmin-edge', 'Garmin', 'Edge 1040 Solar', 'edge 1040 solar', '', NULL, 'Solar', '010-02503-20', 'https://www.garmin.com/en-US/p/731136/', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/', 'https://res.garmin.com/en/products/010-02503-20/g/cf-lg-83f20adf-6855-4454-803d-fb668f2ba1f6.jpg',
     TRUE, TRUE, 'NOT_EVALUATED', 'CURRENT_RETAIL', TRUE, 0, 'https://www.garmin.com/en-US/p/731136/', '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/731136/", "version": "official-product-specifications", "checkedAt": "2026-11-02T22:40:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T22:40:00Z'),
    ('garmin-edge-explore-3', 'garmin-edge', 'Garmin', 'Edge Explore 3', 'edge explore 3', '', NULL, NULL, '010-04661-00', 'https://www.garmin.com/en-US/p/1980980/', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/', 'https://res.garmin.com/en/products/010-04661-02/g/cf-lg.jpg',
     TRUE, TRUE, 'NOT_EVALUATED', 'CURRENT_RETAIL', TRUE, 0, 'https://www.garmin.com/en-US/p/1980980/', '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1980980/", "version": "official-product-specifications", "checkedAt": "2026-11-02T22:40:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T22:40:00Z'),
    ('garmin-edge-explore-3-plus', 'garmin-edge', 'Garmin', 'Edge Explore 3 Plus', 'edge explore 3 plus', '', NULL, NULL, '010-04661-10', 'https://www.garmin.com/en-US/p/1981054/', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/', 'https://res.garmin.com/en/products/010-04661-10/g/cf-lg.jpg',
     TRUE, TRUE, 'NOT_EVALUATED', 'CURRENT_RETAIL', TRUE, 0, 'https://www.garmin.com/en-US/p/1981054/', '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1981054/", "version": "official-product-specifications", "checkedAt": "2026-11-02T22:40:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T22:40:00Z'),
    ('garmin-edge-840-solar-solar', 'garmin-edge', 'Garmin', 'Edge 840 Solar', 'edge 840 solar', '', NULL, 'Solar', '010-02695-20', 'https://www.garmin.com/en-US/p/798946/', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/', 'https://res.garmin.com/en/products/010-02695-20/v/cf-lg.jpg',
     TRUE, TRUE, 'NOT_EVALUATED', 'CURRENT_RETAIL', TRUE, 3, 'https://www.garmin.com/en-US/p/798946/', '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/798946/", "version": "official-product-specifications", "checkedAt": "2026-11-02T22:40:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T22:40:00Z'),
    ('garmin-edge-540-solar-solar', 'garmin-edge', 'Garmin', 'Edge 540 Solar', 'edge 540 solar', '', NULL, 'Solar', NULL, 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/', 'https://res.garmin.com/en/products/010-02694-20/g/cf-lg.jpg',
     TRUE, TRUE, 'NOT_EVALUATED', 'CURRENT_RETAIL', TRUE, 3, 'https://www.garmin.com/en-US/p/798938/', '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/798938/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T22:40:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T22:40:00Z')
ON CONFLICT (id) DO NOTHING;

-- Older Edge generations: reviewed historical rows, Maps Unknown.
INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, part_number, product_url, source_url, source_image_url,
    active, map_capable, support_status, record_source, collector_managed
) VALUES
    ('garmin-edge-1030-plus', 'garmin-edge', 'Garmin', 'Edge 1030 Plus', 'edge 1030 plus', '', NULL, NULL, '010-02424-00', 'https://www.garmin.com/en-US/p/704417/', 'https://www.garmin.com/en-US/p/704417/', 'https://res.garmin.com/en/products/010-02424-00/v/cf-lg-96f8c563-6618-480c-bc51-d6f83cce9f0a.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-1030', 'garmin-edge', 'Garmin', 'Edge 1030', 'edge 1030', '', NULL, NULL, '010-01758-00', 'https://www.garmin.com/en-US/p/567991/', 'https://www.garmin.com/en-US/p/567991/', 'https://res.garmin.com/en/products/010-01758-00/v/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-1030-bontrager', 'garmin-edge', 'Garmin', 'Edge 1030 Bontrager', 'edge 1030 bontrager', '', NULL, NULL, '010-01758-10', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://res.garmin.com/en/products/010-01758-10/v/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-830', 'garmin-edge', 'Garmin', 'Edge 830', 'edge 830', '', NULL, NULL, '010-02061-00', 'https://www.garmin.com/en-US/p/621232/', 'https://www.garmin.com/en-US/p/621232/', 'https://res.garmin.com/en/products/010-02061-00/v/cf-lg-c49da283-894e-4ed1-9b8c-fa01fcc63d06.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-530', 'garmin-edge', 'Garmin', 'Edge 530', 'edge 530', '', NULL, NULL, '010-02060-00', 'https://www.garmin.com/en-US/p/621224/', 'https://www.garmin.com/en-US/p/621224/', 'https://res.garmin.com/en/products/010-02060-00/v/cf-lg-fa1cc038-7c87-4edc-8c66-20db27c83e21.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-520-plus', 'garmin-edge', 'Garmin', 'Edge 520 Plus', 'edge 520 plus', '', NULL, NULL, '010-02083-00', 'https://www.garmin.com/en-US/p/623539/', 'https://www.garmin.com/en-US/p/623539/', 'https://res.garmin.com/en/products/010-02083-00/v/cf-lg-6c675062-c990-47e8-939b-57e9b79caae2.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-520', 'garmin-edge', 'Garmin', 'Edge 520', 'edge 520', '', NULL, NULL, '010-01368-00', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://res.garmin.com/en/products/010-01368-00/v/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-820', 'garmin-edge', 'Garmin', 'Edge 820', 'edge 820', '', NULL, NULL, '010-01626-00', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://res.garmin.com/en/products/010-01626-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-explore-820', 'garmin-edge', 'Garmin', 'Edge Explore 820', 'edge explore 820', '', NULL, NULL, NULL, 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://res.garmin.com/en/products/010-01626-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-130-plus', 'garmin-edge', 'Garmin', 'Edge 130 Plus', 'edge 130 plus', '', NULL, NULL, '010-02385-00', 'https://www.garmin.com/en-US/p/698436/', 'https://www.garmin.com/en-US/p/698436/', 'https://res.garmin.com/en/products/010-02385-00/v/cf-lg-3713a0f1-fa47-43e6-9c44-4dfe3121386f.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-130', 'garmin-edge', 'Garmin', 'Edge 130', 'edge 130', '', NULL, NULL, '010-01913-00', 'https://www.garmin.com/en-US/p/596828/', 'https://www.garmin.com/en-US/p/596828/', 'https://res.garmin.com/en/products/010-01913-00/v/cf-lg-bae877c0-7f87-4bbf-99e0-fbb6c993fb3f.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-explore', 'garmin-edge', 'Garmin', 'Edge Explore', 'edge explore', '', NULL, NULL, '010-02029-00', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://developer.garmin.com/connect-iq/compatible-devices/', NULL,
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-1000', 'garmin-edge', 'Garmin', 'Edge 1000', 'edge 1000', '', NULL, NULL, '010-01161-00', 'https://www.garmin.com/en-US/p/134491/', 'https://www.garmin.com/en-US/p/134491/', 'https://res.garmin.com/en/products/010-01161-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-explore-1000', 'garmin-edge', 'Garmin', 'Edge Explore 1000', 'edge explore 1000', '', NULL, NULL, NULL, 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://developer.garmin.com/connect-iq/compatible-devices/', 'https://res.garmin.com/en/products/010-01527-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-touring', 'garmin-edge', 'Garmin', 'Edge Touring', 'edge touring', '', NULL, NULL, '010-01162-00', 'https://www.garmin.com/en-US/p/134596/', 'https://www.garmin.com/en-US/p/134596/', 'https://res.garmin.com/en/products/010-01163-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-touring-plus', 'garmin-edge', 'Garmin', 'Edge Touring Plus', 'edge touring plus', '', NULL, NULL, '010-01164-00', 'https://www.garmin.com/en-US/p/143677/', 'https://www.garmin.com/en-US/p/143677/', 'https://res.garmin.com/en/products/010-01165-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-810', 'garmin-edge', 'Garmin', 'Edge 810', 'edge 810', '', NULL, NULL, '010-01063-00', 'https://www.garmin.com/en-US/p/112912/', 'https://www.garmin.com/en-US/p/112912/', 'https://res.garmin.com/en/products/010-01063-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-510', 'garmin-edge', 'Garmin', 'Edge 510', 'edge 510', '', NULL, NULL, '010-01064-00', 'https://www.garmin.com/en-GB/p/112885/', 'https://www.garmin.com/en-GB/p/112885/', 'https://res.garmin.com/en/products/010-01064-00/g/cf-lg-1.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-800', 'garmin-edge', 'Garmin', 'Edge 800', 'edge 800', '', NULL, NULL, '010-00899-01', 'https://www.garmin.com/en-GB/p/69043/', 'https://www.garmin.com/en-GB/p/69043/', 'https://res.garmin.com/en_GB/products/010-00899-01/g/E800_cf_lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-500', 'garmin-edge', 'Garmin', 'Edge 500', 'edge 500', '', NULL, NULL, NULL, 'https://static.garmin.com/pumac/Edge_500_OM_EN.pdf', 'https://static.garmin.com/pumac/Edge_500_OM_EN.pdf', 'https://res.garmin.com/en/products/010-00829-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-200', 'garmin-edge', 'Garmin', 'Edge 200', 'edge 200', '', NULL, NULL, '010-00978-01', 'https://www.garmin.com/en-GB/p/90675/', 'https://www.garmin.com/en-GB/p/90675/', 'https://res.garmin.com/en/products/010-00978-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-25', 'garmin-edge', 'Garmin', 'Edge 25', 'edge 25', '', NULL, NULL, NULL, 'https://www8.garmin.com/manuals/webhelp/edge20-25/EN-US/GUID-02CB0825-BE92-42AA-A1DD-C3B875A1EEB3-homepage.html', 'https://www8.garmin.com/manuals/webhelp/edge20-25/EN-US/GUID-02CB0825-BE92-42AA-A1DD-C3B875A1EEB3-homepage.html', NULL,
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-20', 'garmin-edge', 'Garmin', 'Edge 20', 'edge 20', '', NULL, NULL, NULL, 'https://www8.garmin.com/manuals/webhelp/edge20-25/EN-US/GUID-02CB0825-BE92-42AA-A1DD-C3B875A1EEB3-homepage.html', 'https://www8.garmin.com/manuals/webhelp/edge20-25/EN-US/GUID-02CB0825-BE92-42AA-A1DD-C3B875A1EEB3-homepage.html', NULL,
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-705', 'garmin-edge', 'Garmin', 'Edge 705', 'edge 705', '', NULL, NULL, '010-00555-31', 'https://www.garmin.com/en-GB/p/10885/', 'https://www.garmin.com/en-GB/p/10885/', 'https://res.garmin.com/en/products/010-00555-20/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-605', 'garmin-edge', 'Garmin', 'Edge 605', 'edge 605', '', NULL, NULL, '010-00555-01', 'https://www.garmin.com/en-GB/p/10884/', 'https://www.garmin.com/en-GB/p/10884/', 'https://res.garmin.com/en/products/010-00555-00/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-305', 'garmin-edge', 'Garmin', 'Edge 305', 'edge 305', '', NULL, NULL, '010-00447-31', 'https://www.garmin.com/en-GB/p/331/', 'https://www.garmin.com/en-GB/p/331/', 'https://res.garmin.com/en/products/010-00447-22/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE),
    ('garmin-edge-205', 'garmin-edge', 'Garmin', 'Edge 205', 'edge 205', '', NULL, NULL, '010-00447-11', 'https://www.garmin.com/en-GB/p/6400/', 'https://www.garmin.com/en-GB/p/6400/', 'https://res.garmin.com/en/products/010-00447-12/g/cf-lg.jpg',
     TRUE, NULL, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE)
ON CONFLICT (id) DO NOTHING;

-- The collector's image placeholder for each collector row.
INSERT INTO device_asset (device_model_id, asset_type, status, scope)
SELECT id, 'product-image', 'MISSING', 'MODEL'
FROM device_model
WHERE id IN ('garmin-edge-1060', 'garmin-edge-850', 'garmin-edge-550', 'garmin-edge-540', 'garmin-edge-840', 'garmin-edge-1040', 'garmin-edge-1050', 'garmin-edge-explore-2', 'garmin-edge-mtb', 'garmin-edge-1040-solar-solar', 'garmin-edge-explore-3', 'garmin-edge-explore-3-plus', 'garmin-edge-840-solar-solar', 'garmin-edge-540-solar-solar')
  AND collector_managed = TRUE
ON CONFLICT (device_model_id, asset_type, scope) DO NOTHING;

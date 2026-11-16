-- Older Edge models with their real Maps value, checked 2026-11-16 (owner
-- decision 2026-11-16: "every model that supports maps, watches and Edge, is
-- not blocked"; contracts/INSTALLATION_AUTHORIZATION.md, Edge test rows).
-- Migration 091 stored Maps Unknown (NULL, PENDING) for every Edge model older
-- than the Edge 1040 generation. This migration replaces that NULL with the
-- value Garmin publishes, and only that NULL:
--   * Maps Yes from Garmin's product specifications, row "Ability to add maps:
--     yes" (parsed with the collector's own specification parser): Edge 1030
--     Plus, 1030, 830, 530, 520 Plus, 1000, Touring, Touring Plus, 810, 800,
--     705, 605.
--   * Maps Yes from Garmin's TopoActive cycling maps compatible-device list
--     (product 730831, SKU 010-D1761-00), with the owner's manual showing map
--     settings for loaded maps: Edge 820, Explore, Explore 820, Explore 1000.
--     These have no Garmin product page left.
--   * Maps No (reviewed owner decision, same form as migration 075): Edge 130
--     Plus, 130, 510, 200, 305, 205. Their Garmin specifications list courses
--     but no map row, and Garmin's map compatibility list does not name them.
--   * Unchanged (NULL, PENDING): Edge 1030 Bontrager, 520, 500, 25, 20. Garmin
--     publishes no specification page and no map compatibility entry for them.
-- Each update is guarded by the exact previous state (Maps NULL on a
-- HISTORICAL_REVIEWED, non-collector row) and, for specification evidence, by
-- the reviewed product page. Data only: no schema, identity, report,
-- assignment, statistic or collector row changes. The previous revision reads
-- every row unchanged; released clients apply the ordinary rule. Most of these
-- Edge models connect as USB mass storage, which Terento does not use, so a
-- Maps=Yes row there approves a model the app usually cannot open.
CREATE TEMP TABLE edge_historical_maps_seed (id TEXT PRIMARY KEY, source TEXT, map_capable BOOLEAN NOT NULL, evidence JSONB NOT NULL) ON COMMIT DROP;
INSERT INTO edge_historical_maps_seed (id, source, map_capable, evidence) VALUES
    ('garmin-edge-1030-plus', 'https://www.garmin.com/en-US/p/704417/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/704417/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-1030', 'https://www.garmin.com/en-US/p/567991/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/567991/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-830', 'https://www.garmin.com/en-US/p/621232/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/621232/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-530', 'https://www.garmin.com/en-US/p/621224/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/621224/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-520-plus', 'https://www.garmin.com/en-US/p/623539/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/623539/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-1000', 'https://www.garmin.com/en-US/p/134491/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/134491/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-touring', 'https://www.garmin.com/en-US/p/134596/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/134596/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-touring-plus', 'https://www.garmin.com/en-US/p/143677/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/143677/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-810', 'https://www.garmin.com/en-US/p/112912/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-US/p/112912/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-800', 'https://www.garmin.com/en-GB/p/69043/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-GB/p/69043/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-705', 'https://www.garmin.com/en-GB/p/10885/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-GB/p/10885/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-605', 'https://www.garmin.com/en-GB/p/10884/', TRUE, '{"value": true, "source": "https://www.garmin.com/en-GB/p/10884/", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "ability to add maps"}'::jsonb),
    ('garmin-edge-820', NULL, TRUE, '{"value": true, "source": "https://buy.garmin.com/ecommerceServices/productCompatibility/en-GB/GB/p/010-D1761-00/compatibleDevices", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Garmin TopoActive cycling maps (https://www.garmin.com/en-GB/p/730831/, 010-D1761-00) compatible devices: Edge® 820", "manual": "https://www8.garmin.com/manuals/webhelp/edge820/EN-US/Edge_820_OM_EN-US.pdf"}'::jsonb),
    ('garmin-edge-explore', NULL, TRUE, '{"value": true, "source": "https://buy.garmin.com/ecommerceServices/productCompatibility/en-GB/GB/p/010-D1761-00/compatibleDevices", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Garmin TopoActive cycling maps (https://www.garmin.com/en-GB/p/730831/, 010-D1761-00) compatible devices: Edge® Explore", "manual": "https://www8.garmin.com/manuals/webhelp/edgeexplore1030/EN-US/Edge_Explore_1030_OM_EN-US.pdf"}'::jsonb),
    ('garmin-edge-explore-820', NULL, TRUE, '{"value": true, "source": "https://buy.garmin.com/ecommerceServices/productCompatibility/en-GB/GB/p/010-D1761-00/compatibleDevices", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Garmin TopoActive cycling maps (https://www.garmin.com/en-GB/p/730831/, 010-D1761-00) compatible devices: Edge® Explore 820", "manual": "https://www8.garmin.com/manuals/webhelp/edgeexplore820/EN-US/Edge_Explore_820_OM_EN-US.pdf"}'::jsonb),
    ('garmin-edge-explore-1000', NULL, TRUE, '{"value": true, "source": "https://buy.garmin.com/ecommerceServices/productCompatibility/en-GB/GB/p/010-D1761-00/compatibleDevices", "version": "reviewed-official-garmin-source-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": "Garmin TopoActive cycling maps (https://www.garmin.com/en-GB/p/730831/, 010-D1761-00) compatible devices: Edge® Explore 1000", "manual": "https://www8.garmin.com/manuals/webhelp/edgeexplore1000/EN-US/Edge_Explore_1000_OM_(Full_OM)_EN-US.pdf"}'::jsonb),
    ('garmin-edge-130-plus', 'https://www.garmin.com/en-US/p/698436/', FALSE, '{"value": false, "source": "https://www.garmin.com/en-US/p/698436/", "version": "reviewed-owner-decision-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": null, "review": "Reviewed owner decision 2026-11-16: the official specifications list courses and navigation routes but no map row (Garmin''s map Edge pages list Basemap and Ability to add maps), and Garmin''s TopoActive cycling maps compatible-device list does not name it"}'::jsonb),
    ('garmin-edge-130', 'https://www.garmin.com/en-US/p/596828/', FALSE, '{"value": false, "source": "https://www.garmin.com/en-US/p/596828/", "version": "reviewed-owner-decision-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": null, "review": "Reviewed owner decision 2026-11-16: the official specifications list courses and navigation routes but no map row (Garmin''s map Edge pages list Basemap and Ability to add maps), and Garmin''s TopoActive cycling maps compatible-device list does not name it"}'::jsonb),
    ('garmin-edge-510', 'https://www.garmin.com/en-GB/p/112885/', FALSE, '{"value": false, "source": "https://www.garmin.com/en-GB/p/112885/", "version": "reviewed-owner-decision-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": null, "review": "Reviewed owner decision 2026-11-16: the official specifications list courses and navigation routes but no map row (Garmin''s map Edge pages list Basemap and Ability to add maps), and Garmin''s TopoActive cycling maps compatible-device list does not name it"}'::jsonb),
    ('garmin-edge-200', 'https://www.garmin.com/en-GB/p/90675/', FALSE, '{"value": false, "source": "https://www.garmin.com/en-GB/p/90675/", "version": "reviewed-owner-decision-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": null, "review": "Reviewed owner decision 2026-11-16: the official specifications list courses and navigation routes but no map row (Garmin''s map Edge pages list Basemap and Ability to add maps), and Garmin''s TopoActive cycling maps compatible-device list does not name it"}'::jsonb),
    ('garmin-edge-305', 'https://www.garmin.com/en-GB/p/331/', FALSE, '{"value": false, "source": "https://www.garmin.com/en-GB/p/331/", "version": "reviewed-owner-decision-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": null, "review": "Reviewed owner decision 2026-11-16: the official specifications list courses and navigation routes but no map row (Garmin''s map Edge pages list Basemap and Ability to add maps), and Garmin''s TopoActive cycling maps compatible-device list does not name it"}'::jsonb),
    ('garmin-edge-205', 'https://www.garmin.com/en-GB/p/6400/', FALSE, '{"value": false, "source": "https://www.garmin.com/en-GB/p/6400/", "version": "reviewed-owner-decision-2026-11-16", "checkedAt": "2026-11-16T00:00:00Z", "field": null, "review": "Reviewed owner decision 2026-11-16: the official specifications list courses and navigation routes but no map row (Garmin''s map Edge pages list Basemap and Ability to add maps), and Garmin''s TopoActive cycling maps compatible-device list does not name it"}'::jsonb);

UPDATE device_model d SET
    map_capable = s.map_capable,
    specification_evidence = d.specification_evidence || jsonb_build_object('map_capable', s.evidence),
    updated_at = now()
FROM edge_historical_maps_seed s
WHERE d.id = s.id
  AND d.map_capable IS NULL
  AND d.record_source = 'HISTORICAL_REVIEWED'
  AND d.collector_managed = FALSE
  AND d.family_id = 'garmin-edge'
  AND (s.source IS NULL OR d.product_url = s.source);

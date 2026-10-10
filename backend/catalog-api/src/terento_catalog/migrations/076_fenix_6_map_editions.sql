-- Owner decision 2026-10-10: add the fēnix 6 map-capable editions that the
-- 2026-10-09 review left out (contracts/INSTALLATION_AUTHORIZATION.md).
-- Additive and backward-compatible: rows are inserted only when their id is
-- absent; no existing row, column or constraint is changed. The existing
-- fēnix 6 / 6S / 6X rows keep their stored values.
--
-- Each `model` is chosen so its policy base model equals the normalized name
-- the watch reports ("fēnix 6X Pro Solar" -> "fenix 6x pro"). Maps evidence:
-- the Garmin product specifications (`Full vector map: yes`) or the fēnix 6
-- Pro Series owner's manual Map topic ("Your device comes preloaded with
-- maps"). Dual Power is Garmin Japan's name for the Pro Solar editions and
-- fēnix 6X Asia is the Asian fēnix 6X Pro (Garmin device types 006-B3769,
-- 006-B3771 and 006-B3516). Standard (non-Pro) fēnix 6 and 6S editions are
-- not added: Garmin publishes no map row for them.
INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url, source_image_url,
    active, map_capable, support_status, record_source, collector_managed,
    screen_technology, inreach, specification_source, specification_evidence,
    specification_checked_at
) VALUES
    ('garmin-fenix-6-pro', 'garmin-fenix', 'Garmin', 'fēnix 6 Pro', 'fenix 6 pro', 'Historical', 47, 'MIP', 'https://www.garmin.com/en-US/p/641479/', 'https://www.garmin.com/en-US/p/641479/', 'https://res.garmin.com/en/products/010-02158-22/v/cf-lg-1dc0e640-4559-4402-a7ff-993b25806190-1.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www.garmin.com/en-US/p/641479/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/641479/", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "full vector map"}}'::jsonb, '2026-10-10T00:00:00Z'),
    ('garmin-fenix-6s-pro', 'garmin-fenix', 'Garmin', 'fēnix 6S Pro', 'fenix 6s pro', 'Historical', 42, 'MIP', 'https://www.garmin.com/en-US/p/641530/', 'https://www.garmin.com/en-US/p/641530/', 'https://res.garmin.com/en/products/010-02159-10/v/cf-lg-877bbbbd-9b15-41cd-9c8f-e212602518ee-1.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www.garmin.com/en-US/p/641530/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/641530/", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "full vector map"}}'::jsonb, '2026-10-10T00:00:00Z'),
    ('garmin-fenix-6x-pro', 'garmin-fenix', 'Garmin', 'fēnix 6X Pro', 'fenix 6x pro', 'Historical', 51, 'MIP', 'https://www.garmin.com/en-US/p/641435/', 'https://www.garmin.com/en-US/p/641435/', 'https://res.garmin.com/en/products/010-02157-00/v/cf-lg-ecea6607-4328-4761-be0b-cb997234b58b.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www.garmin.com/en-US/p/641435/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/641435/", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "full vector map"}}'::jsonb, '2026-10-10T00:00:00Z'),
    ('garmin-fenix-6-pro-dual-power', 'garmin-fenix', 'Garmin', 'fēnix 6 Pro Dual Power', 'fenix 6 pro dual power', 'Dual Power', 47, 'MIP', 'https://www.garmin.com/en-US/p/702902/', 'https://www.garmin.com/en-US/p/702902/', 'https://res.garmin.com/en/products/010-02410-10/v/cf-lg-90c3d106-4455-4164-96e2-24a38eb5493a.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html',
     '{"map_capable": {"value": true, "source": "https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "fēnix 6 Pro Series owner''s manual, Map: \"Your device comes preloaded with maps\"; Dual Power is the Japanese Pro Solar edition (006-B3771)"}}'::jsonb, '2026-10-10T00:00:00Z'),
    ('garmin-fenix-6s-pro-dual-power', 'garmin-fenix', 'Garmin', 'fēnix 6S Pro Dual Power', 'fenix 6s pro dual power', 'Dual Power', 42, 'MIP', 'https://www.garmin.com/en-US/p/641530/', 'https://www.garmin.com/en-US/p/641530/', NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html',
     '{"map_capable": {"value": true, "source": "https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "fēnix 6 Pro Series owner''s manual, Map: \"Your device comes preloaded with maps\"; Dual Power is the Japanese Pro Solar edition (006-B3769)"}}'::jsonb, '2026-10-10T00:00:00Z'),
    ('garmin-fenix-6x-pro-dual-power', 'garmin-fenix', 'Garmin', 'fēnix 6X Pro Dual Power', 'fenix 6x pro dual power', 'Dual Power', 51, 'MIP', 'https://www.garmin.com/en-US/p/641375/', 'https://www.garmin.com/en-US/p/641375/', 'https://res.garmin.com/en/products/010-02157-23/v/cf-lg-b1a5264c-ce35-484c-9fd3-ee0b190c7896-1.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html',
     '{"map_capable": {"value": true, "source": "https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "fēnix 6 Pro Series owner''s manual, Map: \"Your device comes preloaded with maps\"; fēnix 6X Pro Dual Power is a fēnix 6X Pro name (006-B3516)"}}'::jsonb, '2026-10-10T00:00:00Z'),
    ('garmin-fenix-6x-asia', 'garmin-fenix', 'Garmin', 'fēnix 6X Asia', 'fenix 6x asia', 'Asia', 51, 'MIP', 'https://www.garmin.com/en-US/p/641435/', 'https://www.garmin.com/en-US/p/641435/', NULL, TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, 'MIP', NULL, 'https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html',
     '{"map_capable": {"value": true, "source": "https://www8.garmin.com/manuals/webhelp/fenix66s6xpro/EN-US/GUID-151DFE9D-A8AF-4477-9028-BF8E0EC34C00.html", "version": "reviewed-official-garmin-source-2026-10-10", "checkedAt": "2026-10-10T00:00:00Z", "field": "fēnix 6 Pro Series owner''s manual, Map: \"Your device comes preloaded with maps\"; the Asian fēnix 6X is the fēnix 6X Pro (006-B3516)"}}'::jsonb, '2026-10-10T00:00:00Z')
ON CONFLICT (id) DO NOTHING;

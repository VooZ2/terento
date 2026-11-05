-- Owner decision 2026-11-02: Garmin Edge cycling computers that connect over
-- MTP may receive maps under the ordinary catalog Maps rule, so the owner can
-- test Edge installs before deciding whether to keep or withdraw them
-- (contracts/INSTALLATION_AUTHORIZATION.md). This is not a public support
-- claim: public Compatibility still needs the separate Admin publication.
-- Additive and backward-compatible: rows are inserted only when their id is
-- absent; no existing row, column or constraint is changed, and the previous
-- revision reads every row unchanged.
--
-- Only the MTP generations are added (Edge 540/840/1040, 1050, 550/850, 1060
-- and Explore 2): Terento writes over MTP only. Each `model` is chosen so its
-- policy base model equals the reported name ("Edge 1040 Solar" -> "edge
-- 1040"). Maps evidence: `Ability to add maps: yes` in the Garmin product
-- specifications, checked 2026-11-02 with the collector's own specification
-- parser. Solar editions share their base model, so no row carries a Solar
-- value and a reported Solar edition stays a candidate.
INSERT INTO device_family (id, manufacturer, name, canonical_name, source_url)
VALUES ('garmin-edge', 'Garmin', 'Edge', 'edge', 'https://www.garmin.com/en-US/c/sports-fitness/cycling-bike-computers-bike-radar-power-meter-headlights/')
ON CONFLICT (id) DO NOTHING;

INSERT INTO device_model (
    id, family_id, manufacturer, model, canonical_model, variant,
    case_size_mm, display_type, product_url, source_url, source_image_url,
    active, map_capable, support_status, record_source, collector_managed,
    screen_technology, inreach, specification_source, specification_evidence,
    specification_checked_at
) VALUES
    ('garmin-edge-540', 'garmin-edge', 'Garmin', 'Edge 540', 'edge 540', '', NULL, NULL, 'https://www.garmin.com/en-US/p/798938/', 'https://www.garmin.com/en-US/p/798938/', 'https://res.garmin.com/en/products/010-02694-00/v/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/798938/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/798938/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-840', 'garmin-edge', 'Garmin', 'Edge 840', 'edge 840', '', NULL, NULL, 'https://www.garmin.com/en-US/p/798777/', 'https://www.garmin.com/en-US/p/798777/', 'https://res.garmin.com/en/products/010-02695-00/v/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/798777/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/798777/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-1040', 'garmin-edge', 'Garmin', 'Edge 1040', 'edge 1040', '', NULL, NULL, 'https://www.garmin.com/en-US/p/731139/', 'https://www.garmin.com/en-US/p/731139/', 'https://res.garmin.com/en/products/010-02503-00/v/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/731139/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/731139/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-1050', 'garmin-edge', 'Garmin', 'Edge 1050', 'edge 1050', '', NULL, NULL, 'https://www.garmin.com/en-US/p/1196129/', 'https://www.garmin.com/en-US/p/1196129/', 'https://res.garmin.com/en/products/010-02890-01/g/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/1196129/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1196129/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-550', 'garmin-edge', 'Garmin', 'Edge 550', 'edge 550', '', NULL, NULL, 'https://www.garmin.com/en-US/p/1630737/', 'https://www.garmin.com/en-US/p/1630737/', 'https://res.garmin.com/en/products/010-03022-00/v/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/1630737/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1630737/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-850', 'garmin-edge', 'Garmin', 'Edge 850', 'edge 850', '', NULL, NULL, 'https://www.garmin.com/en-US/p/1630197/', 'https://www.garmin.com/en-US/p/1630197/', 'https://res.garmin.com/en/products/010-03023-01/v/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/1630197/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1630197/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-1060', 'garmin-edge', 'Garmin', 'Edge 1060', 'edge 1060', '', NULL, NULL, 'https://www.garmin.com/en-US/p/1967830/', 'https://www.garmin.com/en-US/p/1967830/', 'https://res.garmin.com/en/products/010-04598-00/v/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/1967830/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/1967830/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z'),
    ('garmin-edge-explore-2', 'garmin-edge', 'Garmin', 'Edge Explore 2', 'edge explore 2', '', NULL, NULL, 'https://www.garmin.com/en-US/p/802162/', 'https://www.garmin.com/en-US/p/802162/', 'https://res.garmin.com/en/products/010-02703-00/g/cf-lg.jpg', TRUE, TRUE, 'NOT_EVALUATED', 'HISTORICAL_REVIEWED', FALSE, NULL, NULL, 'https://www.garmin.com/en-US/p/802162/',
     '{"map_capable": {"value": true, "source": "https://www.garmin.com/en-US/p/802162/", "version": "reviewed-official-garmin-source-2026-11-02", "checkedAt": "2026-11-02T00:00:00Z", "field": "ability to add maps"}}'::jsonb, '2026-11-02T00:00:00Z')
ON CONFLICT (id) DO NOTHING;

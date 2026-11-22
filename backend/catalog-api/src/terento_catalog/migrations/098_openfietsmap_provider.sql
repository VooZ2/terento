-- Register the reviewed OpenFietsMap adapter without activating public support.
-- Additive only: the running and the rollback revision ignore the new row.
INSERT INTO map_provider (id, name, adapter_id, status, website, license,
    license_information, attribution, license_url)
VALUES ('openfietsmap', 'OpenFietsMap', 'openfietsmap', 'PAUSED', 'https://www.openfietsmap.nl/',
    'Map data © OpenStreetMap contributors (ODbL); cartography © Openfietsmap.nl, CC BY-NC-SA 3.0, listed with the author''s permission; contour lines and DEM © SRTM/NASA, U.S. Geological Survey and J. de Ferranti (viewfinderpanoramas.org).',
    'Map data © OpenStreetMap contributors (ODbL); cartography © Openfietsmap.nl, CC BY-NC-SA 3.0, listed with the author''s permission; contour lines and DEM © SRTM/NASA, U.S. Geological Survey and J. de Ferranti (viewfinderpanoramas.org).',
    'Map data © OpenStreetMap contributors; cartography © Openfietsmap.nl (CC BY-NC-SA 3.0)',
    'https://creativecommons.org/licenses/by-nc-sa/3.0/')
ON CONFLICT (id) DO NOTHING;

-- Edition is the map type: full (Benelux, Germany, Alps, islands, Europe areas),
-- Benelux light, and the transparent Benelux hiking-route layer.
ALTER TABLE map_package ADD CONSTRAINT openfietsmap_map_type_check
    CHECK (provider_id <> 'openfietsmap' OR
        (map_type IS NOT NULL AND map_type IN ('ofm-full', 'ofm-light', 'ofm-hiking')
         AND geographic_region_id IS NOT NULL));
ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;
ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap', 'maprando', 'bbbike', 'osmapa', 'luckymaps', 'openfietsmap', 'custom'));

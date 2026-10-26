-- Register the reviewed OSMapaPL adapter without activating public support.
INSERT INTO map_provider (id, name, adapter_id, status, website, license,
    license_information, attribution, license_url)
VALUES ('osmapa', 'OSMapaPL', 'osmapa', 'PAUSED', 'https://osmapa-garmin.las.org.pl/',
    'Map data © OpenStreetMap contributors (ODbL); OSMapaPL by OSMapa volunteers and Fundacja Centrum Badań nad Lasem i Zasobami Przyrodniczymi.',
    'Map data © OpenStreetMap contributors (ODbL); OSMapaPL by OSMapa volunteers and Fundacja Centrum Badań nad Lasem i Zasobami Przyrodniczymi.',
    'Map data © OpenStreetMap contributors (ODbL); OSMapaPL by OSMapa volunteers and Fundacja Centrum Badań nad Lasem i Zasobami Przyrodniczymi',
    'https://www.openstreetmap.org/copyright')
ON CONFLICT (id) DO NOTHING;

-- Style is the conflict group (one FID per style); geography distinguishes
-- Poland from Poland with border areas.
ALTER TABLE map_package ADD CONSTRAINT osmapa_map_type_check
    CHECK (provider_id <> 'osmapa' OR
        (map_type IS NOT NULL AND map_type IN ('podstawowa', 'ogonki', 'light', 'warstwice')
         AND geographic_region_id IS NOT NULL));
ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;
ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap', 'maprando', 'bbbike', 'osmapa', 'custom'));

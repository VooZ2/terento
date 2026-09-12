-- Register the reviewed adapter without activating public support.
INSERT INTO map_provider (id, name, adapter_id, status, website, license,
    license_information, attribution, license_url)
VALUES ('bbbike', 'BBBike', 'bbbike', 'PAUSED', 'https://extract.bbbike.org/',
    'Map data © OpenStreetMap contributors (ODbL); Garmin map styles and source terms provided by BBBike.',
    'Map data © OpenStreetMap contributors (ODbL); Garmin map styles and source terms provided by BBBike.',
    'Map data © OpenStreetMap contributors; Garmin maps from BBBike',
    'https://extract.bbbike.org/garmin.html')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE map_package
    ADD COLUMN map_type TEXT,
    ADD COLUMN geographic_region_id TEXT,
    ADD COLUMN country_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN region_kind TEXT NOT NULL DEFAULT 'country';
ALTER TABLE map_package ADD CONSTRAINT bbbike_map_type_check
    CHECK (provider_id <> 'bbbike' OR
        (map_type IS NOT NULL AND map_type IN ('bbbike-latin1', 'ontrail-latin1')
         AND geographic_region_id IS NOT NULL));
ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;
ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap', 'maprando', 'bbbike', 'custom'));

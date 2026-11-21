-- Register the reviewed Lucky Maps adapter without activating public support.
-- Additive only: the running and the rollback revision ignore the new row.
INSERT INTO map_provider (id, name, adapter_id, status, website, license,
    license_information, attribution, license_url)
VALUES ('luckymaps', 'Lucky Maps', 'luckymaps', 'PAUSED', 'https://luckymaps.ch/',
    'Map data © OpenStreetMap contributors (ODbL); Lucky Maps © luckymaps.ch, Lukas M., free for private use, CC BY-SA 4.0; based on Freizeitkarte (FZK project, CC BY 3.0); contours © U.S. Geological Survey and viewfinderpanoramas.org.',
    'Map data © OpenStreetMap contributors (ODbL); Lucky Maps © luckymaps.ch, Lukas M., free for private use, CC BY-SA 4.0; based on Freizeitkarte (FZK project, CC BY 3.0); contours © U.S. Geological Survey and viewfinderpanoramas.org.',
    'Map data © OpenStreetMap contributors; Lucky Maps © luckymaps.ch (CC BY-SA 4.0)',
    'https://luckymaps.ch/en/')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE compatibility_evidence_event
    DROP CONSTRAINT compatibility_evidence_event_provider_check;
ALTER TABLE compatibility_evidence_event
    ADD CONSTRAINT compatibility_evidence_event_provider_check
    CHECK (provider IN ('freizeitkarte', 'opentopomap', 'maprando', 'bbbike', 'osmapa', 'luckymaps', 'custom'));

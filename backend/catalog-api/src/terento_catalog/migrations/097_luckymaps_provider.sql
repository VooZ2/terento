-- Register the reviewed Lucky Maps adapter without activating public support.
-- Additive only: the running and the rollback revision ignore the new row.

-- A provider that has never been ACTIVE is left out of every catalog
-- projection, so a registered but unreleased provider shows nothing to users.
-- Every provider registered before this migration has already been published.
ALTER TABLE map_provider ADD COLUMN IF NOT EXISTS first_activated_at TIMESTAMPTZ;
UPDATE map_provider SET first_activated_at = created_at WHERE first_activated_at IS NULL;

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

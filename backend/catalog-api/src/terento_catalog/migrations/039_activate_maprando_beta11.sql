-- Beta.11 explicitly activates the reviewed MapRando catalog projection.
-- This migration only changes provider metadata/lifecycle state; package rows,
-- manifests and existing-provider records are untouched.

INSERT INTO map_provider (
    id, name, adapter_id, status, website, license, license_information,
    attribution, license_url
) VALUES (
    'maprando',
    'MapRando',
    'maprando',
    'ACTIVE',
    'https://ravenfeld.gitlab.io/open-garmin-map/',
    'Map data © OpenStreetMap contributors (ODbL); MapRando map generation by Alexis Lecanu; see the provider source for terms.',
    'Map data © OpenStreetMap contributors (ODbL); MapRando map generation by Alexis Lecanu; see the provider source for terms.',
    'Map data © OpenStreetMap contributors; MapRando by Alexis Lecanu',
    'https://gitlab.com/ravenfeld/garmincustommap'
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    adapter_id = EXCLUDED.adapter_id,
    status = 'ACTIVE',
    website = EXCLUDED.website,
    license = EXCLUDED.license,
    license_information = EXCLUDED.license_information,
    attribution = EXCLUDED.attribution,
    license_url = EXCLUDED.license_url,
    updated_at = now();

INSERT INTO provider_source (provider_id, source_type, source_url)
VALUES
    ('maprando', 'WEBSITE', 'https://ravenfeld.gitlab.io/open-garmin-map/'),
    ('maprando', 'CATALOG', 'https://ravenfeld.fr/MapRando/'),
    ('maprando', 'LICENSE', 'https://gitlab.com/ravenfeld/garmincustommap')
ON CONFLICT (provider_id, source_type, source_url) DO NOTHING;

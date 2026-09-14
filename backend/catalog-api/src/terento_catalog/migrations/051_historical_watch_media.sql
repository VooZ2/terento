-- Official product images remain available outside the current retail category.
-- Update media only, filling missing URLs; identities/specifications stay intact.
WITH media(id, image_url, evidence) AS (VALUES
    ('garmin-fenix-7s-42', 'https://res.garmin.com/en/products/010-02539-01/v/cf-lg-2759aec9-b3e9-47b5-96ed-1a066f0af687.jpg', '{"source": "https://www.garmin.com/en-AU/p/735542/pn/010-02539-01/", "title": "f\u0113nix\u00ae 7S \u2013 Standard Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7x-51', 'https://res.garmin.com/en/products/010-02541-01/v/cf-lg-69399493-9540-4ea5-8033-b4aba04cea8f.jpg', '{"source": "https://www.garmin.com/nl-BE/p/735579/pn/010-02541-01/", "title": "f\u0113nix\u00ae 7X \u2013 Solar Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7-pro', 'https://res.garmin.com/en/products/010-02777-10/v/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/866191/pn/010-02777-10/", "title": "f\u0113nix\u00ae 7 Pro \u2013 Sapphire Solar Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7-pro-solar-no-wifi', 'https://res.garmin.com/en/products/010-02777-10/v/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/866191/pn/010-02777-10/", "title": "f\u0113nix\u00ae 7 Pro \u2013 Sapphire Solar Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7s-pro', 'https://res.garmin.com/en/products/010-02776-10/v/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/866139/pn/010-02776-10/", "title": "f\u0113nix\u00ae 7S Pro \u2013 Sapphire Solar Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7x-pro', 'https://res.garmin.com/en/products/010-02778-01/g/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/865945/pn/010-02778-00/", "title": "f\u0113nix\u00ae 7X Pro \u2013 Solar Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7x-pro-solar-no-wifi', 'https://res.garmin.com/en/products/010-02778-01/g/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/865945/pn/010-02778-00/", "title": "f\u0113nix\u00ae 7X Pro \u2013 Solar Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-forerunner-965', 'https://res.garmin.com/en/products/010-02809-01/v/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/886725/pn/010-02809-01/", "title": "Forerunner\u00ae 965", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-epix-pro-gen-2', 'https://res.garmin.com/en/products/010-02803-10/v/cf-lg.jpg', '{"source": "https://www.garmin.com/en-US/p/894067/pn/010-02803-10/", "title": "epix\u2122 Pro (Gen 2) \u2013 Sapphire Edition | 47 mm", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-7-47', 'https://res.garmin.com/en/products/010-02540-01/v/cf-lg-f8d67916-945d-46c2-b5a7-768e40f3acd4.jpg', '{"source": "https://www.garmin.com/pt-BR/p/735611/pn/010-02540-01/", "title": "f\u0113nix\u00ae 7 \u2013 Standard Edition", "checkedAt": "2026-09-14", "scope": "MODEL", "representative": true}'::jsonb)
)
UPDATE device_model AS dm
SET source_image_url = media.image_url,
    specification_evidence = dm.specification_evidence || jsonb_build_object('source_image', media.evidence)
FROM media
WHERE dm.id = media.id
  AND dm.record_source = 'HISTORICAL_REVIEWED'
  AND NULLIF(dm.source_image_url, '') IS NULL;

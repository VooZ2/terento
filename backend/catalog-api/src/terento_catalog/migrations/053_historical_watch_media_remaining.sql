-- Official Garmin product photographs for the remaining historical map-capable watches.
-- Media only: do not change model identity, specifications or approvals.
-- All URLs are direct Garmin-hosted res.garmin.com assets checked 2026-09-15.
WITH media(id, image_url, evidence) AS (VALUES
    ('garmin-d2-mach-1',
     'https://res.garmin.com/en/products/010-02582-55/v/cf-lg-d8e1efa8-966c-4e9d-971e-1536b407b5fc.jpg',
     '{"source": "https://www.garmin.com/en-GB/p/798926/pn/010-02582-55/", "title": "D2™ Mach 1", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-descent-mk1',
     'https://res.garmin.com/en/products/010-01760-12/v/cf-lg-498c04be-8a9a-4136-8728-a6f62a78e2c3.jpg',
     '{"source": "https://www.garmin.com/en-GB/p/568181/pn/010-01760-12/", "title": "Descent™ Mk1", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-descent-mk2',
     'https://res.garmin.com/en/products/010-02132-00/v/cf-lg-90f9236a-78f2-4f4f-b461-d7d89eba9b42.jpg',
     '{"source": "https://www.garmin.com/en-US/p/633356/", "title": "Descent™ Mk2", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-enduro-2',
     'https://res.garmin.com/en/products/010-02754-00/g/cf-lg.jpg',
     '{"source": "https://www.garmin.com/en-US/p/854515/", "title": "Enduro™ 2", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-5x',
     'https://res.garmin.com/en/products/010-01733-00/v/cf-lg.jpg',
     '{"source": "https://www.garmin.com/en-US/p/560327/", "title": "fēnix® 5X", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-fenix-5-plus',
     'https://res.garmin.com/en/products/010-01988-00/v/cf-lg-e37adc65-8f4c-47a1-b178-1a70a53c8416.jpg',
     '{"source": "https://www.garmin.com/en-US/p/603267/", "title": "fēnix® 5 Plus", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-forerunner-945',
     'https://res.garmin.com/en/products/010-02063-10/v/cf-lg-a416e7ee-3d8d-4102-97f0-15ffd4bcda9b.jpg',
     '{"source": "https://www.garmin.com/en-US/p/621922/pn/010-02063-10/", "title": "Forerunner® 945", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-quatix-6',
     'https://res.garmin.com/en/products/010-02158-90/g/cf-lg-75ccd32f-c34f-408f-90db-06472aed9598.jpg',
     '{"source": "https://www.garmin.com/en-GB/p/699976/", "title": "quatix® 6", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-quatix-7',
     'https://res.garmin.com/en/products/010-02540-60/v/cf-lg-a006b022-3c06-4018-9fc5-9a62720167e8.jpg',
     '{"source": "https://www.garmin.com/en-US/p/818387/", "title": "quatix® 7 – Standard Edition", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-tactix-charlie',
     'https://res.garmin.com/en/products/010-02084-00/g/cf-lg-b6cc2880-6b9b-4d69-ac31-a7e26a12afd9.jpg',
     '{"source": "https://www.garmin.com/en-US/p/623921/", "title": "tactix® Charlie", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-tactix-delta',
     'https://res.garmin.com/en/products/010-02357-00/g/cf-lg-2c2fad14-11ab-4115-90bf-22cd64eae0d4.jpg',
     '{"source": "https://www.garmin.com/en-US/p/pn/010-02357-00/", "title": "tactix® Delta – Sapphire Edition", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb),
    ('garmin-tactix-7',
     'https://res.garmin.com/en/products/010-02704-00/v/cf-lg-5b6f4bde-0274-49c1-a0fa-99cecf5d9d7c.jpg',
     '{"source": "https://www.garmin.com/en-US/p/802925/pn/010-02704-00/", "title": "tactix® 7 – Standard Edition", "checkedAt": "2026-09-15", "scope": "MODEL", "representative": true}'::jsonb)
)
UPDATE device_model AS dm
SET source_image_url = media.image_url,
    specification_evidence = dm.specification_evidence || jsonb_build_object('source_image', media.evidence)
FROM media
WHERE dm.id = media.id
  AND dm.record_source = 'HISTORICAL_REVIEWED'
  AND NULLIF(dm.source_image_url, '') IS NULL;

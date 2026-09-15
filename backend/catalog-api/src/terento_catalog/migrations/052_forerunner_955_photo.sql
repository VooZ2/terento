-- Official Forerunner 955 (non-Solar) product photograph, checked 2026-09-15.
-- Media only: do not change model identity, specifications or approvals.
UPDATE device_model
SET source_image_url = 'https://res.garmin.com/en/products/010-02638-10/v/cf-lg-d0a186df-582c-4f80-aeef-7eb37b60471b.jpg',
    specification_evidence = specification_evidence || jsonb_build_object(
        'source_image', jsonb_build_object(
            'source', 'https://www.garmin.com/en-US/p/777655/',
            'title', 'Forerunner 955',
            'checkedAt', '2026-09-15',
            'scope', 'MODEL',
            'representative', true
        )
    )
WHERE id = 'garmin-forerunner-955'
  AND record_source = 'HISTORICAL_REVIEWED'
  AND NULLIF(source_image_url, '') IS NULL;

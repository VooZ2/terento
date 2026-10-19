-- Official epix (Gen 2) product photograph, checked 2026-10-19. The row came
-- from 016 without media and 051/053 did not cover it, so public pages showed
-- the generic watch. Media only: do not change model identity, specifications
-- or approvals.
UPDATE device_model
SET source_image_url = 'https://res.garmin.com/en/products/010-02582-01/v/cf-lg-58ede9b6-fbfa-43b9-a81a-9e114b29b58d.jpg',
    specification_evidence = specification_evidence || jsonb_build_object(
        'source_image', jsonb_build_object(
            'source', 'https://www.garmin.com/en-GB/p/760778/pn/010-02582-01/',
            'title', 'epix (Gen 2) – Standard Edition | 47 mm',
            'checkedAt', '2026-10-19',
            'scope', 'MODEL',
            'representative', true
        )
    )
WHERE id = 'garmin-epix-gen-2-47'
  AND record_source = 'HISTORICAL_REVIEWED'
  AND NULLIF(source_image_url, '') IS NULL;

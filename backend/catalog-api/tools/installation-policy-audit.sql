-- Read-only audit for the native installation authorization policy.
-- It intentionally includes support_status only to prove that the expected
-- decision is derived from active + map_capable and not from that metadata.

SELECT
    count(*) FILTER (WHERE map_capable IS TRUE) AS map_capable_true,
    count(*) FILTER (WHERE map_capable IS FALSE) AS map_capable_false,
    count(*) FILTER (WHERE map_capable IS NULL) AS map_capable_null,
    count(*) FILTER (
        WHERE active IS TRUE AND map_capable IS TRUE
    ) AS active_maps_yes,
    count(*) FILTER (
        WHERE active IS TRUE AND map_capable IS TRUE
          AND support_status = 'UNSUPPORTED'
    ) AS maps_yes_with_unsupported_metadata,
    count(*) FILTER (
        WHERE lower(model) LIKE '%edge%'
           OR lower(canonical_model) LIKE '%edge%'
    ) AS edge_rows
FROM device_model
WHERE lower(manufacturer) = 'garmin';

SELECT
    id,
    model,
    canonical_model,
    variant,
    active,
    map_capable,
    support_status,
    CASE
        WHEN active IS NOT TRUE THEN 'BLOCKED'
        WHEN map_capable IS TRUE THEN 'APPROVED'
        WHEN map_capable IS FALSE THEN 'BLOCKED'
        ELSE 'PENDING'
    END AS expected_installation_authorization
FROM device_model
WHERE lower(manufacturer) = 'garmin'
ORDER BY id;

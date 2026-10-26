-- BBBike OpenTopoMap style: a third independent BBBike map type. Catalog v3/v4
-- keep publishing only the first two types; v5 adds this one.
ALTER TABLE map_package DROP CONSTRAINT bbbike_map_type_check;
ALTER TABLE map_package ADD CONSTRAINT bbbike_map_type_check
    CHECK (provider_id <> 'bbbike' OR
        (map_type IS NOT NULL AND map_type IN ('bbbike-latin1', 'ontrail-latin1', 'opentopo-latin1')
         AND geographic_region_id IS NOT NULL));

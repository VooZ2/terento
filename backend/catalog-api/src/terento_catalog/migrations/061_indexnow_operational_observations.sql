-- IndexNow reports use the existing bounded operational observation store.
-- The payload remains allowlisted by operational_health.py; this migration only
-- extends the classification checks and does not create a second queue/table.
ALTER TABLE operational_observation
    DROP CONSTRAINT IF EXISTS operational_observation_kind_check,
    DROP CONSTRAINT IF EXISTS operational_observation_component_check;

ALTER TABLE operational_observation
    ADD CONSTRAINT operational_observation_kind_check
        CHECK (kind IN ('WEEKLY_TEST', 'RELEASE_GATE', 'DEPLOYMENT', 'INDEXNOW')),
    ADD CONSTRAINT operational_observation_component_check
        CHECK (component IN ('test-matrix', 'release', 'site', 'catalog-api', 'indexnow'));

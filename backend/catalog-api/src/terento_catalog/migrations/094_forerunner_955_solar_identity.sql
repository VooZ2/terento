-- Forerunner 955 and Forerunner 955 Solar are one catalog row (owner request
-- 2026-11-16: "FR955 Solar ... assigned Standard").
-- Garmin's device list has one device type for the whole generation:
-- 006-B4024-00, urlName "forerunner955", named "Forerunner® 955 Dual Power"
-- (the Japanese name of the Solar edition). Production results of both
-- "Forerunner 955" and "Forerunner 955 Solar" (raw MTP model and Garmin XML
-- description) report that one code, so no reported fact separates Standard
-- from Solar. The historical row garmin-forerunner-955 (migration 016) is
-- therefore the whole generation, and its variant label "Standard" was wrong
-- for the Solar watches assigned to it. The label becomes "Historical", like
-- the other reviewed generation rows (Forerunner 965, fēnix 7 Pro). No result,
-- assignment, statistic or permission changes; the Solar results already
-- assigned to this row are correct under the new label.
UPDATE device_model
SET variant = 'Historical', updated_at = now()
WHERE id = 'garmin-forerunner-955'
  AND variant = 'Standard'
  AND record_source = 'HISTORICAL_REVIEWED'
  AND collector_managed = FALSE;

-- Code link: 006-B4024-00 names both Forerunner 955 rows (this row and the
-- Japanese "Forerunner 955 Dual Power" row of migration 075, whose link was
-- PENDING). The PENDING link outside the candidates kept every
-- "Forerunner 955 Solar" result in Identity review. Only undecided links
-- change; an administrator's decision always stays. USB 091e:4fb8 (libmtp
-- "Forerunner 955 Solar") stays PENDING: no source names the Dual Power code.
CREATE TEMP TABLE forerunner_955_code_seed (facts jsonb) ON COMMIT DROP;
INSERT INTO forerunner_955_code_seed (facts) VALUES
('{"kind":"XML_PART_NUMBER","value":"006-B4024-00","device_model_id":"garmin-forerunner-955","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"reviewed-2026-11-16","source_names":["Forerunner® 955 Dual Power"],"reason":"Migration 094: Garmin''s device list has one Forerunner 955 device type (006-B4024-00, urlName forerunner955); Forerunner 955 and 955 Solar results both report it."}'::jsonb),
('{"kind":"XML_PART_NUMBER","value":"006-B4024-00","device_model_id":"garmin-forerunner-955-dual-power","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"17d5055eb1ae5c8f7b0aaf66d8c01451e4addf473692afc4bd58e40e788799bc","source_names":["Forerunner® 955 Dual Power"],"reason":"Migration 094: Garmin''s device list names this code Forerunner 955 Dual Power."}'::jsonb);

INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, source_names)
SELECT s.facts->>'kind', s.facts->>'value', d.id, s.facts->>'source_url', s.facts->>'source_version', s.facts->'source_names'
FROM forerunner_955_code_seed s
JOIN device_model d ON d.id = s.facts->>'device_model_id'
WHERE NOT EXISTS (
    SELECT 1 FROM device_identity_mapping m
    WHERE m.kind = s.facts->>'kind' AND m.value = s.facts->>'value' AND m.device_model_id = d.id);

WITH reviewed AS (
    UPDATE device_identity_mapping m
    SET status = 'APPROVED', review_reason = s.facts->>'reason', reviewed_by = NULL, reviewed_at = now()
    FROM forerunner_955_code_seed s
    WHERE m.status = 'PENDING'
      AND m.kind = s.facts->>'kind' AND m.value = s.facts->>'value'
      AND m.device_model_id = s.facts->>'device_model_id'
    RETURNING m.id, m.review_reason)
INSERT INTO device_identity_mapping_audit (mapping_id, previous_status, new_status, reason)
SELECT id, 'PENDING', 'APPROVED', review_reason FROM reviewed;

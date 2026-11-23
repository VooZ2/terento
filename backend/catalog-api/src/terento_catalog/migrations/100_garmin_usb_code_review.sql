-- Garmin USB code review, 2026-11-23 (owner: "taisyk laikrodzio priskyrima";
-- check every USB code the same way). Data only: no report, assignment,
-- permission or statistic is changed here; identity assessment reads the
-- reviewed links on its next pass and the scheduler re-assesses undecided
-- results as usual. Identity grants no write authority
-- (contracts/INSTALLATION_AUTHORIZATION.md).
--
-- Rule used for every decision: a Garmin watch's USB product ID is 0x4000 plus
-- its Garmin device type number (091e:51b8 = 0x4000 + 4536 = 006-B4536-00).
-- Production reports confirm it (fēnix 7 Pro 006-B4375-00 with 091e:5117,
-- fēnix 8 51 mm Solar 006-B4533-00 with 091e:51b5, fēnix 8 47 mm AMOLED and
-- quatix 8 47 mm AMOLED 006-B4536-00 with 091e:51b8), and so does every
-- single-model libmtp name. A code therefore names the catalog models Garmin's
-- device list names for that device type, and no others.
--
-- 091e:51b8 = 006-B4536-00, which Garmin's device list names "fēnix 8 AMOLED
-- (47mm/51mm)" and "quatix 8 AMOLED (47mm/51mm)" (links APPROVED in migration
-- 086). quatix 8 47 mm AMOLED reported it on 2026-11-22 ("quatix 8 - 47mm",
-- 006-B4536-00) and, without its link, waited in Identity review; the PENDING
-- 43 mm and 51 mm links also kept the code's review incomplete. fēnix 8 43 mm
-- AMOLED is device type 006-B4534-00 (USB 091e:51b6), so its 51b8 link is
-- rejected. quatix 8 51 mm AMOLED shares the device type: without its link a
-- completely reviewed code would make every quatix 8 51 mm a code conflict.
--
-- Only undecided links change; an administrator's decision always stays.
-- Missing APPROVED links are added first for catalog models this database has.
CREATE TEMP TABLE usb_code_review_seed (facts jsonb) ON COMMIT DROP;
INSERT INTO usb_code_review_seed (facts) VALUES
('{"decision":"APPROVED","kind":"USB","value":"091e:51b8","device_model_id":"garmin-fenix-8-47-amoled","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"reviewed-2026-11-23","source_names":["fēnix® 8 AMOLED (47mm/51mm)"],"reason":"Migration 100: USB 091e:51b8 is Garmin device type 006-B4536-00, fēnix 8 AMOLED (47mm/51mm)."}'::jsonb),
('{"decision":"APPROVED","kind":"USB","value":"091e:51b8","device_model_id":"garmin-fenix-8-51-amoled","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"reviewed-2026-11-23","source_names":["fēnix® 8 AMOLED (47mm/51mm)"],"reason":"Migration 100: USB 091e:51b8 is Garmin device type 006-B4536-00, fēnix 8 AMOLED (47mm/51mm)."}'::jsonb),
('{"decision":"APPROVED","kind":"USB","value":"091e:51b8","device_model_id":"garmin-quatix-8-47-amoled","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"reviewed-2026-11-23","source_names":["quatix® 8 AMOLED (47mm/51mm)"],"reason":"Migration 100: USB 091e:51b8 is Garmin device type 006-B4536-00, quatix 8 AMOLED (47mm/51mm); quatix 8 47 mm reported it on 2026-11-22."}'::jsonb),
('{"decision":"APPROVED","kind":"USB","value":"091e:51b8","device_model_id":"garmin-quatix-8-51-amoled","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"reviewed-2026-11-23","source_names":["quatix® 8 AMOLED (47mm/51mm)"],"reason":"Migration 100: USB 091e:51b8 is Garmin device type 006-B4536-00, quatix 8 AMOLED (47mm/51mm)."}'::jsonb),
('{"decision":"REJECTED","kind":"USB","value":"091e:51b8","device_model_id":"garmin-fenix-8-43-amoled","reason":"Migration 100: fēnix 8 43 mm AMOLED is Garmin device type 006-B4534-00 (USB 091e:51b6); 091e:51b8 is 006-B4536-00 (47 mm/51 mm)."}'::jsonb);

INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, source_names)
SELECT s.facts->>'kind', s.facts->>'value', d.id, s.facts->>'source_url', s.facts->>'source_version', s.facts->'source_names'
FROM usb_code_review_seed s
JOIN device_model d ON d.id = s.facts->>'device_model_id'
WHERE s.facts->>'decision' = 'APPROVED'
  AND NOT EXISTS (
      SELECT 1 FROM device_identity_mapping m
      WHERE m.kind = s.facts->>'kind' AND m.value = s.facts->>'value' AND m.device_model_id = d.id);

WITH reviewed AS (
    UPDATE device_identity_mapping m
    SET status = s.facts->>'decision', review_reason = s.facts->>'reason', reviewed_by = NULL, reviewed_at = now()
    FROM usb_code_review_seed s
    WHERE m.status = 'PENDING'
      AND m.kind = s.facts->>'kind' AND m.value = s.facts->>'value'
      AND m.device_model_id = s.facts->>'device_model_id'
    RETURNING m.id, m.status, m.review_reason)
INSERT INTO device_identity_mapping_audit (mapping_id, previous_status, new_status, reason)
SELECT id, 'PENDING', status, review_reason FROM reviewed;

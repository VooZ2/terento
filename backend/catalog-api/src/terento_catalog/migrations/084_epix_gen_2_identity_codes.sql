-- epix (Gen 2) model codes for Identity review, captured 2026-10-19.
-- The original epix and epix (Gen 2) both report the name "EPIX", so the name
-- alone cannot pick a generation (installation_policy.AMBIGUOUS_REPORTED_BASE_MODELS).
-- Garmin's device list names XML part numbers 006-B3943-00 and 006-B3944-00
-- "epix (Gen 2)" (additional name quatix 7 - Sapphire Edition, already seeded
-- by 048); libmtp names USB 091e:4f67 "EPIX 2". Migration 048 linked these
-- codes only to quatix 7. New links start PENDING: an administrator reviews
-- them in Admin. No report, assignment, permission or statistic is changed.
CREATE TEMP TABLE epix_gen_2_code_seed (facts jsonb) ON COMMIT DROP;
INSERT INTO epix_gen_2_code_seed (facts) VALUES
('{"kind":"XML_PART_NUMBER","value":"006-B3943-00","device_model_id":"garmin-epix-gen-2-47","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"17d5055eb1ae5c8f7b0aaf66d8c01451e4addf473692afc4bd58e40e788799bc","source_names":["epix™ (Gen 2)","quatix® 7 – Sapphire Edition"]}'::jsonb),
('{"kind":"XML_PART_NUMBER","value":"006-B3944-00","device_model_id":"garmin-epix-gen-2-47","source_url":"https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes","source_version":"17d5055eb1ae5c8f7b0aaf66d8c01451e4addf473692afc4bd58e40e788799bc","source_names":["epix™ (Gen 2)","quatix® 7 – Sapphire Edition"]}'::jsonb),
('{"kind":"USB","value":"091e:4f67","device_model_id":"garmin-epix-gen-2-47","source_url":"https://github.com/libmtp/libmtp/blob/master/src/music-players.h","source_version":"675a2c4aa192d1190b56888ff73e037753ec25c899f2abc279955e33a02f831c","source_names":["EPIX 2"]}'::jsonb);
INSERT INTO device_identity_mapping (kind,value,device_model_id,source_url,source_version,source_names)
SELECT s.facts->>'kind',s.facts->>'value',d.id,s.facts->>'source_url',s.facts->>'source_version',s.facts->'source_names'
FROM epix_gen_2_code_seed s JOIN device_model d ON d.id=s.facts->>'device_model_id'
ON CONFLICT DO NOTHING;

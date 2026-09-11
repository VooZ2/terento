-- User-authorized one-time cleanup of a test installation.
--
-- The admin UI calls the operation UUID the Diagnostic ID and the individual
-- compatibility row UUID the Installation ID. Match either identifier in
-- either compatibility column so the cleanup remains exact if the IDs are
-- supplied in the opposite order. Map events are keyed by operation_id.

DELETE FROM map_download_event
WHERE operation_id IN (
    '10126c60-7129-49fc-8149-91b03f419960'::uuid,
    '67dd09c7-f14f-4a22-8514-894eded0c050'::uuid
);

DELETE FROM compatibility_evidence_event
WHERE event_id IN (
    '10126c60-7129-49fc-8149-91b03f419960'::uuid,
    '67dd09c7-f14f-4a22-8514-894eded0c050'::uuid
)
   OR operation_id IN (
    '10126c60-7129-49fc-8149-91b03f419960'::uuid,
    '67dd09c7-f14f-4a22-8514-894eded0c050'::uuid
);

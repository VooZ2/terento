-- User-authorized one-time cleanup of a test diagnostic.
--
-- The admin UI calls the operation UUID the Diagnostic ID. Match it against
-- both event UUID columns because compatibility rows may use the diagnostic
-- UUID as either event_id or operation_id. Map events are keyed by
-- operation_id. This migration intentionally targets only the exact UUID
-- supplied by the user.

DELETE FROM map_download_event
WHERE operation_id = 'c1e548b3-9ae4-49e3-a9e7-7366bf3a30e9'::uuid;

DELETE FROM compatibility_evidence_event
WHERE event_id = 'c1e548b3-9ae4-49e3-a9e7-7366bf3a30e9'::uuid
   OR operation_id = 'c1e548b3-9ae4-49e3-a9e7-7366bf3a30e9'::uuid;

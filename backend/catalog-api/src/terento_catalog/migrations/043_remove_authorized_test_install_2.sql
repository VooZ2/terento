-- User-authorized one-time cleanup of a second test installation.
-- The admin UI calls the operation UUID the Diagnostic ID and the individual
-- compatibility row UUID the Installation ID. Match either identifier in
-- either compatibility column so the cleanup remains exact if the IDs are
-- supplied in the opposite order. Map events are keyed by operation_id.

DELETE FROM map_download_event
WHERE operation_id IN (
    'a493ae4e-6106-4a38-927a-e02ba0e742a0'::uuid,
    'bcec90c2-bc3b-4f39-a6df-2a077658b512'::uuid
);

DELETE FROM compatibility_evidence_event
WHERE event_id IN (
    'a493ae4e-6106-4a38-927a-e02ba0e742a0'::uuid,
    'bcec90c2-bc3b-4f39-a6df-2a077658b512'::uuid
)
   OR operation_id IN (
    'a493ae4e-6106-4a38-927a-e02ba0e742a0'::uuid,
    'bcec90c2-bc3b-4f39-a6df-2a077658b512'::uuid
);

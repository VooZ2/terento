-- 074: index compatibility evidence by canonical catalog device.
--
-- Additive and rollback-compatible: one new index, no data or view change. The
-- previous API revision runs the same queries and only gets faster plans.
-- compatibility_model_statistics looks up evidence by canonical device for
-- every aggregate row (review linkage), and the Devices/Installations snapshot
-- computes each device's first verified success the same way; without this
-- index each lookup scanned the whole table and the planner's cost estimate
-- crossed PostgreSQL's JIT optimisation threshold. The table holds at most 24
-- months of privacy-minimised rows, so a plain transactional build takes a
-- short write lock only.
CREATE INDEX IF NOT EXISTS compatibility_evidence_canonical_device_idx
    ON compatibility_evidence_event (canonical_device_model_id, compatibility_identity);

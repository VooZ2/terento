-- Additive and rollback-compatible: old clients/rows retain unknown purpose.
-- Never infer install/update intent from an absent terminal operation event.
ALTER TABLE map_download_event
    ADD COLUMN acquisition_purpose TEXT
    CHECK (acquisition_purpose IN ('install', 'update'));

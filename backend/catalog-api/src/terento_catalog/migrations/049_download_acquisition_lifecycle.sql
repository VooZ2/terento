-- Additive: released build29 events remain valid with no component identity.
ALTER TABLE map_download_event
    ADD COLUMN acquisition_id UUID,
    ADD COLUMN component_kind TEXT CHECK (component_kind IN ('main', 'contours')),
    ADD CONSTRAINT map_download_event_acquisition_pair CHECK (
        (acquisition_id IS NULL) = (component_kind IS NULL));
ALTER TABLE map_download_event DROP CONSTRAINT map_download_event_event_type_check;
ALTER TABLE map_download_event ADD CONSTRAINT map_download_event_event_type_check CHECK (
    event_type IN ('DOWNLOAD_STARTED', 'DOWNLOAD_PROCESSING', 'DOWNLOAD_SUCCEEDED',
                  'DOWNLOAD_FAILED', 'DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED',
                  'INSTALL_SUCCEEDED', 'INSTALL_FAILED'));
CREATE INDEX map_download_event_acquisition_idx ON map_download_event(acquisition_id)
    WHERE acquisition_id IS NOT NULL;
-- One package can acquire both a main map and contours in one operation.
-- Preserve legacy deduplication while separating new component attempts.
ALTER TABLE map_download_event DROP CONSTRAINT map_download_event_operation_id_event_type_map_package_id_key;
CREATE UNIQUE INDEX map_download_event_legacy_dedup_idx
    ON map_download_event(operation_id, event_type, map_package_id)
    WHERE acquisition_id IS NULL;
CREATE UNIQUE INDEX map_download_event_acquisition_phase_idx
    ON map_download_event(acquisition_id, event_type)
    WHERE acquisition_id IS NOT NULL;
CREATE UNIQUE INDEX map_download_event_acquisition_terminal_idx
    ON map_download_event(acquisition_id)
    WHERE acquisition_id IS NOT NULL AND event_type IN (
        'DOWNLOAD_SUCCEEDED', 'DOWNLOAD_FAILED', 'DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED');

-- Map lifecycle updates are distinct from first map-package installations.
-- Keep the operation identity and idempotency model unchanged.
ALTER TABLE map_download_event DROP CONSTRAINT map_download_event_event_type_check;
ALTER TABLE map_download_event ADD CONSTRAINT map_download_event_event_type_check CHECK (
    event_type IN ('DOWNLOAD_STARTED', 'DOWNLOAD_PROCESSING', 'DOWNLOAD_SUCCEEDED',
                  'DOWNLOAD_FAILED', 'DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED',
                  'INSTALL_SUCCEEDED', 'INSTALL_FAILED',
                  'MAP_UPDATE_SUCCEEDED', 'MAP_UPDATE_FAILED'));

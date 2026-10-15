-- 083: why a map download failed (contracts/map-event.schema.json
-- failureReason), DOWNLOAD_FAILED events only.
--
-- Additive: one nullable column with a closed CHECK. The previous API revision
-- never writes or reads it, and released clients through 1.0.0 send no
-- reason, which stays NULL (unknown).
ALTER TABLE map_download_event
    ADD COLUMN failure_reason TEXT,
    ADD CONSTRAINT map_download_event_failure_reason_check CHECK (
        failure_reason IS NULL OR (
            event_type = 'DOWNLOAD_FAILED'
            AND failure_reason IN (
                'TIMED_OUT', 'CONNECTION_LOST', 'OFFLINE', 'CANNOT_CONNECT', 'NETWORK_ERROR',
                'PROVIDER_REFUSED', 'PROVIDER_RATE_LIMITED', 'PROVIDER_NOT_FOUND',
                'PROVIDER_SERVER_ERROR', 'INCOMPLETE', 'SOURCE_UPDATED', 'SOURCE_INVALID',
                'MAC_STORAGE', 'OTHER')));

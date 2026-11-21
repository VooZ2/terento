-- 096: accept the app funnel stage RECONNECT_WAIT (contracts/APP_FUNNEL_CONTRACT.md).
--
-- Apps newer than 1.2.2 report the "Reconnect your device" wait after a stop
-- before any write: SHOWN when it appears, then how it ended. Expand only:
-- the stage and outcome checks are widened; every existing row and every
-- value the previous API revision writes stays valid, so a rollback to that
-- revision is safe. No column, index or stored value changes.
ALTER TABLE app_funnel_event DROP CONSTRAINT app_funnel_event_stage_check;
ALTER TABLE app_funnel_event ADD CONSTRAINT app_funnel_event_stage_check
    CHECK (stage IN ('DEVICE_CONNECT', 'AUTHORIZATION', 'CATALOG', 'INSTALL_BLOCKED', 'RECONNECT_WAIT'));
ALTER TABLE app_funnel_event DROP CONSTRAINT app_funnel_event_check;
ALTER TABLE app_funnel_event ADD CONSTRAINT app_funnel_event_check CHECK (
    (stage = 'DEVICE_CONNECT' AND outcome IN (
        'CONNECTED', 'TIMEOUT_NO_USB', 'TIMEOUT_USB_PRESENT', 'BUSY',
        'MULTIPLE_DEVICES', 'NOT_MTP_MODE', 'DISCONNECTED', 'FAILED'))
    OR (stage = 'AUTHORIZATION' AND outcome IN (
        'APPROVED', 'PENDING', 'OUT_OF_SCOPE', 'UNKNOWN_MODEL', 'AMBIGUOUS',
        'CATALOG_UNAVAILABLE', 'UPDATE_REQUIRED'))
    OR (stage = 'CATALOG' AND outcome IN (
        'REMOTE', 'REMOTE_PARTIAL', 'BUNDLED_FALLBACK', 'UPDATE_REQUIRED'))
    OR (stage = 'INSTALL_BLOCKED' AND outcome IN (
        'AUTHORIZATION', 'DEVICE_STORAGE', 'MAC_STORAGE', 'CATALOG_UNVERIFIED',
        'LOCAL_CAPABILITY', 'OTHER'))
    OR (stage = 'RECONNECT_WAIT' AND outcome IN (
        'SHOWN', 'RESUMED', 'CANCELLED', 'TIMED_OUT', 'DIFFERENT_DEVICE'))
);

-- 078: which way a web installer relay job sent the map (contracts/WEB_INSTALLER_STATISTICS_CONTRACT.md).
-- Additive and rollback-compatible: one nullable column the previous API never reads.
--
-- Which way a relay job's map bytes went: straight from the server
-- (dl.terento.app:8443), through the Cloudflare-proxied lab host (fallback
-- when the visitor's network blocks the direct port), or both.
ALTER TABLE web_installer_relay_job
    ADD COLUMN served_via TEXT CHECK (served_via IN ('direct', 'proxied', 'mixed'));

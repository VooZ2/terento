-- Owner decision 2026-11-22: draw map style previews for the two 1.3.0
-- providers before they are activated (both authors agreed to previews).
-- preview_enabled only selects what the renderer draws; while a provider is
-- not ACTIVE its styles stay out of /maps/previews/manifest.json and its
-- tiles are not served (CatalogService.preview_tile_response).
UPDATE map_provider SET preview_enabled = TRUE, updated_at = now()
WHERE id IN ('openfietsmap', 'luckymaps') AND status <> 'RETIRED';

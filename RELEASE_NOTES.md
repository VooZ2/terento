# Terento v1.0.0-beta.14 (build 35)

Terento offers Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) community maps for map-capable Garmin smartwatches on Apple Silicon Macs running macOS 13 or later.

## Improvements

- Installation and Update now check the current Garmin device catalog before acquiring a map and again before writing. Active models with Maps=Yes can be authorized without a public successful-install record.
- Missing size or display details no longer prevent authorization when every plausible catalog variant supports maps. Unknown or ambiguous devices remain pending, and an unavailable policy safely prevents a new write.
- Authorization refusals do not create failed-installation evidence. Per-map result identity improves diagnostics and statistics correlation while preserving the existing privacy controls.

Public Compatibility results do not grant installation permission. Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place.

## Known issues

Garmin Edge installation is not supported yet by the current catalog; support is planned for a future release. Some devices may need reconnecting if detection or map listing stalls.

The reported OpenTopoMap India download failure (#278) remains under investigation: no reproducible application defect has been established. This release does not claim to fix that report or the closed connection report #276.

<!-- DMG SHA-256: deb2b43f9b6409b09b218daf2caac12762391f60f8ff8f74e756f0adb4482058 -->

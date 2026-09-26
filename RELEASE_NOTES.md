# Terento v1.0.0-beta.15 (build 36)

Terento offers Freizeitkarte, OpenTopoMap, MapRando, BBBike and BBBike (Ontrail) community maps for map-capable Garmin smartwatches on Apple Silicon Macs running macOS 13 or later.

## Fixes

- Fixed the **Install** action on the **Ready to install** screen. The current device authorization now reaches the installation engine, and the action explains when authorization or the device map scan is still pending.
- Fixed **About → Update** rejecting the beta.14 update metadata with “The release summary is invalid.” The client now accepts the existing bounded plain-text summary format, and the public summary remains concise.

The fixes were owner-tested with a Garmin fēnix 8 47 mm before release. Existing protected-map, ownership, safe Update and explicit Remove safeguards remain in place.

## Known issues

Garmin Edge installation is not supported yet by the current catalog; support is planned for a future release. Some devices may need reconnecting if detection or map listing stalls.

The reported OpenTopoMap India download failure (#278) remains under investigation: no reproducible application defect has been established.

<!-- DMG SHA-256: fb8fd9e992386f97c708995d7ac3e58e072ea25159649e821e94c3f856565320 -->

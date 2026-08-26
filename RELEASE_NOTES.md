# Terento v1.0.0-beta.7

Release date: 2026-08-26

Beta.7 keeps the complete validated Freizeitkarte catalog visible while
separating catalog membership from Terento's map-acquisition policy. Downloads
for Crimea and canonical Russian Federation regions are withheld before any
temporary workspace or network request is created. Other regions, including
Ukraine, Belarus and unknown non-Russian identities, remain available under
the normal validation rules.

This remains a pre-MVP beta for hardware validation. Freizeitkarte remains the
only map provider, and model eligibility is not a claim that every exact watch
has been independently verified.

## Highlights

- Crimea remains listed under its canonical provider identity and is presented
  as part of Ukraine and temporarily occupied by russia.
- Canonical Russian Federation packages remain searchable and visible, but
  Terento does not offer their downloads while russia's war of aggression
  against Ukraine continues.
- Withheld rows show a neutral `Unavailable` state, policy explanation and no
  checkbox-like control, size, update action or storage impact.
- Ukraine and all other non-withheld packages retain the normal selectable map
  control and acquisition flow.
- Install and Safe Update use one acquisition-policy gate. A withheld package
  fails before creating temporary files or making an HTTP request.
- Existing Terento-owned maps are not reclassified. Backup and Remove remain
  available, while Update is hidden for a currently withheld region.

## Application updates

- Terento performs one non-blocking HTTPS metadata check per launch after the
  first window becomes usable. Startup failures remain silent.
- About retains the manual update check and persistent result state.
- A user-confirmed Download action opens only a strictly validated official
  Terento distribution URL. The app does not download, mount or replace itself.

## Safety and privacy

- Garmin-owned, unknown and manually managed files remain read-only.
- New installs never overwrite an existing target. Safe Update still follows
  write-new → verify → remove-old and never deletes the working map first.
- Device manifests and physical-watch ownership keys remain local. There is no
  account, login, cloud device profile or server-side Garmin identifier storage.
- Catalog filtering and acquisition policy do not add telemetry or map proxying;
  available maps still download directly from Freizeitkarte infrastructure.

## Validation status

- Automated policy tests cover canonical Crimea and Russian identities,
  Freizeitkarte `RUS*` alias mapping, non-Russian controls, stale selections,
  accessibility labels, Manage actions and fail-before-workspace/network order.
- The full native shell regression matrix and signed arm64 Release dry-run pass
  on the beta.7 candidate tree, including bundled-library and runtime-path
  verification.
- Owner hardware evidence on the connected fēnix 8 confirms the 63-package
  catalog view, withheld Russia/Crimea presentation and normal Ukraine row.
- No install, update or remove operation was performed as part of that visual
  hardware check. Safe Update's real-device newer-map gate remains pending.

## Known limitations

- Map-capable means eligible for a guarded beta attempt, not independently
  verified compatibility.
- Safe Update has not yet passed its real-device newer-map gate.
- Freizeitkarte is the only supported map provider. Terento does not host,
  mirror or proxy map binaries.
- macOS 13 or later on Apple Silicon is required. Intel Macs, App Store, PKG,
  Windows and Linux distributions are not included.

## Release artifacts

The release pipeline completed successfully and Apple notarization was
accepted with no issues.

```text
Terento-1.0.0-beta.7-macOS-arm64.dmg  6a74b7613a81c68b9e0e3995dd0e00c6a7778957fc039b40a113731573e95faa
Terento-1.0.0-beta.7-macOS-arm64.zip  f9940254242935843e7fdd340d5962961e4cdaf8f6752dcf2cef9d3fef248203
```

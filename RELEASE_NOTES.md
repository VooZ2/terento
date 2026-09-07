# Terento v1.0.0-beta.10

Beta.10 adds OpenTopoMap contour lines, clearer Finishing diagnostics, and
fixes for map removal and temporary disk usage. Distributed build: **13**.
Freizeitkarte and OpenTopoMap remain the enabled map providers.

## What changed

- Install and remove OpenTopoMap maps with validated contour-line packages.
- Restore Remove availability for managed maps after reconnect and for
  recognized incomplete custom imports, with exact ownership checks retained.
- Remove Terento's temporary downloads and extracted map files after installation
  and Finishing complete, including failure and cancellation paths. Original
  custom files selected from Downloads are preserved.
- Recheck a missing final inventory entry once after successful sampled
  verification before reporting a missing map. The map upload is never retried.
- Record bounded Finishing checkpoints and failure details in local diagnostics
  and the user-reviewed Report issue draft to investigate intermittent failures.
- Include minor presentation and diagnostic reporting corrections.

## Validation and limitations

The owner confirmed Custom IMG, Freizeitkarte Lithuania/Andorra and OpenTopoMap
Latvia with contours installation/removal in one session, followed by the
requested reconnect and longer-connected checks. Mac temporary-file cleanup
was checked separately. This is evidence for the tested fēnix 8 AMOLED, not a
general compatibility claim for every Garmin model.

Intermittent USB/session failures are not claimed to be eliminated. If Finishing
fails, use Report issue in this version to include the improved diagnostic
summary. The original Forerunner 970 Australia scenario in #119 still benefits
from confirmation on that exact device and map.

macOS 13 or later on Apple Silicon is required. This remains a Public beta;
real safe-update evidence for each provider remains a separate gate.

## Privacy and safety

Garmin-owned and unknown files remain read-only. Existing working maps are not
deleted before replacements are verified. Original custom source files and
local device manifests remain on your Mac. Raw diagnostic logs are not uploaded
automatically; compatibility and map-statistics preferences remain available
in Terento → Diagnostics. This public build has no -local suffix and uses the
ordinary production diagnostic streams.

## Release artifacts

Developer ID signing, Apple notarization, stapling, Gatekeeper and launch checks
passed for both packages. Apple submission `9c7d9a17-99a8-4466-8b84-666ce1be0589`
was accepted with no issues. The complete release pipeline and live catalog
validation passed.

```text
Terento-1.0.0-beta.10-macOS-arm64.dmg  bbbd2f01f36dbab56c4b63ad8810dd7934faf0f461b076319fb1a98281265052
Terento-1.0.0-beta.10-macOS-arm64.zip  0e45a7627e2332d31e9b0a945cbf95a3f24367ec996bba47c67f390f5c24a851
```

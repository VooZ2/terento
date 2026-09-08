# Terento v1.0.0-beta.10

Beta.10 build 15 improves installation failure reports. Distributed build: **15**.
Freizeitkarte and OpenTopoMap remain the enabled map providers.

## What changed in build 15

- Expand the user-reviewed Report issue text with bounded verification events,
  attempt counts, operation durations, target match counts and sizes.
- Keep the first target/identity/read failure and cleanup outcome separately.
- Include validated/transferred/reported sizes, sampled verification results,
  failed component and mapped transport classification without raw native messages.
- Copy the complete report for pasting when it is too large for a GitHub form URL.
- Clarify that administrator summaries contain coarse uploaded fields, not the
  detailed local trace; use the app's Report issue for the extended report.

Install, Remove, safe-update rules, retry timing and verification coverage are
unchanged from build 13. No new provider or device support is claimed.

## Validation and limitations

Build 13 hardware evidence: the owner confirmed Custom IMG, Freizeitkarte Lithuania/Andorra and OpenTopoMap
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
passed for both packages. Apple submission `1f7e860f-57e1-4444-8cce-d49d4f36a073` was accepted
with no issues. The complete release pipeline and live catalog validation passed.
Automated validation and comparison with build 13 cover this diagnostic change;
no additional hardware installation/removal test was required or performed.

```text
Terento-1.0.0-beta.10-macOS-arm64.dmg  fc29a91375ed558dd4f9614c54a1e551da6b236f28b5fe99cfe6445550c6f174
Terento-1.0.0-beta.10-macOS-arm64.zip  e321edfad7a99414edcb26c2a44023851e75564f96cdf2913017d4158ba5a49b
```

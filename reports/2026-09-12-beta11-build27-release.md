# Beta.11 build 27 — release preparation

Date: 2026-09-12. Branch: terento/beta11-build27. Public release is not yet
published. The owner explicitly authorized a new public build retaining beta.11.

## Scope and evidence

Promotes the local build25 USB operation lifetime/reference balancing, bounded
recovery and sampled-read workaround, plus build26 Install maps presentation
caching. Owner-reported MapRando Andorra and France installation PASS on fēnix 8
47 mm AMOLED / firmware23.31. Agent observed read-only connection/inventory and
matching32MiB A/B content hashes; no claim of on-watch usability, safe update,
other-device coverage or measured end-to-end UI latency.

The Release build configuration contained duplicate C/Swift compilation-condition
keys that could override TERENTO_BUNDLED_MTP. Build27 consolidates each setting
and enables the native context cleanup in both Debug and Release. Release
contracts now reject duplicate/missing definitions. No new install/remove policy,
coverage reduction, verification bypass, provider, or dependency upgrade.

## Release gate

Local release contracts PASS. Full pipeline, signed bundle, notarization, PR CI,
public assets and live website validation pending. First preflight exposed an
incomplete website generator sequence; the canonical full generator chain was
rerun before continuing. No partial output was published.

Public label stays1.0.0-beta.11; CFBundleVersion advances22 ->27. Local builds23–26
are not public releases. Artifacts will use v1.0.0-beta.11-build27.

## Signed artifact gate — PASS

Full local pipeline67/67 runners PASS (248.7s), production catalog contract PASS,
Release arm64 build/signing/notarization/stapling/Gatekeeper and ZIP/DMG launch
smokes PASS. Source1712407; later receipt/checksum-only metadata does not change
the app. Python3.12 with the pinned jsonschema test dependency was selected after
the initial system-Python preflight failure.

ZIP SHA256: ee4e4264e6c22be4ea3c57f576c8f4a2e6ccc3436c1dee19f762f2e86dc2a6b4
DMG SHA256: ffa62491b55355ff5843f4a8780856cc0ba0506a69e99813453529c51d6a5ee5
Initial PR168 CI34653709893 PASS. Final checksum commit CI and public publication
remain pending. Artifacts are Developer ID signed with public beta.11/build27,
without the local label. Public22 remains available until publication.

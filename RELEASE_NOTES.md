# Terento v1.0.0-beta.11

<!-- Public DMG SHA-256: 4f96a8e60f4ecb68cb9a5ea1ebd4490b0b65564d1659b607f1c44e60ffcd01dc -->

## What's new?

- MapRando is now available as the third catalog provider alongside Freizeitkarte and OpenTopoMap through the beta.11 API.
- Manage Maps keeps the provider's map version/date and installed size visible.
- GitHub issue reports open with the reviewed diagnostic title and body already filled in.

## Fixed

- Build 27 improves Garmin connection recovery after map operations and addresses sampled verification failures observed on fēnix 8. The owner completed MapRando Andorra and France installations with the local candidate.
- Install maps reuses catalog presentation data to reduce repeated work during search, scrolling, and provider filtering.

- Build 22 fixes Finishing stopping after two minutes while map verification was still progressing. Verification now allows continued progress, with a timeout for inactivity and a bounded overall duration.

- MapRando map packages now pass the correct raw IMG validation path before installation.

## Known issues

- Intermittent MTP/session failures can still stop an installation during Finishing; use Report issue to share the prefilled diagnostic report.

# OpenTopoMap contour shadow audit — 2026-09-06

Command:

```text
PYTHONPATH=backend/catalog-api/src python3 -m terento_catalog.opentopomap_contour_audit \
  --sample-region andorra --expected-main-count 177
```

Observed from the official OpenTopoMap source:

- main packages: `177` / expected `177`;
- unique contour sources: `176`;
- package-to-contour attachments: `179`;
- validated contour measurements: `178` attachments;
- unavailable contour attachments: `1`;
- unknown install sizes: `0`;
- shared contour sources: `1` (Canada relationship);
- minimum install size: `378,880` bytes;
- maximum install size: `4,271,505,408` bytes;
- Andorra representative sample: one Garmin IMG payload, `VALIDATED`, with
  fixed-header Garmin markers plus printable `OpenTopoMap` and `ANDORRA`
  identity tokens;
- unavailable source: `otm-saint-helena-ascension-and-tristan-da-cunha-contours.zip`,
  reported as an empty payload by the bounded ZIP inspection;
- the Canada shared source is retained as one source and must be deduplicated
  before any device write.

This is Phase 2 shadow evidence only. The public catalog remains `off`; no
provider binary is stored, mirrored, or published by this report. The
unavailable Saint Helena optional artifact remains isolated from valid main
maps and is excluded from any internal allowlist.


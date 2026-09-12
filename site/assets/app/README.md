# Website application screenshots

## September 12, 2026 refresh (local, not published)

The seven owner-supplied prepared PNGs replace the corresponding screenshot
masters without pixel edits or resizing. Each new master is 2358 × 1575 pixels
with transparent rounded corners. `maps-installed.png` retains the existing
website stem `maps-done.png` to keep the asset mapping stable.

| Placement (all six locales) | Master | Context |
| --- | --- | --- |
| Home hero | installing-maps.png | Installation progress |
| Home Install maps tab | install-maps.png | Provider and region catalog |
| Home Manage maps tab | manage-maps.png | Installed maps grouped by provider |
| Guide map selection step | map-selected.png | Search and a selected map; replaces the catalog screenshot |
| Guide completion step | maps-done.png | Completed installation |
| Download and Guide connection step | your-garmin.png | New September 12 connection screenshot, cropped and rounded to match |

`ready-to-install.png` is refreshed for future use but is not added to the
current three-step Guide. `about.png` and social artwork remain unchanged.

`scripts/optimize-app-images.mjs` produces the existing responsive AVIF/WebP
sizes (640, 960, 1280, 1600) and largest-width PNG fallback. Original masters
are unchanged; responsive derivatives use the existing resizing/compression
settings. Pass master filenames to regenerate only those screenshots without
regenerating social artwork. Full runs retain their existing social output.
The current refreshed image query version is `20260912-app-screens-v2`, owned
by `scripts/normalize-public-shell.py` and synchronized with the Guide source.
The connection screenshot now uses the same cache version.

Validation: all 11 site test runners, six-locale generator parity, structured
data checks, and existence/decoding of all 52 referenced screenshot assets pass.
Browser checks: Home (including both tabs) and Guide images load at 1440px and
390px viewport widths. Desktop Home and mobile Guide captures visually reviewed.
The six supplied prepared masters match byte for byte. The additional Your Garmin
source was cropped at (31, 94) to 2358 × 1575 and given the same 48px alpha mask;
retained RGB pixels match the original crop exactly.

This asset task does not change native behavior, release metadata, provider
support claims, or hardware evidence.

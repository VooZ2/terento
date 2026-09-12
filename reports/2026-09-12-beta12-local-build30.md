# beta.12-local build30 — persistent catalog and scroll spacing

Owner screenshot showed catalog rows touching the filter toolbar while scrolling.
Install now presents its catalog directly: the Available maps header/disclosure
and associated expanded state are removed. Filtered result count and Clear filters
sit below the search/filter controls, matching Manage maps. A12pt padding outside
the catalog scroll region matches the custom-import gap; it cannot scroll away.
Custom import disclosure, map selection, storage, Continue and all install/remove
execution and safety conditions remain unchanged.

Optimized Debug beta.12-local/build30 build PASS. Full APP24/24 runners
(32.4s) and native selection39 plus static safety guards PASS. Independent
diff review confirmed unchanged selection/action guards and callbacks. Fresh ZIP extraction, deep
strict ad-hoc signatures, exact local label/build30, arm64 and bundled library
paths PASS. Local artifact is not notarized or published; no running app was
replaced/launched and no device operations were performed.

Artifact:dist/Terento-1.0.0-beta.12-local-build30-macOS-arm64.zip.
App:dist/beta.12-local-build30/Terento.app.
SHA256:b1080d3d8a86179e0e4b3e0900f2f4b3308fa9d7d13b4584b382df166daa6e0c.
The owner should verify scrolling and the persistent gap in the local build.
Prior build29 GitHub required suites passed; new-head CI runs after push.
Public beta.11/build27 metadata is unchanged. PR173 remains a draft for UI review.

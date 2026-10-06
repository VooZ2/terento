# Vendored GPXSee subset

- Upstream: https://github.com/tumic0/GPXSee
- Commit: `65291cf455793d7d997a885301cb16f3a69cc77c` (2026-10-02)
- Licence: GNU GPL version 3 (`LICENSE`, copied from upstream `licence.txt`).
  Terento is also GPL-3.0, so the subset is distributed under the same terms.
- Copyright: Martin Tůma and the GPXSee contributors.

Only the Garmin IMG decoder and raster tile renderer are vendored, together
with the projection, geometry and text-layout code they depend on. `FILES`
lists every vendored path relative to upstream `src/`; the build compiles
every `.cpp` in that list. The files are unmodified copies.

## Updating

1. Check out the new upstream commit.
2. Recompute the dependency closure of `src/main.cpp` with the compiler
   (`g++ -MM` over the `.cpp` files in `FILES` plus any new ones the build
   needs) and refresh `FILES`.
3. Copy the listed files from upstream `src/` into `src/`, update the commit
   above, and run the renderer tests in `backend/catalog-api/tests/`.

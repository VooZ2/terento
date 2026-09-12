# BBBike backend local contract evidence — 2026-09-12

Local isolated working tree `/private/tmp/terento-bbbike-integration`; this
receipt does not claim production deployment or real Garmin hardware evidence.

## Source metadata

The official ready-region HTML inventory contains380 geographic regions and760
requested latin1 packages, including parent regions and subdivisions. The
Russia branch was excluded before traversal; no city root or other styles were
collected. All760 packages have bounded original-source metadata measurements
with exact ZIP/IMG sizes, README region/style/date, provider payload MD5 and
Garmin header evidence. The754 ordinary URLs passed the additional exact
truncated-header-prefix check; the six reviewed alternate URLs passed their
full bounded inspection. No provider binary is committed or hosted.

Cambodia, Jordan and Luxembourg each use two exact `/osm/garmin/example/` URLs
linked from their ready-region pages. These six aliases were separately
reviewed: both styles' source logfiles identify complete country PBF input;
the input bounds match the corresponding ready-region polygon bounds, with
coordinate-order normalization. README and IMG title match region/style.
This permits six exact aliases, not the example namespace generally.

380 regions ×2 types have distinct lifecycle identities after the native
uppercase/alphanumeric normalization. Geographic names are plain display text;
subdivision names include parent context. American Oceania retains unknown
country coverage (empty codes) and a supported `subregion` category rather than
inventing a country assignment.

## Automated evidence

- Backend unit suite:330 tests PASS after source cache, unavailable-package,
  exact-alias, geography, API and statistics changes.
- Disposable real PostgreSQL: all44 migrations PASS; existing catalog/source
  proof/overview/compatibility aggregation regression script PASS.
- BBBike actual six-package metadata seed/upsert, both local telemetry streams,
  replay deduplication and production aggregate exclusion PASS.
- Disposable production-classification test events resolve the two Lithuania
  package types separately while sharing geographic identity `LITHUANIA` and
  country `LT`. Untyped diagnostic fallback retains known geography without
  inventing a package/type. These events existed only in `terento_ci`.
- Actual live three-provider metadata plus finalized BBBike metadata round-trip
  through PostgreSQL: v2=FZK63+OTM177; v3=FZK63+MapRando160+OTM177;
  v4 adds BBBike760, still PAUSED. No fourth provider enters released v3.
- Strict metadata importer validation:760 packages /760 available /PAUSED PASS.
- Backend/contracts whitespace validation PASS.

The separate native task reports full760-package Swift decode/adapter/proof
validation and real Andorra ZIP acquisition-to-final-write-validator PASS.
That is automated local source evidence, not a real-device installation.

## Reproducible local outputs

Final metadata artifacts are in `/private/tmp/bbbike-source-gate/`:
`catalog-bbbike.json`, `snapshot-bbbike.json`, `db-catalog-v2.json`,
`db-catalog-v3.json`, `db-catalog-v4.json`. They contain metadata only.
The committed representative fixture is
`tests/fixtures/bbbike/representative-catalog.json` (Andorra, Lithuania, Alps;
both styles). Actual map binaries remain outside the repository.

To validate a prepared snapshot, run:

```sh
python -m terento_catalog.bbbike_snapshot snapshot-bbbike.json --expected-packages 760
```

After the separately authorized backend migration/deployment, the same command
with `--apply` imports the reviewed metadata into a PAUSED provider and records
a collection result. The command refuses a non-PAUSED provider. No provider
activation or public app/site publication is part of this receipt.

## Limits

Source header/README inspection does not verify the full compressed IMG or
provider MD5; native acquisition does that after download. No script inside an
archive is executed. Calendar update ordering is daily; a same-day republish
changes source proof but does not create an invented ordered map version.
Whole-download source drift is rejected before a device write. Device install,
reconnect, on-watch usability and real newer-release lifecycle evidence remain
owner gates. Local test rows must remain excluded from public statistics.

# Garmin device catalog

## Source and scope

The source is Garmin's official [smartwatch category](https://www.garmin.com/en-US/c/wearables-smartwatches/) and the official
category JSON endpoint used by that page. The collector runs weekly on Monday
at 03:00 UTC after the map-collection phase (currently the reference provider
collector; future provider collectors run through their reviewed adapters). It
never scrapes or fetches external sources during an API request.

The source category is the initial scope for Garmin watch/wearable discovery.
The collector does not expand into unrelated automotive, marine, cycling,
handheld, dog, or other product categories. Garmin's retail category is not a
complete historical device database, so known older models may be inserted
from separately reviewed sources.

The current official JSON request is:

```text
https://www.garmin.com/c/api/getCategoryProducts?categoryKey=10002&locale=en-US&storeCode=US&appName=www-category-pages
```

This is an implementation detail of Garmin's own category page, so a changed
response shape fails closed and preserves the previous catalog.

## Device catalog versus compatibility

`/devices/catalog.json` primarily answers: “This Garmin product exists in the
official current retail catalog.” Its additive nullable `mapCapable` field
reports only the reviewed Garmin Map Manager capability classification used by
the beta client; it is not public compatibility evidence and does not by
itself authorize a write. Compatibility status is deliberately absent from
this public contract. Retail rows are collector-managed; inactive
retail rows remain in the database for continuity, while reviewed historical
rows have `record_source = HISTORICAL_REVIEWED` and
`collector_managed = false` and are intentionally excluded from this endpoint.
The existing validated fēnix 8 USB identity (`VID 0x091e`, `PID 0x51b8`) is
stored separately and is not copied to other devices.

The historical registry in `terento_catalog.historical_devices` is versioned
and sourced from Garmin's official Connect IQ compatible-device references.
It includes fēnix 7, fēnix 7S/7X, fēnix 6 variants, epix Gen 2, and Forerunner
955. A consented evidence event can resolve to one of these rows even when
the current retail collector has never returned it. Historical rows are never
deactivated by retail absence.

The private admin view is additive and is not part of this public contract.
`/admin/devices.json` is authenticated and may include catalogue sync
metadata, map-capability state, operator support state, installation
aggregates joined by the exact canonical device record ID, and image
observability fields (`asset`, `sourceAsset`, `image`). When
`device_model.map_capable` is NULL, the admin payload classifies the
canonical model with the same Map Manager prefix list as the native client.
The HTML page may render an allowlisted `res.garmin.com` `sourceAsset` as a
thumbnail when no controlled `AVAILABLE` asset exists; that image is not
proxied by Terento. Public clients must continue to use
`/devices/catalog.json` for catalog data.

## Admin time display

Authenticated `/admin` pages keep API and storage timestamps in UTC ISO 8601,
then render them in the visitor's browser time zone by default. The header
includes a time-zone selector for manual IANA-zone changes; the choice is
stored only in that browser's local storage. This changes presentation only
and does not alter API fields, database values, or collector schedules. One
shared formatter renders admin timestamps as `YYYY-MM-DD HH:mm` in the selected
zone; the zone remains available from the selector and timestamp tooltip rather
than being repeated beside every value.

## Canonicalization

Display names retain official diacritics, for example `fēnix`. Stable identity
IDs use ASCII canonical slugs, while `canonicalModel` remains a readable ASCII
identity, for example:

```text
garmin-fenix-8-47-amoled

canonicalModel: "fenix 8"
```

The parser records explicit case sizes in millimetres and explicit display or
power labels such as AMOLED, Solar, and MicroLED. Color, band, material, and
similar cosmetic SKU differences collapse to one meaningful device record.
Functional variants such as Tactical Edition remain part of the stable ID.

If case size, display type, or part number is absent in the official source,
the corresponding field remains null. The collector does not guess values or
USB identities. Partial model-plus-size evidence must not be serialized or
matched as an exact display variant; for example, `fēnix 8 - 47mm` without
display evidence cannot claim an AMOLED-only exact variant.

## Asset policy

Garmin image URLs may appear in the official category response. The weekly
collector preserves only an HTTPS URL hosted by `res.garmin.com` as source
metadata; it does not download, mirror, or proxy the image. A production API
response can contain a Terento-controlled `asset` only when a separate,
explicit `AVAILABLE` record exists in `device_asset`
with the necessary source, license, checksum, storage, and scope metadata, and
its URL is under the same API origin `https://api.terento.app/assets/devices/`.
Supported scopes are `EXACT_VARIANT`, `MODEL_SIZE`, `MODEL`, `FAMILY`, and
`GENERIC`. A new or unillustrated device is represented as:

```json
"asset": {"status": "MISSING"}
```

The internal lifecycle is `MISSING`, `PENDING_REVIEW`, `AVAILABLE`, or
`DEPRECATED`. `PENDING_REVIEW` and `DEPRECATED` candidates are not publicly
exposed as URLs. There is no public approval route; preparation and approval
are explicit operator actions.

### Device Assets and Attribution

Images are presentation metadata used only to identify the connected device.
They are not evidence of compatibility and do not imply Garmin endorsement,
partnership, certification, or official support. The asset and compatibility
systems remain independent: an asset may be `AVAILABLE` while compatibility is
`UNKNOWN`, and a device may be `VERIFIED` while its asset is `MISSING`.

Every public `AVAILABLE` asset contains a validated source declaration:

| `asset.source.type` | `brand` | `attributionRequired` | Meaning |
| --- | --- | --- | --- |
| `OFFICIAL_PRODUCT_MEDIA` | `Garmin` | `true` | Official Garmin media used only for identification |
| `TERENTO_RENDER` | `Terento` | `false` | Terento-created visual representation |
| `GENERIC_FALLBACK` | `Terento` | `false` | Neutral fallback illustration |

The catalog-level `legal` object is shared metadata rather than repeated legal
text in every device row. The required Garmin notice is:

> Garmin and fēnix are trademarks of Garmin Ltd.
> Terento is an independent open-source project and is not affiliated with Garmin.

The macOS client reads `asset.url`, `asset.version`, `asset.scope`,
`asset.source.type`, and `asset.source.attributionRequired` from this API. If
no applicable controlled `asset` exists, it may use `sourceAsset.url` only when
the URL is HTTPS, hosted by `res.garmin.com`, and carries valid Garmin source
metadata. If `sourceAsset` is not yet present, the macOS client may derive the
same official product-media path from a validated catalog part number. The
client downloads that source image directly to the user's Mac and caches it
locally; the catalog API never relays the image. Invalid or incomplete source
metadata is ignored and the generic fallback remains. Authenticated admin HTML
pages, including `/admin/devices`, may additionally load allowlisted
`https://res.garmin.com` URLs as thumbnails so operators can verify that a
catalog row has a model-matched official product image. The catalog API still
never downloads, mirrors, or proxies those bytes.

## Asset delivery and fallback contract

The intended flow is:

```text
weekly Garmin discovery → device catalog metadata
approved asset → api.terento.app asset storage → macOS local cache
no approved asset → official Garmin sourceAsset → macOS local cache
no applicable image → generic Terento watch fallback
```

For an available asset, the client matches in this order:
`EXACT_VARIANT`, `MODEL_SIZE`, `MODEL`, `FAMILY`, `GENERIC`. Missing display or
size evidence cannot select a more-specific asset. It uses a local cache key
derived from the asset checksum, or from URL plus version when no checksum is
present. A changed version or checksum downloads a new cache entry. A missing
catalog, insufficient identity precision, failed checksum, or missing asset
always falls back to the generic Terento watch. The collector creates the
`MISSING` baseline only; asset acquisition and approval remain separate
manual operations.

## Controlled asset workflow

The `terento-catalog-asset` operator command accepts a local file or HTTPS
source, validates a normalized WebP, and writes candidates into private review
storage. `prepare` creates `PENDING_REVIEW`; `approve` atomically publishes the
validated WebP under `/assets/devices/` and changes the record to `AVAILABLE`.
The public API never serves review storage. The runtime limit is 8 MiB and
dimensions must be valid and between 1 and 16384 pixels.

## Historical evidence and inactive policy

Compatibility ingestion resolves a reviewed historical identity in the same
database transaction as event insertion. If no reviewed identity matches, the
event remains stored under its privacy-minimised textual identity instead of
being rejected because it is absent from the retail catalog. This resolution
does not grant a device write and is not consulted by the native write safety
profile.

The collector writes only current retail rows. A historical row is not part of
the collector's absence counter and remains active in the database regardless
of how many weekly retail collections omit it. Current retail rows are never
deleted automatically; a model is marked inactive only after it is absent
from three consecutive successful complete collections.

## Failure policy

The collector writes only after the category response has passed shape and
scope validation. A product-page enrichment failure keeps the successful
category record but marks that run partial. A category-source failure leaves
the previous catalog untouched and records a failed collection run.

Records are never deleted automatically. A model is marked inactive only
after it is absent from three consecutive successful full weekly collections;
partial collections do not increment that counter. Inactive records remain
available in the catalog for historical identity and future compatibility work.

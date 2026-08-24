# Catalog API contract

Base URL in production:

```text
https://api.terento.app
```

The map and device catalog routes are public read-only metadata. A separate
opt-in compatibility-evidence boundary has one validated write route and one
private authenticated operator route. No route serves map binaries.

## `POST /compatibility/events`

Accepts at most 16 KiB of allowlisted schema-version-1 JSON after client
opt-in. Event UUIDs are idempotent. Unknown fields, local paths, malformed
payloads, non-Freizeitkarte providers, and privacy-prohibited data are
rejected. The endpoint is rate limited and stores raw immutable events in the
separate compatibility tables; a repeated confirmed event records its
confirmation separately. Upload failure never changes the macOS installation
result.

## `GET /internal/compatibility/`

Returns an aggregate HTML operator view only after environment-configured
Basic authentication. It includes no-store, noindex and restrictive CSP
headers. Production must expose it only over HTTPS with edge-level
brute-force protection. Raw event payloads are not displayed by default.

## `GET /health`

Returns HTTP 200 when the service can reach PostgreSQL:

```json
{"status":"ok"}
```

Returns HTTP 503 and `{"status":"error"}` when the database is unavailable.
Responses use `Cache-Control: no-store`.

## `GET /maps/catalog.json`

Returns catalog version 1. The response contains the latest known metadata for
all currently indexed Freizeitkarte Garmin packages. The collector indexes
official regional pages and keeps the original provider download URL; the API
does not download or proxy the package.

```json
{
  "catalogVersion": 1,
  "updatedAt": "2026-08-21T06:27:14Z",
  "providers": [
    {
      "id": "freizeitkarte",
      "name": "Freizeitkarte",
      "website": "https://www.freizeitkarte-osm.de/garmin/en/mitteleuropa.html",
      "attribution": "Map data © OpenStreetMap contributors; produced map © FZK project",
      "licenseURL": "https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
      "licenseInformation": "...",
      "maps": [
        {
          "id": "freizeitkarte-ltu",
          "region": "LTU",
          "name": "Lithuania",
          "country": "Lithuania",
          "version": {"year": 2026, "month": 5},
          "downloadSizeBytes": 361187697,
          "installSizeBytes": 429793280,
          "sizeBytes": 361187697,
          "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/LTU+_en_gmapsupp.img.zip",
          "releaseDate": "2026-05-03",
          "identifier": "LTU+"
        }
      ]
    }
  ]
}
```

The example shows one map entry for brevity; the verified live source dry-run
on 2026-08-21 produced 63 current Freizeitkarte Garmin map entries, with 63
known download sizes and 63 known final IMG install sizes.

The client-compatible package list contains only records with a normalized
version and a known download size. `sizeBytes` remains the backwards-compatible
package-size field. New clients must use `downloadSizeBytes` for
archive/network sizing and `installSizeBytes` for final Garmin storage sizing.
`installSizeBytes` may be `null`; `null` is unknown and must not be treated as
zero or as the download size. The macOS storage gate blocks until it has a
measured final IMG size. The client still validates the extracted IMG before
installation even when the catalog provides this metadata.
`sourceURL` is always an original provider URL. The API never fetches that
archive for the client and never streams its bytes.

The collector uses the release page as the provider-wide version signal. For
each official regional page it selects the English Garmin package when
available, otherwise the first published language variant. It validates the
archive byte length with `HEAD` when available and reads only bounded ZIP tail
and central-directory `Range` sections from the original provider URL to find
the selected `.img` entry's uncompressed size. It never downloads the full
archive to the VPS. If Range is unavailable or the ZIP is malformed, the
download size may remain known while `installSizeBytes` remains unknown; a
diagnostic is stored and the previous known-good value is preserved. A full
collection failure does not clear the previous known-good catalog.

Successful responses include:

```text
Cache-Control: public, max-age=300, stale-while-revalidate=86400
ETag: "<sha256>"
Last-Modified: <HTTP date>
```

Clients should send `If-None-Match` or `If-Modified-Since` and accept HTTP 304.
The `catalogVersion` value changes only for an intentional contract change;
adding optional metadata fields does not require a version bump.

## `GET /devices/catalog.json`

Returns catalog version 2 for the separate Garmin device catalog. Records are discovered from the
official smartwatch category and do not mean that Terento has tested or
supports the model. The retail source is not a complete historical Garmin
database; inactive historical records can remain in the response.

```json
{
  "catalogVersion": 2,
  "updatedAt": "2026-08-21T06:27:14Z",
  "legal": {
    "manufacturerNotice": true,
    "text": "Garmin and fēnix are trademarks of Garmin Ltd. Terento is an independent open-source project and is not affiliated with Garmin."
  },
  "devices": [
    {
      "id": "garmin-fenix-8-47-amoled",
      "manufacturer": "Garmin",
      "family": "fenix",
      "familyName": "fēnix",
      "model": "fēnix 8",
      "canonicalModel": "fenix 8",
      "variant": "47 mm, AMOLED",
      "caseSizeMm": 47,
      "displayType": "AMOLED",
      "partNumber": "010-02904-10",
      "productURL": "https://www.garmin.com/en-US/p/1228429/",
      "active": true,
      "asset": {
        "status": "AVAILABLE",
        "url": "https://api.terento.app/assets/devices/garmin/fenix-8-47-amoled.webp",
        "version": 1,
        "scope": "MODEL_SIZE",
        "source": {
          "type": "OFFICIAL_PRODUCT_MEDIA",
          "brand": "Garmin",
          "attributionRequired": true
        }
      },
      "sourceAsset": {
        "url": "https://res.garmin.com/en/products/010-02904-10/g/cf-lg.jpg",
        "scope": "MODEL",
        "version": 1,
        "attribution": "Garmin official product media",
        "source": {
          "type": "OFFICIAL_PRODUCT_MEDIA",
          "brand": "Garmin",
          "attributionRequired": true
        }
      }
    }
  ]
}
```

`caseSizeMm`, `displayType`, and `partNumber` may be `null` when the official
source does not provide the field. `asset` is always present in version 2 and
is either `{ "status": "MISSING" }` or an `AVAILABLE` asset. An optional
`sourceAsset` contains only allowlisted official Garmin media metadata and is
not a Terento-hosted binary. Review and
deprecated states are never exposed as public URLs. An available asset has a
scope of `FAMILY`, `MODEL`, `MODEL_SIZE`, `EXACT_VARIANT`, or `GENERIC`, a
valid `source` declaration, a version, and an optional checksum under the same API domain:
`https://api.terento.app/assets/devices/`. A discovered device remains catalog
metadata only and never becomes a compatibility or support claim.

### Device Assets and Attribution

Device images are used only for device identification and a better display of
the connected hardware. They do not indicate endorsement, partnership,
certification, or official support. Asset availability never changes the
separate compatibility evidence status (`UNKNOWN`, `TESTING`, `TESTED`,
`SUPPORTED`, or `VERIFIED`).

The `asset.source` object uses exactly one of these source types:

- `OFFICIAL_PRODUCT_MEDIA` — official Garmin product media used only for
  identification; `brand` is `Garmin` and `attributionRequired` is `true`.
- `TERENTO_RENDER` — a Terento-created visual representation; `brand` is
  `Terento` and `attributionRequired` is `false`.
- `GENERIC_FALLBACK` — the neutral Terento fallback illustration; `brand` is
  `Terento` and `attributionRequired` is `false`.

The top-level `legal` object is reusable global metadata. For Garmin product
media, clients must show or make available the following notice:

> Garmin and fēnix are trademarks of Garmin Ltd.
> Terento is an independent open-source project and is not affiliated with Garmin.

The macOS app consumes the controlled `asset` first. If that is missing, it
may consume `sourceAsset.url`, or derive the documented Garmin product-media
URL from a validated catalog `partNumber`, only after validating the HTTPS
`res.garmin.com` origin and Garmin attribution metadata. The image is fetched
directly by the Mac and cached locally; the API does not proxy or host it. A
missing or invalid asset/source falls back to the generic Terento watch
illustration.

The device endpoint supports the same public cache policy as the map endpoint:
`ETag`, `Last-Modified`, `Cache-Control: public, max-age=300,
stale-while-revalidate=86400`, and conditional GET responses with HTTP 304.

The device catalog is metadata only. It has no route for connected-device
identifiers and it does not authorize MTP operations, map installation, or
ownership decisions. Those decisions remain local to the macOS client and its
compatibility/manifest layers.

## `GET /assets/devices/<asset>.webp`

Serves only validated WebP runtime assets from the same `api.terento.app`
origin. Assets use a long-lived immutable cache policy and an SHA-256 ETag.
Review storage, source images, arbitrary files, and traversal paths are not
served.

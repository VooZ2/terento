# Catalog API contract

Base URL in production:

```text
https://api.terento.app
```

The map and device catalog routes are public read-only metadata. A separate
opt-in compatibility-evidence boundary has one validated write route, one
private authenticated operator route, and a default-disabled reviewed public
aggregate route. No route serves map binaries.

## `POST /compatibility/events`

Accepts at most 16 KiB of allowlisted schema-version-1, schema-version-2, or schema-version-3 JSON after client
opt-in. Event UUIDs are idempotent. Unknown fields, local paths, malformed
payloads, non-Freizeitkarte providers, and privacy-prohibited data are
rejected. A random per-event deletion token is required; older beta payloads
without one are rejected rather than retained without a self-service deletion
credential. The endpoint is rate limited and stores allowlisted columns in the
separate compatibility table. The original JSON body is not retained; only
the approved fields and a SHA-256 hash of the event deletion token are stored.
New clients do not send a post-install
confirmation signal; legacy `userConfirmed` fields are tolerated only for
backward compatibility with older beta clients. Upload failure never changes
the macOS installation result.

Version 2 events may include an exact `compatibilityIdentity`, `variant`,
`caseSizeMm`, privacy-safe `displayType`, and `canonicalDeviceId`, plus
optional `reconnectVerified` and `mapVisibleAfterReconnect` observations.
Older beta clients remain accepted when the newer identity fields are absent;
such model-only evidence must not be matched to a sibling exact variant.
Reconnect is never required for any compatibility status. The canonical
aggregate groups by `canonicalDeviceId` when available and uses exact
`compatibilityIdentity` only as the fallback for older uncanonicalized events.
It then uses the successful opt-in installation count: `TESTING` for zero successful installations on
recognized map-capable evidence, `TESTED` for 1–2, `SUPPORTED` for 3–4, and
`VERIFIED` for 5 or more. Failed reports, opt-out local installs, and duplicate
event IDs do not increase the successful count. Firmware variation, physical
device count, operator review, reconnect, and map visibility are retained only
as optional evidence dimensions and do not promote a status.

Version 3 groups all map results from one Install press under a random
`operationId` and records the exact app release/build plus controlled failure
stage/code, write/remote-object/cleanup booleans, and a coarse transfer
progress bucket. It may also record the sanitized raw MTP model label and one
allowlisted identity-source category (`MTP_SERIAL`, `GARMIN_UNIT_ID`, or
`UNAVAILABLE`) without the identifier value. It never accepts raw native messages, local paths, object
IDs, manifests, hashes, serials, Unit IDs, or local watch keys. Selected maps
not reached after an earlier failure use `NOT_STARTED`. Download, extraction,
source-validation, and preflight failures remain visible in the private
operation detail but `writeStarted=false` excludes them from device
compatibility rates. Compatibility thresholds count distinct write-started
operations, not child map rows; a multi-map operation succeeds only when all
of its selected map results verify. Legacy events remain one operation each.

## `DELETE /compatibility/events`

Accepts the event UUID and its 64-character deletion token. The service hashes
the supplied token and deletes the matching event. A missing event and an
incorrect token both return the same not-found response. This prevents the
event UUID alone from authorizing deletion. The route is rate limited and the
client keeps deletion tokens locally; the server stores only their hashes.

Compatibility events older than 24 months are pruned from the active database
by the service health cycle.

## `GET https://api.terento.app/admin`

Returns an aggregate HTML operator dashboard after database-backed login. The
dashboard uses the Terento branded English admin shell, exact model/variant
columns, compact evidence metrics, and client-side search/status/sort controls;
these controls do not change backend aggregation. The first administrator can
be created only once through `/admin/setup` with the environment-provided
bootstrap secret. Passwords use salted PBKDF2-SHA256;
opaque sessions and CSRF values are stored only as SHA-256 hashes. Cookies are
Secure, HttpOnly, SameSite=Strict, and scoped to `/admin`. Login/setup attempts
are rate limited. Pages include no-store, noindex and restrictive CSP headers.
The error count links to a private per-operation detail with child map results,
release/build, raw MTP model label, identity-source category, failure stage and
allowlisted codes. Current error counts and compatibility rates exclude
resolved historical failures. Those events remain available in a separate
`Resolved / historical diagnostics` section with their resolution reason. Raw
event payloads and raw diagnostic text are not displayed. `/internal/compatibility/` redirects to
this route for the earlier local implementation.

## `GET https://api.terento.app/admin/campaign-links`

Returns the authenticated operator's local Campaign link builder. It is a
client-side tool: no campaign links, history, or analytics data are stored and
no campaign-link API is exposed. The builder restricts destinations to
`terento.app`, normalizes UTM values, replaces existing UTM parameters, and
keeps the canonical parameter order `utm_source`, `utm_medium`,
`utm_campaign`, `utm_content`, `utm_term`. The page uses the same private
admin session, CSRF cookie, no-store response policy, and noindex policy as
`GET https://api.terento.app/admin`.

## `GET https://api.terento.app/admin/devices`

Returns the authenticated Garmin device observability page. The page is
limited to Garmin catalog records and combines catalog metadata, map
capability, separate installation authorization, exact-ID installation
aggregates, approved cached assets or allowlisted Garmin `sourceAsset`
thumbnails, and latest successful sync metadata. Map-capable Yes/No uses a
stored `device_model.map_capable` value when present; otherwise the page
classifies the canonical model with the same Map Manager prefix list as the
native macOS client. Unknown remains only for models outside that list. The
page keeps the dense list paginated in the browser and opens a detail dialog
for technical fields, including which image origin was used
(controlled Terento asset vs official Garmin product media).

`GET https://api.terento.app/admin/devices.json` returns the same additive
data as JSON for admin tooling. The endpoint uses the existing admin session,
is no-store/noindex, and joins installation events only through
`canonical_device_model_id`. It is not part of the native or public device
catalog API contracts.

The page labels the operator field `Installation authorization` and shows a
separate, classifier-derived `Compatibility status`. The visible values are
Pending, Approved, and Blocked; the existing internal enum remains
`NOT_EVALUATED`, `SUPPORTED`, or `UNSUPPORTED`. CSRF-protected
`POST /admin/devices/authorization` (with the legacy `/admin/devices/support`
alias retained) updates only `device_model.support_status` and records an
audit entry. It cannot change evidence events, operation-level install counts,
compatibility status, or any native device write authorization.

`POST /admin/diagnostics/resolve` and `/admin/diagnostics/reopen` change only
the retained diagnostic lifecycle, while `POST /admin/diagnostics/identity`
assigns or leaves an exact canonical Garmin record and writes an identity audit
entry. Neither action deletes evidence or changes the original install
outcome. Admin counts are grouped by distinct install operation, not raw
per-map evidence rows.

## `GET /compatibility/public/top-models.json`

Prepared for a later public TOP-models widget. The route returns 404 unless
`PUBLIC_COMPATIBILITY_STATS_ENABLED=true`. Even then, it includes only model
rows that an operator has separately marked `APPROVED` and enabled for public
statistics. Results are ordered by successful installation count and include
attempted, successful, failed, canonical model, exact identity, case size,
display type, canonical device-catalog ID, map-capability, last-evidence, and
canonical-status fields; firmware and raw event records are omitted. All
four canonical statuses may be public after review. The native macOS client
continues to use this existing route. The public website uses the additive
`/compatibility/public/models.json` projection below. The endpoint remains
default-disabled and the page shows no public evidence when the flag or
approved aggregate data is absent.

The response's `evidenceStatus` is the authoritative public status for the
exact `compatibilityIdentity`. It is one of `TESTING`, `TESTED`, `SUPPORTED`,
or `VERIFIED`; non-map devices are not represented by a compatibility status.
`canonicalModel`, `caseSizeMm`, `displayType`, `variant`, and
`canonicalDeviceId` identify the exact reviewed catalog variant. Clients must
not fall back from a sized row to a model-only or sibling-size row. The native macOS client
refreshes this endpoint after device discovery, stores only a bounded
exact-identity cache for offline presentation, and uses a neutral unavailable
UI when neither a current response nor a recent cached canonical result is
available. A transport/install registry or write-safety decision must not
change `evidenceStatus`.

The production website and native macOS client request `limit=500` before
performing exact-identity matching. Clients must not rely on the route's
smaller default result page to represent the complete reviewed catalog.

The reviewed Garmin `091e:51b8` hardware identity is associated separately
with `garmin-fenix-8-47-amoled` and may therefore match that exact public row
when MTP omits the display token. This is reviewed identity evidence, not an
inference from case size or artwork. An unreviewed 47 mm identity without
display evidence must not match either the AMOLED or Solar row, including via
the native offline cache.

## `GET /compatibility/public/models.json`

Additive evidence-first projection for the public Compatibility page. It uses
the same default-disabled flag and `APPROVED`/`public_statistics_enabled`
review gate as the existing route, but it is a separate contract so the
website does not need to join the retail device catalog. Historical evidence
rows can therefore appear even when Garmin no longer lists that model in its
current retail category. The response contains exact identity, evidence
counts, `evidenceStatus`, family/variant display metadata, and an `image`
object. `image` follows controlled Terento asset → allowlisted Garmin
`garmin-source` URL → the neutral Terento `fallback` image at
`https://terento.app/assets/generic-garmin-watch.png`. The fallback is
presentation-only and does not indicate a model match or compatibility.

This endpoint does not expose `supportStatus`, operator review decisions,
transport profiles, write authorization, Unit IDs, or raw event data. The
website uses only `evidenceStatus` for its compatibility badge. Existing
native/web clients are not required to call this endpoint, and
`/devices/catalog.json` remains unchanged.

## `GET /health`

Returns HTTP 200 when the service can reach PostgreSQL:

```json
{"status":"ok"}
```

Returns HTTP 503 and `{"status":"error"}` when the database is unavailable.
Responses use `Cache-Control: no-store`.

## `GET /maps/catalog.json`

Returns catalog version 1. The response contains the latest known metadata for
all currently indexed downloadable Freizeitkarte Garmin packages. The collector indexes
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
          "id": "freizeitkarte-deu",
          "region": "DEU",
          "name": "Germany",
          "country": "Germany",
          "version": {"year": 2026, "month": 5},
          "downloadSizeBytes": 361187697,
          "installSizeBytes": 429793280,
          "sizeBytes": 361187697,
          "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/DEU+_en_gmapsupp.img.zip",
          "releaseDate": "2026-05-03",
          "identifier": "DEU+"
        }
      ]
    }
  ]
}
```

The example shows one map entry for brevity; the current snapshot contains 63
Freizeitkarte Garmin map entries. The provider catalog may change after that
date.

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
separate compatibility evidence status (`TESTING`, `TESTED`, `SUPPORTED`, or
`VERIFIED`).

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

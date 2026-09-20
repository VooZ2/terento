# Shared public JSON contracts

These Draft 2020-12 schemas describe current public payloads, not database
models. They are canonical contract documentation and test inputs; production
Python, Swift and JavaScript do not load JSON Schema validators.

| Schema | Public payload | Body version |
| --- | --- | --- |
| `map-catalog.schema.json` | `GET /maps/catalog.json` | `schemaVersion: 2`, legacy `catalogVersion: 1` |
| `map-catalog.schema.json` | `GET /maps/catalog-v3.json` | same body versions; Freizeitkarte, OpenTopoMap, MapRando |
| `map-catalog.schema.json` | `GET /maps/catalog-v4.json` | same body versions; adds BBBike and its two map types |
| `device-catalog.schema.json` | `GET /devices/catalog.json` | independent `catalogVersion: 2` |
| `compatibility-event.schema.json` | `POST /compatibility/events` request body | accepted versions 1–4; current emitter uses 4 |
| `map-event.schema.json` | `POST /map-events` request body | `schemaVersion: 1` |

HTTP authentication, idempotency and rate-limit headers are outside these body
schemas. Schema versions are independent of Terento app versions and build
numbers. Relative `$id` values identify files within this directory; `$ref`
values resolve only to local `$defs`. No schema or fixture needs network access.

Statistics populations, formulas, deduplication and historical interpretation
are canonical in [`STATISTICS_CONTRACT.md`](STATISTICS_CONTRACT.md). The
contract distinguishes terminal provider acquisitions, fresh main-map results,
optional components and updates; it does not authorize a production migration
or claim complete telemetry coverage.

## Responses and client compatibility

The current beta.12 client requests `/maps/catalog-v4.json`. The legacy route
retains Freizeitkarte and OpenTopoMap; v3 additionally exposes MapRando.
Older clients can reject a complete snapshot containing an unknown installable
provider, so these projections must remain separate. v4 additionally exposes
BBBike with `bbbike-latin1` and `ontrail-latin1` map types. Catalog body versions
remain unchanged. Source activation and exact-model evidence are separate.
MapRando/BBBike versions may include an optional day; legacy provider versions
retain their existing meanings.

`released-catalog-clients.json` pins a published source revision for each route.
Daily and deployment checks run those exact native decoders, independently of
the current beta checkout. This is source-client compatibility evidence, not
an execution of a downloaded notarized app or a real Garmin transfer.

Response objects permit unknown additive fields, including nested objects.
`required` lists specify the serialized response contract. They do not impose
new requirements on existing clients. Optional properties can be absent;
nullable properties explicitly permit JSON null. Map-level `sizeBytes` retains
the legacy download/package meaning; artifact-level `sizeBytes` is the final
image size or null. `downloadSizeBytes` and `installSizeBytes` are distinct.

The bundled native `Resources/Maps/catalog.json` is deliberately the legacy
`catalogVersion: 1` decoder projection, without public `schemaVersion: 2` and
some API fields. It is not validated against the public response schema or
rewritten to match it. Swift tests decode it through the unchanged loader.
The native decoder also tolerates an omitted public `schemaVersion`; the
shared missing-schema-version fixture therefore fails JSON Schema but still
decodes in Swift. Missing `providers` fails native decoding, while the website
retains its static fallback. Missing device `canonicalModel` fails decoding.

Website provider cards consume the map catalog. The Compatibility page uses
`/compatibility/public/models.json`, a separate payload outside these four
contracts. No website consumer of the device catalog is introduced here.

## Event strictness and privacy

Event schemas use the existing server field allowlists and reject additional
properties. Do not add Unit IDs, serials, accounts, local paths, raw logs, map
binaries, arbitrary metadata or persistent device identifiers. `id` and
`operationId` are random event/operation identifiers. `canonicalDeviceId` is a
public model identity. `identityResolutionCode` reports a method name only.
Custom IMG compatibility events use coarse `custom` labels; map events exclude
custom imports. No change to collection defaults, retention or privacy policy
is authorized by these schemas.

Current map events and compatibility diagnostic versions 3–4 require a strict
SemVer `releaseLabel`. A valid label ending exactly in `-local` is classified
server-side as local test telemetry; it is excluded from production aggregates
and can only be purged through the authenticated admin test-data flow.
Compatibility versions 1–3 retain the historical `deletionToken` field; version
4 forbids it. This documents old request acceptance, not a restored deletion
feature. Versions 3–4 check structured diagnostic types and consistency.
The existing server does not validate those diagnostic fields on versions
1–2; the schema records this legacy limitation rather than silently tightening
the API. Clients must not exploit that gap to transmit extra diagnostic data.
A future tightening requires its own privacy/compatibility review.

Some checks remain procedural: raw JSON byte limits (16 KiB compatibility,
8 KiB map events), Python UUID normalization, accepted ISO timestamp syntax,
and `mapResultIndex < selectedMapCount`. Map timestamps require a timezone;
legacy compatibility timestamps do not. Standard schema validation alone is
not equivalent to server acceptance. Tests also call the existing validators.
The map server's equality comparison currently accepts JSON `true` as version
1; the schema records that behavior without changing the runtime. Compatibility
versions explicitly reject booleans. These are documented existing limits,
not new allowed data uses.

## Changing a contract

1. Inspect the serializer, validator, API documentation and existing consumers.
2. Add an optional response field for additive evolution; coordinate server and
   client handling for breaking fields, versions or semantics. Do not use app
   release numbers as API versions.
3. Update the schema, descriptions and its explicit `required` list. Event fields
   require privacy review and the existing server allowlist to agree first.
4. Update shared fixtures and Python/Swift/website expectations as applicable.
   Run backend, native, app, site and shared/CI suites. Schema/fixture changes under `contracts/` select every suite, including release
   checks; prose-only Markdown changes use the documentation/CI checks.
5. Review canonical architecture/state and public documentation in the same
   change. Keep local-only `internal/` documentation out of public commits.

Fixtures in `contracts/fixtures/` are read directly by Python, Swift and Node
tests. They contain synthetic event IDs and public retail model metadata, never
real user/device identifiers. They are not copied into package resources or
language-specific directories. Invalid filenames identify the intended error;
backend tests assert the error keyword and location, not just any failure.

Local test setup:

```sh
python3 -m pip install -e 'backend/catalog-api[test]'
Tests/run-all-tests.sh
```

Backend tests validate real serializer outputs, shared fixtures, legacy request
versions, privacy rejection examples and procedural checks. Swift tests exercise
current decoders, additive fields and bundled fallback; Node tests execute the
actual provider-card script with mocked DOM/fetch and shared map fixtures.

## Optional XML model metadata and server identification

Compatibility events accept optional `garminModelDescription` (1–160 Unicode
code points, no control characters or local paths) and
`garminModelPartNumber` (1–64 ASCII letters, digits or hyphens). The latter is
the literal Model/PartNumber field, commonly `006-B…`; it is not a retail
`010-…` SKU. Existing v1–v4 requests remain valid. Invalid optional app fields
are omitted; whole XML, Unit ID and serial numbers remain excluded.

Device catalog v2 adds nullable `screenTechnology` (`AMOLED`, `MicroLED`,
`MIP`), `solar` and `inReach`. Legacy `displayType`, representative
`partNumber`, IDs and status criteria remain compatible. Null is unknown,
never false. The identity mapping registry is server-side and is not sent to
clients. A reported `canonicalDeviceId` is a candidate, never assignment
permission: the server evaluates all five identity checks before resolving it.

An actually observed `010-…` XML value uses the separate retail SKU registry;
`006-B…` uses the XML/Connect IQ registry. Source-derived properties share their
provenance and never count as independent observations.

The `map-event.valid-acquisition.json` fixture is consumed by the Swift event
runner and Python schema checks. Optional paired acquisition/component fields
and processing/cancellation/interruption phases extend schema1; legacy fixtures
remain unchanged and accepted. Server UUID and outcome validation remains the
intake boundary. No raw device or file identity is added.

### Operation failure fixture

`fixtures/compatibility-event.valid-failed-operation.json` is a deterministic
synthetic fixture from the Swift InstallationEvidenceEvent encoder for an
operation-owned failed installation. The event schema adds the controlled
`INSTALL_FAILED_UNKNOWN` failure code for genuinely unclassified failures and
the optional-component outcome fields; no private data is added. The API must accept this code
before the corresponding client is published. Backend delivery tests can also
consume fresh native fixture output through `TERENTO_DIAGNOSTIC_FIXTURE_OUTPUT`.

Cross-component changes and releases must follow
[APP_API_RELEASE_CONTRACT.md](APP_API_RELEASE_CONTRACT.md), including generated
Swift payload tests, accepted-code parity and API-before-client publication.

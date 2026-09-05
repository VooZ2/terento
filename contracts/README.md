# Shared public JSON contracts

These Draft 2020-12 schemas describe current public payloads, not database
models. They are canonical contract documentation and test inputs; production
Python, Swift and JavaScript do not load JSON Schema validators.

| Schema | Public payload | Body version |
| --- | --- | --- |
| `map-catalog.schema.json` | `GET /maps/catalog.json` | `schemaVersion: 2`, legacy `catalogVersion: 1` |
| `device-catalog.schema.json` | `GET /devices/catalog.json` | independent `catalogVersion: 2` |
| `compatibility-event.schema.json` | `POST /compatibility/events` request body | accepted versions 1–4; current emitter uses 4 |
| `map-event.schema.json` | `POST /map-events` request body | `schemaVersion: 1` |

HTTP authentication, idempotency and rate-limit headers are outside these body
schemas. Schema versions are independent of Terento app versions and build
numbers. Relative `$id` values identify files within this directory; `$ref`
values resolve only to local `$defs`. No schema or fixture needs network access.

## Responses and client compatibility

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
   Run backend, native, app, site and shared/CI suites. Changes under `contracts/`
   select every suite, including release checks.
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

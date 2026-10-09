# Native installation authorization

This is the canonical product decision for starting or continuing a native map
write. The API device catalog, not public Compatibility or the local Map Manager
presentation registry, owns the capability decision. The backend policy is live:
the 2026-09-24 read-only check returned HTTP 200 with schemaVersion 3 and
policyVersion 3. Native enforcement is distributed in beta.14 build 35 from
packaged source `19d465dc97c53198dff3ec10c4cd73dad13fa2df`; beta.13 did not
enforce this policy. The published ZIP and DMG passed signing, notarization,
launch checks and independent published-asset checksum verification.

The client must identify the connected Garmin manufacturer and a reliable,
normalized **base model** without substring or broad family matching. Collect
all active catalog rows for that base model, then use reliable variant facts
only to narrow the candidate rows. Evaluate variant attributes independently.
If evidence for a variant attribute conflicts, treat that attribute as unknown
and do not filter on it. **Conflicting variant evidence broadens the candidate
set. It does not by itself deny authorization. Authorization is determined from
the Maps capability of all remaining possible candidates.** A conflict in
manufacturer or base-model identity itself is unreliable and must produce
`PENDING`; it is not a variant conflict. `catalogDeviceID` is only a hint and
cannot choose or narrow candidates by itself. Missing case size, display,
Solar, or inReach information does not prevent approval if every plausible
active candidate has `mapCapable=true`. All candidates with Maps=Yes produce
`APPROVED`; all with Maps=No produce `BLOCKED`; mixed candidates or any NULL
capability produce `PENDING`. An unknown base model or no candidates is
`PENDING`, with no write. Inactive rows never confer approval; `active=false`
is reserved for a deliberate withdrawal, and no routine path sets it. A
collector-managed model that leaves Garmin's current category is **retired from
retail, not deactivated**: after three consecutive successful complete weekly
collections without it, it keeps `active=true` and its stored Maps value, so
owners of discontinued watches (for example fēnix 8, Enduro 3, quatix 8 once
Garmin stops selling them) keep the same decision. Retirement is the
`consecutive_missed_collections >= 3` counter, shown in Admin as "Retired from
retail"; a model seen again is current retail. A policy
endpoint failure, missing route, or invalid response is `CATALOG_UNAVAILABLE`,
also with no write. This is a temporary verification failure, not evidence of
permanent incompatibility.

**Generation-label base-model aliases.** Some watches report a whole model name
without the generation label of the catalog model. The server owns the fix, so
released clients need no change. `GENERATION_LABEL_BASE_MODEL_ALIASES` in
`backend/catalog-api/src/terento_catalog/installation_policy.py` is a small,
reviewed table of exact, whole normalized base-model names. For each alias, the
policy response also contains one alias row for every catalog row of the target
base model, including inactive rows and rows with a NULL or `false` Maps value.
An alias row is a copy of its target row. Only `baseModel` (set to the alias)
and `id` (the target id plus `@alias-<alias>`) differ. Thus `active`,
`mapCapable`, `scope`, `installationAuthorization` and the variant facts stay
bound to the real row. The same candidate, variant-narrowing and capability
rules apply to the alias, so a NULL, `false` or inactive target gives the same
`PENDING` or `BLOCKED` result. An alias never uses family, prefix or substring
matching, and it never changes any other base model. If real catalog rows
already have the alias base model, the alias is not applied. Every other unknown
base model stays `PENDING`. Released clients (beta.14 build 35 to rc.2 build 42)
reject duplicate policy ids. They use the id only for that check: they do not
match on it, persist it, log it, upload it or report it. For this reason alias
rows need their own ids, and these ids cannot reach evidence, reports or
statistics. Alias rows
add no fields to schema 3 and do not change `policyVersion`. Clients fetch the
policy fresh for each decision (`no-store`), so the next check sees them. Add an
alias only when repository evidence shows that the watch reports that name and
Garmin sold exactly one generation under it. Current table: reported `epix Pro`
(`EPIX PRO`, `epix Pro 51mm`) → `epix pro gen 2`. Garmin sold only one epix Pro
generation, catalogued as "epix Pro (Gen 2)", so the reported name cannot mean
another product. Plain `epix` is not an alias because Garmin sold an original
epix and epix (Gen 2); it is a real catalog row for the original epix (see
below), so a watch that reports plain `epix` is decided by that row (Maps=Yes).
Both epix generations have maps, so the result is the same for either. The
MARQ (Gen 2) lines are not aliased because first-generation MARQ editions exist
under the same names; those first-generation names are real Maps=Yes rows, so
a Gen 2 watch that reported a plain first-generation name would also be
approved correctly. Edge models stay absent and `PENDING`.

The public Compatibility directory and its `TESTED`/`SUPPORTED`/`VERIFIED`
evidence categories, `successfulInstallations`, Admin `support_status`, and
prior successful installs neither grant nor revoke write authority. Catalog
`mapCapable` is the stored nullable value; separately observed or inferred
map capability is diagnostic evidence only. The current Garmin Edge models
are absent from the API catalog and therefore `PENDING`, not permanently
unsupported. A future reliably identified, active Edge catalog model with
Maps=Yes follows the same rule without a dedicated blacklist, whitelist, or
feature flag. Public product claims remain independently evidence-gated.

The stored catalog Maps value of a **new** collector-managed model comes only
from the official Garmin product specifications the collector already reads:
an explicit `yes` on a map-support row (`Built-in mapping`, `Full vector map`,
`Ability to add maps`, `Preloaded maps`, `TopoActive maps`, `Maps`,
`Map support`) stores `true`; an explicit `no` on a whole-support row
(`Built-in mapping`, `Full vector map`, `Ability to add maps`, `Maps`,
`Map support`) with no conflicting `yes` stores `false`. The row lists are
`MAP_POSITIVE_ROWS` and `MAP_NEGATIVE_ROWS` in
`backend/catalog-api/src/terento_catalog/collectors/garmin/specifications.py`;
change both together. Current Garmin pages use `Built-in mapping` and
`Full vector map` (for example fēnix 8 and Venu X1); pages that show neither
(for example Forerunner 570, vivoactive 6, Instinct 3) stay Unknown; missing, conflicting or per-SKU-disagreeing
information stores NULL (Unknown → `PENDING`). A model-name prefix never stores
a value, so a future maps-capable model in a family the native display registry
calls non-map (for example a new Venu) is never silently `BLOCKED`. The
evidence row, source page and check time are recorded in
`specification_evidence.map_capable`. A stored `true`/`false` (reviewed,
backfilled or set by an administrator) is never replaced by the collector; an
Unknown row may be filled later from the same specification evidence.
Administrators still set Maps manually; Devices filtered to `Maps: Unknown`
and active models (`/admin/devices?maps=unknown&active=1`) lists active models
whose value is Unknown.

**Reviewed catalog additions and Maps decisions (owner, 2026-10-09).**
Migration 075 applies these decisions; the per-row evidence is stored in
`specification_evidence.map_capable` and listed in
`backend/catalog-api/docs/schema.md`.

- *Missing map-capable models.* Map watches that Garmin no longer sells, or
  whose reported name is a different base model from the existing row, are
  added as active `HISTORICAL_REVIEWED` rows with Maps=Yes, never as aliases.
  Each needs an official Garmin source that states map support: a product
  specification row (`Built-in mapping`, `Full vector map`, `Preloaded road and
  trail maps`, `Moving map …`, or the Japanese `地図のダウンロード機能` /
  `フルベクトル地図` rows), or the owner's manual Map topic ("comes preloaded
  with maps" / "can display … Garmin map data"). The `model` label is chosen so
  its base model equals the name the watch reports. Rows added: quatix 7 Pro,
  D2 Mach 1 Pro, Forerunner 945 LTE, quatix 6X and 7X (Solar), Descent Mk2S and
  Mk2i, MARQ Adventurer/Athlete/Aviator/Captain/Commander/Driver/Golfer/
  Expedition (first generation), D2 Delta/Delta S/Delta PX/Charlie, fēnix 5S
  Plus and 5X Plus, epix (original), tactix 7 – Pro / Pro Ballistics /
  Standard Edition, MARQ (Gen 2) Commander/Athlete/Golfer – Carbon Edition and
  Adventurer – Damascus Steel Edition, fēnix 8 Dual Power (47/51 mm), quatix 6X
  Dual Power, Forerunner 955 Dual Power, and quatix 8 Pro 51 mm (listed by
  Garmin's Connect IQ device list; Maps from the quatix 8 Pro specifications).
  The fēnix 6 family is end of life: its rows stay exactly as they are and no
  fēnix 6 Pro or fēnix 6 Dual Power rows are added. Edge, handheld and
  non-map products are not added. Current-category models (for example
  Enduro 4, Approach S72) are added by the weekly collector from their
  specification rows.
- *Golf watches (pending owner review).* On Approach watches the
  `Full vector map: yes` row (for S44 and S50 `yes (with Garmin Golf
  membership)`) sits in the golf section of the specification table and
  appears to describe golf-course maps, not general map support. Golf-section
  map rows are pending a separate owner decision and do not change stored
  values: every Approach row keeps its current stored Maps value (`false`),
  and migration 075 does not touch them.
- *Reviewed Maps=No.* The collector stores Unknown when a page has no map row.
  As a reviewed owner decision, Bounce 2, D2 Air X15, Forerunner 70, 170 and
  170 Music, vívofit jr. 3 and vívosmart 5 are stored as Maps=No: their
  official specifications show no map row at all and their product categories
  have no maps. Like any stored `true`/`false`, the collector never replaces
  these values; an administrator can still change them.

Installation checks current policy before provider/custom acquisition or
extraction and again at the final write boundary. Safe Update checks when the
operation starts and immediately before its first remote write, comparing the
connected identity around both requests. Once writing has started, exact
target cleanup and rollback use the operation's established safety facts and
do not require another policy request. All other live-device, ownership,
no-overwrite, storage, and transfer checks remain in force.

The connected-device policy result must be supplied to the map engine as it
changes. The Install review action is available only after the current device
identity matches an approved policy result and the map scan is ready. While
authorization is pending or unavailable, the review screen explains the reason
and keeps Install disabled. A policy failure at operation start must surface a
failure instead of leaving an apparently successful button press with no action.
This review/engine synchronization correction is published in beta.15 build 36.
The owner confirmed the Install and Update behavior with the local release
candidate on a Garmin fēnix 8 47 mm before publication; that is owner-reported
hardware evidence for the tested model and behavior.

`installation-policy.schema.json` defines the response shape. The backend
code serves a public-read, metadata-only `GET /devices/installation-policy.json`
projection with `schemaVersion: 3`.

Client schema tolerance: beta.14–beta.18 clients require the exact schema-3
document and record key sets, so the server must not add fields to the
schema-3 projection while those clients are supported. From the next app
candidate, the client still requires every known document and record field to
be present (nullable fields as explicit null) and valid, keeps the exact
`manufacturer: "Garmin"` and unique-ID checks, and tolerates additive unknown
fields at both levels. A field that can narrow or revoke write authority must
never be added to schema 3; it requires a new `schemaVersion`. A client that
receives a higher `schemaVersion` reports the distinct `UPDATE_REQUIRED` block
("This Terento version needs an update before it can install maps.") and never
writes; a malformed, older-schema or unreachable response remains
`CATALOG_UNAVAILABLE`. Mid-operation re-checks keep their existing failure
codes; the visible review and acquisition messages use the update text. The implementation requires a fresh
response and uses `Cache-Control: no-store`; conditional requests return a
new 200 policy rather than 304. The deploy smoke check now includes this
endpoint. Live route validation is independent of app packaging and publication;
a separate validated app build and publication decision remain required.


## Write target resolution — beta.18/build40 (2026-10-05)

Server approval does not replace live target validation. Install, custom import
and managed lifecycle operations resolve one root folder and its nonzero storage
ID with the same `ResolvedMapWriteProfile` / `GarminMapTarget` rules. Only ASCII
case differences in the root name `GARMIN` are accepted. Missing or multiple
roots (including roots on separate storages), zero IDs and incomplete physical
identity fail closed. No first-storage fallback, automatic folder creation or
model-specific exception is permitted.

The complete profile is checked before acquisition and again against the final
live inventory before installation writes. The bounded inventory worker carries
the physical operation profile into its native session. Safe Update also checks
the unique root and expected storage on its physically bound live inventories.
These pre/post-write inventories are map-scope reads (every storage-root entry
plus the single `GARMIN` root subtree; see `app/TerentoCore/README.md`), so root
uniqueness and storage binding are checked on the same root entries as a full
walk, and any missing or ambiguous root makes the native session fall back to
the full walk.
The existing native mutation grant, same-session identity, ownership, protected
objects, source verification, free-space and no-overwrite checks remain required.
A delete grant for a Terento-managed map (Remove, Update's old map) may carry the
sampled removal proof recorded in that map's manifest entry; the native delete
then reads and compares only the recorded regions of the exact same-session
object. Without a proof, and always for external maps, it compares the full
SHA-256. The proof never grants write or delete permission by itself; see
`app/TerentoCore/README.md` (Safety and verification).
Safe Update's pre-write check of the installed managed map uses the same
recorded proof read-only when the entry has one (otherwise the full SHA-256),
and its verification of the new map before the old map is removed is the
fresh-install sampled read-back against the validated local artifact. Neither
check grants permission: the update still needs fresh authorization, the old
map is bound to its recorded size and SHA-256 only after the check passes, and
the old-map delete grant is issued only after the new map was verified.

Native inventory and exact-read resolution project only the verified root and
its descendants in the selected storage to logical `/GARMIN` paths. Original
root filename, suffix/file-name case, IDs, size and object kind are retained;
other storages and paths are untouched. This is a comparison representation,
not a device rename. Protected-inventory comparison retains the original root
name, so a root rename during an operation still fails closed. Existing canonical
manifest paths remain valid without migration, including after reconnect.

A profile failure is a preparation failure with `writeStarted=false`. A valid
transfer attempt can fail at zero bytes; progress callbacks do not define the
write boundary. Local finishing diagnostics accept only fixed `target_reason`
codes: `root_missing`, `root_ambiguous`, `storage_invalid`, `root_invalid`,
`identity_invalid`, `profile_mismatch`. They never log the profile, observed root
path, serial or Unit ID. Uploaded diagnostics keep the existing schema and error
classification; no API or database migration is part of this correction.

This correction is published in beta.18/build40 from verified source `e0f0e704`.
It does not establish a new hardware compatibility claim. The beta.12/beta.16 comparison and #340/#342/#343/#344/#345 reports support
inconsistent root/storage resolution as a strong hypothesis; historical reports
do not contain the raw root/storage facts needed to prove that all eight failed
attempts had this cause. Historical reports and counters remain unchanged. Issue closure requests retesting;
it never converts a recorded failure into successful installation evidence.

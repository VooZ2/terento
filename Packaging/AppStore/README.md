# Mac App Store build configuration (stage 1 spike)

The `AppStore` Xcode configuration builds the same `Terento` target as an App
Sandbox app. It started as a private technical test of USB through the bundled
libmtp/libusb, the finishing helper and the container migration under App
Sandbox with a real watch. Since 2026-11-18 it is the build published on the
[Mac App Store](https://apps.apple.com/app/terento-gps-watch-maps/id6828556832). The DMG/GitHub build (`Debug`,
`Release`, `Packaging/release.sh`) does not change.

## What the configuration changes

`AppStore` copies the target's `Release` settings. It differs only in:

| Setting | Value | Why |
| --- | --- | --- |
| `CODE_SIGN_ENTITLEMENTS` | `app/Terento/Terento-AppStore.entitlements` | App Sandbox entitlements below. |
| `SWIFT_ACTIVE_COMPILATION_CONDITIONS` | adds `TERENTO_APP_STORE` | Compiles out the code listed below. |
| `TERENTO_APP_STORE_SANDBOX` | `YES` | Turns on the `Embed App Store sandbox helper` build phase. |
| `TERENTO_CONTAINER_MIGRATION_MANIFEST` | empty | A manifest to embed; see "Container migration". |
| `CODE_SIGN_IDENTITY` | `-` (ad-hoc) | Builds without an Apple account. A TestFlight archive overrides it. |
| `ENABLE_HARDENED_RUNTIME` | `NO` | Not required for the Mac App Store; avoids library-validation failures in ad-hoc test builds. |

`Tests/run-app-store-config-contract-tests.sh` fails if any other setting
drifts from `Release`. A version or build bump must therefore change the
`AppStore` entries too.

### Compiled out with `TERENTO_APP_STORE`

These code paths are removed at compile time, not hidden:

- the update check: no `updates/macos-arm64.json` request, no `Check for Updates…`
  menu item, no About `Update` button or status, no update prompt
  (guideline 2.4.5(vii));
- the `Donate` links in About and on Maps installed (guideline 3.1.1).

Support reports to Terento are not compiled out (from 1.3.0). The
installation failure dialog offers `Send report to Terento` while results
are not shared (declined or not chosen yet): it sends only that failure's
report after the person reviews it and presses Send, and changes no sharing
choice. Diagnostics and the Help menu still offer only the GitHub report.
Help also has `Send Feedback…` (a mail draft with only the app version and
build), `Rate on App Store…`, which opens the existing review link, and
`Star on GitHub…`, which opens the repository.

### Opt-in diagnostics (stage 3)

Compatibility and update diagnostics, map usage events and first-run funnel
events are sent only after the person opts in (guideline 5.1.1, GDPR):

- A successful operation is a completed installation (not a partial one) or
  a verified map update. After one, while no choice is recorded, the app
  shows a `Help improve Terento` callout: on `Map installed`
  after an installation, above the list in Manage maps after an update. It
  has three equal buttons and nothing pre-selected. `Share` or `Don't share`
  records `accepted` or `declined` for both streams, and `accepted` also
  queues that operation's compatibility results. `Not now`, or leaving the
  page without choosing, records no choice; the callout comes back once,
  after the next successful operation, and after that it is not shown again
  and nothing is sent (`AppStoreReviewPolicy`, local
  `AppStoreSharingQuestionShownCount`).
  Diagnostics keeps both checkboxes to change it later.
- The App Store notice version is 101 from 1.3.0 (100 in 1.2.x;
  `AppStoreConsentNotice`, used by `VersionedEvidenceConsent` and
  `VersionedMapStatisticsConsent`); only `accepted` under the current version
  permits sharing. At start-up (`AppStoreConsentNotice.migration`):
  - a choice under notice 101 is kept as it is, so `Don't share` is final;
  - `accepted` under 100 is kept with its queue;
  - `declined` under 100 becomes unanswered, because the 1.2.x `Not now`
    recorded a refusal; the person is asked again with the new callout. This
    also applies to a 1.2.x refusal made in Diagnostics or carried over from
    the DMG app, which 1.2.x stored under 100 too;
  - a choice copied from the DMG app (its own notice numbers) becomes
    `declined` if it was declined and unanswered otherwise.
  Every queue without a standing opt-in is dropped, so nothing recorded under
  the DMG notice or without an opt-in is sent.
- Events carry `releaseLabel` with `+appstore` SemVer build metadata (for
  example `1.1.0+appstore`), so Admin tells App Store results apart without
  an API change.
- From the second successful operation, at most once per app version, the
  app asks macOS for the system rating prompt (`requestReview`, guideline
  5.6.1); macOS shows it at most three times a year. One operation is followed
  by at most one of the two: while the sharing callout shows, the request
  waits for the next successful operation. The request is made one second
  after `Map installed` (or Manage maps after an update) is on screen, never
  inside the view update that opens the page. The count keeps the 1.2.x key
  `AppStoreSuccessfulInstallCount`. About links to the App Store review page
  instead of `Donate`.

Catalog, device catalog, installation policy and public compatibility
requests, map downloads and device images keep working. The catalog without a
watch is not part of this configuration.

Device photo: through 1.2.1 this configuration showed only Terento's own
device images and the generic fallback, and never read a `garmin.com` product
page or `res.garmin.com` (`DeviceAssetResolver.allowsOfficialProductMedia`).
From the version after 1.2.1 it shows the same reviewed device photo as the
DMG build, including official product media with its attribution. The App
Store review notes for that version must no longer say that the app shows no
manufacturer product photos, and its list of contacted hosts must include the
device image hosts.

## Entitlements

App, `Terento-AppStore.entitlements`:

| Entitlement | Used for |
| --- | --- |
| `com.apple.security.app-sandbox` | Required for every Mac App Store executable. |
| `com.apple.security.device.usb` | libusb opens the watch through IOUSBLib. |
| `com.apple.security.network.client` | Map catalog, map downloads, installation policy, device catalog and images. |
| `com.apple.security.files.user-selected.read-write` | Custom `.img` import (`fileImporter`), ownership file import (`NSOpenPanel`) and export (`NSSavePanel`). |

Helper, `TerentoFinishingWorker-AppStore.entitlements`: exactly
`com.apple.security.app-sandbox` and `com.apple.security.inherit`. The helper
inherits the app's sandbox, including USB access. No temporary exceptions, and
no `get-task-allow` (`CODE_SIGN_INJECT_BASE_ENTITLEMENTS = NO`).

## Finishing helper

The DMG app runs device reads (snapshot, inventory, header reads and the
sampled read-back after a write) in a child process: it relaunches its own
executable with `--terento-finishing-worker`. Under App Sandbox a child must be
a separate executable signed with only app-sandbox + inherit; a sandboxed app
cannot relaunch itself as that child.

`embed-sandbox-helper.sh` runs as the last build phase. For `AppStore` it
copies the linked app executable to `Contents/MacOS/TerentoFinishingWorker`
and signs it with the helper entitlements and the identifier
`<bundle ID>.TerentoFinishingWorker`. The copy runs only
`MTPFinishingWorker.runIfRequested()` and exits. In `AppStore` builds
`MTPFinishingWorker.perform` launches that helper instead of the app
executable. For `Debug` and `Release` the phase exits at once.

The helper only reads from the watch. It must not outlive the app (plan A5):

- the helper checks its parent every 0.2 s and exits once the app is gone
  (`Quit`, `Quit anyway`, crash or force quit). The app never signals a
  helper by PID at quit, so a reused PID cannot be hit;
- the existing deadline still ends a helper that stops responding.

The same termination would be safe for the DMG worker, but the DMG behaviour
is unchanged in this spike.

## Nested code signing

Under App Sandbox every nested code item must be signed. Xcode does not sign
files that a build phase copies, so `embed-sandbox-helper.sh` signs
`Contents/Frameworks/libusb-1.0.0.dylib`, `libmtp.9.dylib` (built and copied by
`Packaging/NativeDependencies/build.sh`, unchanged) and the helper with the
build's signing identity. Xcode then signs `Terento.app` with the app
entitlements.

## Container migration

macOS moves the items in `Contents/Resources/container-migration.plist` into
the app container once, when it first creates the container. Apple's
documentation says "The operating system will copy the file", but on the
owner's Mac (2026-10-29) the originals were gone from
`~/Library/Application Support/Terento` after the first launch, so treat it as
a move. The manifest cannot use wildcards or filter file content.

`container-migration.plist` (production) lists, under
`~/Library/Application Support/Terento`:

| Item | Code |
| --- | --- |
| `.device-key-secret` | `TerentoManifestStore.swift`, `loadOrCreateSecret()`; without it the same watch gets another key and its manifest is not found. |
| `devices` (each `<device key>/manifest.json`) | `TerentoManifestStore.swift`, manifest URL. |
| `failed-install-recovery.json` | `TerentoManifestStore.swift`, `recoveryURL()`. |
| `MutationEvidence` | `NativeMutationLedger.swift`, `evidenceDirectory()`. |
| `installation-evidence.json`, `update-evidence.json` | `InstallationEvidence.swift`, `LocalInstallationEvidenceStore`; history, sharing choice and the upload queue. |
| `map-statistics-events.json` | `MapStatisticsEvent.swift`, `LocalMapStatisticsEventStore`; sharing choice and the upload queue. |

Not migrated: `app-funnel-events.json`, `compatibility-status.json` (server
copy), `support-report-unsent.json`, `DeviceAssets` (image cache), Caches,
Logs and the preferences (window size and download-speed samples only; no
sharing choice is kept in user defaults).

The three mixed JSON files are copied whole. At start-up the app drops their
migrated queues and treats a migrated `accepted` or missing choice as not
answered, and only a migrated `declined` as an answer (plan section 2).

Embedding rules (`embed-sandbox-helper.sh`):

- `xcodebuild archive` (`ACTION = install`) embeds the production manifest;
- `TERENTO_CONTAINER_MIGRATION_MANIFEST` embeds the given file instead (the
  local test uses this);
- any other build embeds none. Running such a build with the bundle ID
  `app.terento.mac` creates that container without migration, and macOS then
  never migrates for that ID on this Mac; the build prints a warning.

The first launch of a build with the bundle ID `app.terento.mac` (TestFlight,
or an archive run directly) moves the real DMG data into the container. The
DMG app then starts without its manifests and device key, so it must not be
used on that Mac until the backup is copied back. The two apps never share
manifests: a map installed or removed with one app is not recorded by the
other. Use one app per Mac. Back up `~/Library/Application Support/Terento`
before the first launch.

## Local sandbox test

Run on a Mac with Xcode, from the repository root. No Apple account is needed:

```sh
Packaging/AppStore/build-local-sandbox-test.sh
```

The script builds `AppStore` ad-hoc signed with the bundle ID
`app.terento.mac.sandboxtest` and `container-migration.sandboxtest.plist`.
That manifest copies items only from
`~/Library/Application Support/TerentoSandboxTestSeed` into the test
container, `~/Library/Containers/app.terento.mac.sandboxtest`. By default the
script fills the seed with a copy of the DMG data; the originals are only
read. `--seed empty` tests a first-time user, and `--reset` deletes the test
container and seed so the migration runs again. The script refuses to run while
any Terento is open, checks the built bundle ID and manifest, prints both
entitlement sets and the next steps.

Checks with a real watch (plan stage 1):

- A3: without a watch, the connect screen appears;
- A1: with the watch, Terento shows the model, free space and maps;
- A2: one small catalog map installs to the end, including the read-back in
  the helper (`pgrep -fl TerentoFinishingWorker` while it verifies);
- A5: after `Quit`, `Quit anyway` during verification, and a force quit,
  `pgrep -fl TerentoFinishingWorker` prints nothing within 1 s of the
  Terento process ending (not of the click: quitting first removes partial
  downloads, and the helper ends with the process);
- B6: the migrated files are in the container and DMG-installed maps show as
  managed. The seed may keep its originals (Apple documents a copy), but a
  real install moved them.

Install only a map that is not on the watch yet and remove it again with the
test app. The test app works on a copy of the manifests, so do not update or
remove maps that the DMG app manages.

An ad-hoc test does not prove the App Store signature. That needs the internal
TestFlight build below.

## Internal TestFlight build

`archive-for-testflight.sh` runs on the owner's Mac. It needs Xcode signed in
to team `VXALAZU3B5` and an App Store Connect record for `app.terento.mac`.
It:

1. archives `AppStore` with automatic signing (`-allowProvisioningUpdates`
   creates the certificates and the Mac App Store profile). The archive
   embeds the production migration manifest;
2. exports a Mac App Store `.pkg` (`method` `app-store-connect`, `destination`
   `export`);
3. checks the exported package, because the export re-signs nested code:
   - bundle ID, embedded profile, production migration manifest;
   - valid app signature and a signed package;
   - app entitlements equal to the file plus only the profile's
     application and team identifiers;
   - helper entitlements exactly `app-sandbox` + `inherit`.

App Store Connect accepts a build number once per version. The first upload of
a version keeps the Release build number (`46`); each later upload of the same
version passes a sequence number, `archive-for-testflight.sh 1` builds `46.1`,
`2` builds `46.2`.

After every check passes, the script exports the same archive again with
`destination` `upload`: Xcode uploads it with the Apple ID signed in to Xcode,
so no App Store Connect key leaves the Mac. If that fails, the checked `.pkg`
can still be delivered with Transporter. The first launch moves the real DMG
data into the container (see Container migration), so the script prints a
`ditto` backup command to run first.

## CI

- `Tests/run-app-store-config-contract-tests.sh` (app suite, runs anywhere):
  exact entitlements, `AppStore` settings against `Release`, both migration
  manifests, that the update and donation strings are compiled out of
  `AppStore` but still present in the DMG configuration, and the opt-in rules
  above.
- The macOS app job runs `verify-app-store-build.sh`: it builds `AppStore`
  ad-hoc signed, verifies every nested signature, compares the app and helper
  entitlements with the files above, and checks that no executable in the
  bundle contains `updates/macos-arm64.json` or `buymeacoffee`. The Debug app built in the same job is the control that
  must still contain them.

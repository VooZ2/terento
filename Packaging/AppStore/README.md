# Mac App Store build configuration (stage 1 spike)

The `AppStore` Xcode configuration builds the same `Terento` target as an App
Sandbox app. It exists for a private technical test: does USB through the
bundled libmtp/libusb, the finishing helper and the container migration work
under App Sandbox with a real watch? Nothing here is published, and the
DMG/GitHub build (`Debug`, `Release`, `Packaging/release.sh`) does not change.

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

- the update check: no `updates/macos-arm64.json` request, no `Check updates`
  menu item, no About `Update` button or status, no update prompt
  (guideline 2.4.5(vii));
- the `Donate` link (guideline 3.1.1);
- every diagnostics upload: compatibility and update diagnostics,
  map usage events, first-run funnel events, and support reports. The HTTP
  uploaders contain no endpoint. Installation results stay in local history,
  nothing is queued for upload, and data migrated from the DMG app is never
  sent by this build. The About and Diagnostics windows say that this build
  does not send diagnostics, and offer only the GitHub failure report;
- the consent rewrite at start-up, so a migrated sharing choice stays as the
  DMG app wrote it.

Catalog, device catalog, installation policy and public compatibility
requests, map downloads and device images keep working. The consent window and
the catalog without a watch are stage 3, not this configuration.

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

macOS copies the items in `Contents/Resources/container-migration.plist` into
the app container once, when it first creates the container (Apple: "The
operating system will copy the file"). The originals stay where they were. The manifest
cannot use wildcards or filter file content.

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

The three mixed JSON files are copied whole. This build never uploads their
queues. Before a build sends anything (stage 3), it must drop the migrated
queues and treat a migrated `accepted` or missing choice as not answered, and
only a migrated `declined` as an answer (plan section 2).

Embedding rules (`embed-sandbox-helper.sh`):

- `xcodebuild archive` (`ACTION = install`) embeds the production manifest;
- `TERENTO_CONTAINER_MIGRATION_MANIFEST` embeds the given file instead (the
  local test uses this);
- any other build embeds none. Running such a build with the bundle ID
  `app.terento.mac` creates that container without migration, and macOS then
  never migrates for that ID on this Mac; the build prints a warning.

Installing a TestFlight build copies the real DMG data into the container.
After that the DMG app and the App Store app each keep their own manifests,
and they are not synchronised: a map installed or removed with one app is not
recorded by the other. Use one app per Mac. Back up
`~/Library/Application Support/Terento` before the first TestFlight install.

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
  managed. The seed may keep its originals (Apple documents a copy).

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
   `export`). It never uploads;
3. checks the exported package, because the export re-signs nested code:
   - bundle ID, embedded profile, production migration manifest;
   - valid app signature and a signed package;
   - app entitlements equal to the file plus only the profile's
     application and team identifiers;
   - helper entitlements exactly `app-sandbox` + `inherit`.

The owner uploads the `.pkg` with Transporter. Installing it from TestFlight
copies the real DMG data into the container once, so the script prints a
`ditto` backup command to run first.

## CI

- `Tests/run-app-store-config-contract-tests.sh` (app suite, runs anywhere):
  exact entitlements, `AppStore` settings against `Release`, both migration
  manifests, and that the update, donation and upload strings are compiled out
  of `AppStore` but still present in the DMG configuration.
- The macOS app job runs `verify-app-store-build.sh`: it builds `AppStore`
  ad-hoc signed, verifies every nested signature, compares the app and helper
  entitlements with the files above, and checks that no executable in the
  bundle contains `updates/macos-arm64.json`, `buymeacoffee` or an upload
  endpoint. The Debug app built in the same job is the control that must still
  contain them.

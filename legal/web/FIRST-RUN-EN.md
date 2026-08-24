# First-run risk and ownership acknowledgment

English-only copy and UX spec for the public macOS app (GitHub + website, not App Store).

This is **not** an EULA, not a click-wrap licence, and not a digital-content contract. It is a one-time **risk + ownership** acknowledgment shown immediately before the first write to a Garmin device.

This is not legal advice.

---

## Final dialog copy

Use this text in the app. Do not add Lithuanian. Do not paraphrase in the UI.

### Title

Before you connect a watch

### Body

Terento is an independent open-source project. It is **not** a Garmin or Apple product. Neither has endorsed it.

**Who owns what**

- Garmin names, devices, and software belong to Garmin.
- Apple and macOS belong to Apple.
- Maps (Freizeitkarte and OpenStreetMap data) belong to their authors and providers. Terento does not create, relicense, or brand those maps as its own. The app only fetches them from the source and writes them to your device.
- The Terento app is GPL-3.0-or-later.

**Risk**

This app **writes to a Garmin device**. A wrong path, a dropped USB connection, or a bug can damage maps, data, or, rarely, the device. Terento **does not guarantee** success. If you are unsure, do not install.

This does not take away rights that EU and Lithuanian law **do not allow** you to give up.

More: [https://terento.app/legal/](https://terento.app/legal/) · [https://terento.app/privacy/](https://terento.app/privacy/)

### Checkbox

I understand who owns what, and that installing onto a watch is at my own risk.

### Buttons

- **Cancel**
- **Continue** — enabled only when the checkbox is checked

---

## UX spec

### When to show

Show **once**, immediately before the **first write** to a Garmin device (install or update that transfers a file, or any other first mutating write).

Do **not** show:

- on every app launch
- merely because the main window opened
- on connect / device identify
- while browsing maps or downloading to the Mac
- again after a valid acceptance of the current copy version

If the user later starts another write and acceptance is already stored for the current version, skip the dialog and proceed with the existing write confirmation (if any).

If a write is attempted and no valid acceptance is stored, show this dialog **before** any MTP write, delete, overwrite, or device-file mutation.

### Persistence

Store acceptance in `UserDefaults` (standard suite for the app).

| Item | Value |
|---|---|
| Key | `legalAcknowledgementVersion` |
| Type | `Int` |
| Current copy version | `1` |
| Accepted | stored integer **equals** the current copy version |
| Missing / cleared | `integer(forKey:)` is `0` → treat as not accepted |

Re-show only when:

1. the app was reinstalled or defaults were cleared (no stored version), or
2. the legal copy in this file changed and the current copy version was bumped (stored value ≠ current version)

When the dialog text changes in a way that should be seen again, increment the version in **one** place (e.g. `LegalAcknowledgement.currentVersion`) and keep this file in sync.

Do not store the acknowledgment on a server. Do not upload Garmin unit identifiers with it.

### Cancel

**Cancel** aborts the **pending write** only. Do not persist acceptance. Do not quit the app. The user stays in the app; no device file is changed.

### Continue

**Continue** is disabled until the checkbox is on. On Continue: write `legalAcknowledgementVersion = 1` (or the current version), dismiss, then proceed with the write that was about to start.

### Language and chrome

- English only. No `lt` strings, no localization table for this dialog.
- Title, body, checkbox, and buttons as specified. No extra “I agree to the terms” framing.
- The two “More” links open in the default browser (`NSWorkspace` / `openURL`). Do not embed the legal pages in-app.
- Not a licence-scroll, not “Agree / Disagree”, not an App Store EULA sheet.

### What this is not

- Not a substitute for the website legal and privacy pages
- Not a grant of rights in Garmin, Apple, Freizeitkarte, or OpenStreetMap marks or maps
- Not a warranty or a promise that a write will succeed
- Not a waiver of non-waivable EU / Lithuanian rights

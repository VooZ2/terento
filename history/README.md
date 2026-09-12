# Historical validation evidence

These records describe past candidates and release checkpoints, not the current
product state. Current functionality is documented in the component READMEs;
release identity is in [release notes](../RELEASE_NOTES.md) and GitHub Releases.
Original detailed receipts remain available at the immutable source links below.
Private paths in those receipts are historical observations, not reproducible
public build instructions.

## Retained conclusions

- beta.11 build22 corrected progressing sampled-read worker deadlines. Its
  automated evidence did not establish a general USB fix. Subsequent bounded
  process tests gained scheduling tolerance and retained failure stderr.
- Local23 failed its real-device gate. Local24 corrected native reference
  lifetime but still recorded a read failure. Local25 added the reviewed
  partial-read/recovery treatment. Local26 addressed Install Maps rendering
  work. None of these local candidate numbers is a published release.
- beta.11 build27 is published. Owner reported MapRando Andorra/France installs
  on fēnix 8 47 mm AMOLED / firmware 23.31. This is exact-model owner evidence,
  not proof of all watches or a newer-map safe update.
- beta.12 build28 is published at
  [its immutable tag](https://github.com/VooZ2/terento/releases/tag/v1.0.0-beta.12-build28).
  Source f2de8eda3e8ab36724aaeae85ba23fceef5c9d86; DMG SHA-256
  `ccf5cd707c2d27d48b523c44c7c93a3045a126d22c3f9dd2458dbb00430b8304`.
  It includes four providers / five map types. Prior local28–30 failures and
  fixes were preparation, not separate public releases. Local33 recovery
  succeeded after reconnect; inventory/readback root causes remain unresolved.
- Real installation/removal and reconnect evidence must remain separate from
  on-watch usability, full-file hashing and a real update to a newer release.
  The latter was waived for beta.12 and remains untested.
- Website screenshots and five map cards were subsequently published. Old
  receipt wording such as “publication pending” is a checkpoint, not current status.

## Original receipts

- [2026-09-11-beta11-web-release.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-11-beta11-web-release.md)
- [2026-09-11-build22-finishing.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-11-build22-finishing.md)
- [2026-09-11-build23-local-usb-recovery.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-11-build23-local-usb-recovery.md)
- [2026-09-12-beta11-build27-release.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-beta11-build27-release.md)
- [2026-09-12-beta12-build28-release.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-beta12-build28-release.md)
- [2026-09-12-beta12-local-build28.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-beta12-local-build28.md)
- [2026-09-12-beta12-local-build29.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-beta12-local-build29.md)
- [2026-09-12-beta12-local-build30.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-beta12-local-build30.md)
- [2026-09-12-build24-local-device-references.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-build24-local-device-references.md)
- [2026-09-12-build25-local-partial-read.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-build25-local-partial-read.md)
- [2026-09-12-build26-local-install-ui.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-build26-local-install-ui.md)
- [2026-09-12-catalog-ui-polish.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-catalog-ui-polish.md)
- [2026-09-12-home-map-cards.md](https://github.com/VooZ2/terento/blob/11d5a19b1d831d3dbed479d2e1a46807de6a68b8/reports/2026-09-12-home-map-cards.md)

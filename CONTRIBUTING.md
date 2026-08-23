# Contributing to Terento

Thank you for taking an interest in Terento. Contributions, bug reports, documentation improvements, and careful testing are welcome.

## Project status

Terento is an active beta and pre-MVP project for macOS. It is not a stable production release and it does not yet provide a notarized DMG or PKG.

The current native connectivity work is centred in lab/native-connectivity-poc. The normal app flow is deliberately conservative. Device-writing and interruption tests are developer-only tests and must never be treated as a general map-installation test.

## Before you start

- Read the root README and the README in lab/native-connectivity-poc.
- Search existing issues and pull requests before opening a new one.
- For security vulnerabilities, follow SECURITY.md instead of opening a public issue.
- Do not upload Garmin device dumps, map binaries, private logs, credentials, API keys, or personal data.

## Development environment

The current native proof of concept expects:

- macOS 13 or newer;
- Swift 6 or newer and Xcode with SwiftUI support;
- Homebrew;
- libmtp 1.1.23; and
- libusb 1.0.30, used by libmtp.

From lab/native-connectivity-poc, the normal build and test commands are:

    export LIBMTP_PREFIX=/opt/homebrew/opt/libmtp
    export CLANG_MODULE_CACHE_PATH=/tmp/terento-native-poc-module-cache
    swift build
    swift test

Hardware tests require an explicitly authorised personal Garmin device. They are not a substitute for automated tests and should not be run against a device containing irreplaceable data.

## Safe device testing

- Use only a device and account that you own or are explicitly authorised to use.
- Keep a current device backup before any test that can write or remove an object.
- Close other Garmin and MTP applications before testing.
- Use only the fixed test payloads for developer-only write and interruption tests.
- Never use a real map binary as a write-test payload.
- Confirm the target path and device identity before every write or removal test.
- Do not remove or overwrite files that Terento cannot prove it owns.
- Record the device model and test result without recording serial numbers or private device contents.

## Branches and pull requests

The repository currently uses beta as its default branch. Unless the repository announces a new default branch, target pull requests at the current default branch.

Use a focused branch name such as:

- feature/short-description
- fix/short-description
- docs/short-description
- test/short-description

Keep pull requests small and explain:

- what changed and why;
- which components are affected;
- how the change was tested;
- whether real-device testing was performed; and
- any remaining limitations or follow-up work.

Use clear, imperative commit messages. Do not mix unrelated refactors with a safety-sensitive device or map change.

## Review expectations

Changes should preserve the project's safety boundaries:

- fail closed when device identity, ownership, compatibility, or transfer verification is uncertain;
- never silently overwrite or remove unknown or unrelated device files;
- keep map downloads on the user's Mac and retain provider attribution;
- keep Garmin independence and trademark disclaimers intact;
- avoid collecting device data that the app does not need;
- add or update tests for behaviour changes; and
- document beta limitations honestly.

## Maps, data, and third-party code

Do not commit map binaries or redistribute provider data unless the applicable licence explicitly allows it. Preserve source, attribution, and licence information for map providers and dependencies. Review THIRD_PARTY_NOTICES.md before adding a dependency, font, image, or external service.

## Questions

Use GitHub Issues for reproducible bugs and scoped feature requests. Use GitHub Discussions if it is enabled for the repository. For security issues, follow SECURITY.md.
# Terento project structure

This document is the repository map. It separates source, application
packaging, public website content, and local-only material without changing
the current application architecture.

## Public repository areas

These directories and root documents are suitable for the GitHub source
repository, subject to the normal review of the current worktree:

| Area | Purpose |
| --- | --- |
| `app/Terento/` | macOS application shell, `Info.plist`, entitlements, resources, and the bridging header |
| `lab/native-connectivity-poc/` | Current SwiftPM source module, native bridge, resources, and tests used by the app target. The name is historical and is retained for now to avoid breaking project paths. |
| `Terento.xcodeproj/` | macOS application target and Xcode build configuration |
| `Packaging/` | Repeatable local build/release preparation scripts and signing documentation. It must not contain certificates, credentials, or generated release files. |
| `site/` | Public website, localized pages, legal pages, and public assets |
| `legal/` | Public legal web source and publication inputs |
| `backend/catalog-api/` | Metadata-only catalog service |
| `brand/` | Approved brand assets and guidelines; exploratory previews remain local |
| `AGENTS.md` | Repository-wide Codex and contributor instructions |
| `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md` | Source and dependency notices |

## Local-only or operational areas

These areas are intentionally not part of the public GitHub publication
boundary:

| Area | Purpose |
| --- | --- |
| `internal/` | Canonical private architecture, state, research, security, and roadmap documents |
| `docs/` | Local task and deployment notes |
| `deploy/` | Environment-specific deployment/operator material |
| `lab/test-site/` | Local test-site experiments |
| `AGENTS.override.md` | Local machine or operator-specific Codex overrides; ignored and must never be committed |
| `.cursor/` | Local editor/agent state and debug logs |

## Generated and ignored output

Generated files are not copied into a second “ready” source tree. The source
of truth stays in the tracked project, while generated output is kept in
ignored locations:

| Location | Purpose |
| --- | --- |
| `lab/native-connectivity-poc/.build/` | SwiftPM build cache |
| `lab/native-connectivity-poc/.swiftpm/` | SwiftPM local metadata |
| `dist/` | Local release artifacts, including validated arm64 ZIP and DMG files when present |

These paths are ignored by `.gitignore`. A release is identified by its
reviewed commit/tag and its checksummed artifact, not by duplicating the
whole repository into a `production/` or `ready/` directory.

## Current application boundary

The production Xcode target consumes source files from
`lab/native-connectivity-poc/`. Moving that code to a cleaner name such as
`app/core/` or `Sources/TerentoCore/` would require coordinated Xcode project,
bridging-header, SwiftPM, test, and documentation changes. It is therefore a
separate refactor and is deliberately not part of this cleanup.

## Release state and provenance

The local packaging pipeline and `dist/` output are separate from the public
website and from source publication. The pipeline can produce notarized arm64
ZIP and DMG artifacts, but organizing this tree does not publish them.

Release identity, artifact availability, and release-specific provenance are
maintained in `RELEASE_NOTES.md`, GitHub Releases, and current release
metadata. Keep that identity aligned across Xcode settings, release notes,
the Git tag, the update manifest, and artifact names; do not duplicate a
version number in this repository map.

Changes to application code, tests, website/legal content, and packaging must
be reviewed and committed as separate logical changes; this repository-map
update does not change those boundaries or publish them.

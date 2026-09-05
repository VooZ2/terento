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
| `app/TerentoCore/` | Production SwiftPM source module, native bridge, resources, and regression tests consumed by the root Xcode target. |
| `Terento.xcodeproj/` | macOS application target and Xcode build configuration |
| `Packaging/` | Repeatable local build/release preparation scripts and signing documentation. It must not contain certificates, credentials, or generated release files. |
| `site/` | Public website, localized pages, legal pages, and public assets |
| `legal/` | Public legal web source and publication inputs |
| `backend/catalog-api/` | Metadata-only catalog, devices, compatibility evidence, diagnostics and admin API |
| `contracts/` | [Shared public JSON schemas and fixtures](contracts/README.md) consumed directly by Python, Swift and Node tests |
| `Tests/` | Suite inventory, path selection, repository runners and cross-component checks |
| `site-deploy/` | Public website container configuration |
| `.github/workflows/` | CI quality gates, reusable API checks and deployment workflows |
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
| `app/TerentoCore/.build/` | SwiftPM build cache |
| `app/TerentoCore/.swiftpm/` | SwiftPM local metadata |
| `dist/` | Local release artifacts, including validated arm64 ZIP and DMG files when present |

These paths are ignored by `.gitignore`. A release is identified by its
reviewed commit/tag and its checksummed artifact, not by duplicating the
whole repository into a `production/` or `ready/` directory.

## Current application boundary

The root `Terento.xcodeproj/` consumes production source from `app/TerentoCore/`.
`app/Terento/` owns the application shell and packaging configuration. SwiftPM
retains the existing `TerentoPoC`, `TerentoWriteTest` and `TerentoInterruptionTest`
module/executable names; renaming them is deferred. The historical native logger
subsystem string is also retained to preserve diagnostic identity.

Build from the repository root with `swift build --package-path app/TerentoCore`.
The move changes paths, not runtime behavior, bundled resource contents, device
ownership rules or release output.

## CI and contract boundary

`swift-ci.yml` selects the normal PR/branch suites and retains the required
`build-and-test` aggregate. `reusable-catalog-api-quality.yml` owns backend
regression tests, PostgreSQL migration/idempotency/health checks and the Docker
build. Both the selected backend job and `deploy-catalog-api.yml` call that same
workflow. The deployment-time rerun is intentional; it needs no deployment
secrets. Deployment credentials and subsequent rollout steps remain unchanged.

The redundant standalone backend CI workflow has been removed. Ruleset review
confirmed that `build-and-test` is the required check. Changes under `contracts/`
select every existing suite. No new suite category or runtime schema validator
is introduced; the fixtures stay in one repository-level directory.

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

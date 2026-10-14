# Terento versioning

Terento uses semantic versions with beta and release-candidate pre-releases:

```text
MAJOR.MINOR.PATCH
MAJOR.MINOR.PATCH-beta.N
MAJOR.MINOR.PATCH-rc.N
```

Current public Git tags combine the semantic release label with the distributed
build: `v<release-label>-build<CFBundleVersion>`, for example
`v1.0.0-beta.12-build28`, `v1.0.0-rc.1-build41` or `v1.0.0-build44`. Older tags without a build
suffix remain immutable historical identities; do not rename or overwrite them.

- **MAJOR** is reserved for intentionally incompatible public changes after
  stable maturity.
- **MINOR** marks a meaningful new capability line.
- **PATCH** marks a backward-compatible fix or correction within that line.
- **beta.N** increments for each published beta of the same base version.
- **rc.N** marks a release candidate: a feature-complete candidate for the
  stable `MAJOR.MINOR.PATCH` release. Between release candidates only fixes are
  accepted; a new capability waits for a later version. `rc.N` increments for each published candidate of the same base
  version and starts at `rc.1`.

The first build of a new beta or release-candidate label receives the next
monotonically increasing build number. A small backward-compatible correction
that does not change the label may use the next sequential build number without
creating a new label. The build counter is never reset or reused: the first
release candidate continues from the last beta build (for example beta.18 build
40 is followed by rc.1 build 41).

Beta releases and release candidates are pre-releases, not stable production
releases. Published beta history keeps its labels, tags and build numbers.
SemVer precedence orders `1.0.0-beta.N` before `1.0.0-rc.N` before `1.0.0`,
but the update check never compares labels: it orders by marketing version and
`CFBundleVersion`. A beta or release candidate may contain implemented code
whose final real-device validation gate is still pending; release notes must
state that limitation explicitly under KNOWN ISSUES (the release-note format
is defined in [Packaging/README.md](Packaging/README.md#release-notes-format)).
Deferred gates must not be described as passed, and a genuinely new capability line may start the next base version.

Release candidates are distributed on the existing `beta` update channel, the
pre-release channel that installed beta builds already follow. This keeps
current beta users on an in-app update path to each release candidate, and
installed clients only decode the `beta` and `stable` channel values. Do not
introduce a separate `rc` channel. Moving from a release candidate to the
stable label follows [Stable release](#stable-release).

## Stable release

A stable release has a plain `MAJOR.MINOR.PATCH` label, the `stable` update
channel and a GitHub Release that is not a prerelease and is marked Latest.
It is built from `main`. Beta and release-candidate prereleases are built from
`beta` and published only as GitHub prereleases: once a stable release exists,
the update manifest on `main` lists only stable releases. Installed beta.7 and
later clients, including every release candidate, accept a `stable` manifest;
a stable installation is never offered a beta.

Allowed label transitions (the build always rises above every `v*-buildN` tag):

| From | To | Branch | Manifest |
|---|---|---|---|
| `X.Y.Z-rc.N` | `X.Y.Z` | `main` | `stable` |
| `X.Y.Z` | `X.Y.Z` (rebuild), `X.Y.(Z+1)`, `X.(Y+1).0` or `(X+1).0.0` | `main` | `stable` |
| stable `X.Y.Z` | `beta.1` or `rc.1` of a newer version | `beta` | unchanged |
| `beta.N` | the same label (rebuild), `beta.N+1` or `rc.1` | `beta` | unchanged |
| `rc.N` | the same label (rebuild) or `rc.N+1` | `beta` | unchanged |

A stable transition starts from the `main` manifest. A prerelease starts from
the highest-build prerelease tag of the same marketing version, ordered by build
number; with none, only `beta.1` or `rc.1` of a version newer than the
published stable release is allowed. `Tests/release-documentation-tests.cjs`
enforces the table and `Packaging/release.sh` checks the build against the
remote tags and the packaged `TerentoReleaseChannel` against the label.

A stable release needs every real-device gate of its release candidates to
have passed. A gate may stay open only by an explicit, dated owner decision
recorded in the project state; it is then reported as `DEFERRED`, never as
passed, and the release notes list it under KNOWN ISSUES.

Published tags are immutable: never reuse, overwrite, or force-push a tag.
The release tag is the immutable source identity. The manifest releaseTag,
semantic releaseLabel and numeric build must match their corresponding fields; API
schema and catalog contract versions are separate compatibility versions and
are not release versions.

For every publicly distributed Terento build, `CFBundleVersion` is the
canonical ordering value used by the macOS update check and must increase
monotonically. Human-readable beta labels such as `1.0.0-beta.7` do not replace
the build-number requirement. The release manifest must carry the matching
version/build, public release label, update channel, minimum macOS, canonical
DMG URL, concise summary, and trusted full release-notes URL.

## Verified release source

New public builds must be packaged from a clean, GitHub-verified signed commit
already merged into `main` for a stable release, or into `beta` for a beta or
RC prerelease. Use the actual verified merge commit, not an unsigned
PR head with an equivalent tree. `Packaging/release.sh` enforces this through
`Packaging/verify-github-release-source.py` before building or contacting Apple;
`--no-notarize` remains available for undistributed local validation.

Create the new lightweight release tag at that exact packaged commit. Before
publishing the draft release, verify the remote tag still resolves directly to
that SHA and GitHub still reports its commit signature as valid. Do not create
an unsigned annotated tag around it. Record the source SHA with the artifact
checksums in the release receipt. GitHub signature verification is separate
from Apple Developer ID signing/notarization and immutable release attestations.

Existing unsigned releases cannot acquire a commit signature without changing
source identity. Preserve historical tags and assets; never delete/recreate a
release or disable immutability to obtain a badge. GitHub also prevents reuse of
an immutable release's tag name after deletion.

## Preparing a beta or release-candidate build

A reviewed `Packaging/release-candidate.json` (a staging record, not tied to the
`rc` label) can hold the unchanged marketing version and a label that is either
the same published label or exactly one step after it, plus a strictly newer
build. After `X.Y.Z-beta.N` the next label is `X.Y.Z-beta.N+1` or
`X.Y.Z-rc.1`; after `X.Y.Z-rc.N` it is `X.Y.Z-rc.N+1`. A release candidate never
returns to a beta label. Xcode settings must match it exactly, while public
downloads and checksums keep identifying the available release. Release notes
may carry a draft section for the staged label above the published section; the
draft is marked as unpublished and must be finalized before publication. Merge the candidate source through the normal checks, then
package that clean verified merge commit. Publish the actual signed artifacts
before updating public metadata; remove the candidate file in that metadata
change. This staging record does not waive source verification, notarization,
artifact validation or immutable-tag checks.

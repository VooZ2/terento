# Terento versioning

Terento uses semantic-style pre-release versions:

```text
MAJOR.MINOR.PATCH-beta.N
MAJOR.MINOR.PATCH-rc.N
```

Current public Git tags combine the semantic release label with the distributed
build: `v<release-label>-build<CFBundleVersion>`, for example
`v1.0.0-beta.12-build28` or `v1.0.0-rc.1-build41`. Older tags without a build
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
state that limitation explicitly. Deferred gates must not be described as
passed, and a genuinely new capability line may start the next base version.

Release candidates are distributed on the existing `beta` update channel, the
pre-release channel that installed beta builds already follow. This keeps
current beta users on an in-app update path to each release candidate, and
installed clients only decode the `beta` and `stable` channel values. Do not
introduce a separate `rc` channel. Moving from a release candidate to the
stable label and `stable` channel requires its own release-contract review.

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
already merged into beta. Use the actual verified merge commit, not an unsigned
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

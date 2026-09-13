# Terento versioning

Terento uses semantic-style beta versions:

```text
MAJOR.MINOR.PATCH-beta.N
```

Current public Git tags combine the semantic release label with the distributed
build: `v<release-label>-build<CFBundleVersion>`, for example
`v1.0.0-beta.12-build28`. Older tags without a build suffix remain immutable
historical identities; do not rename or overwrite them.

- **MAJOR** is reserved for intentionally incompatible public changes after
  stable maturity.
- **MINOR** marks a meaningful new capability line.
- **PATCH** marks a backward-compatible fix or correction within that line.
- **beta.N** increments for each published beta of the same base version.

The first build of a new beta label receives the next monotonically increasing
build number. A small backward-compatible correction that does not change the
beta label may use the next sequential build number without creating a new beta
label. The build counter is never reset or reused.

Beta releases are pre-releases, not stable production releases. A beta may
contain implemented code whose final real-device validation gate is still
pending; release notes must state that limitation explicitly. Deferred gates
must not be described as passed, and a genuinely new capability line may start
the next base version.

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

## Preparing a same-beta build

A reviewed `Packaging/release-candidate.json` can hold the unchanged version
and beta label plus a strictly newer build. Xcode settings must match it
exactly, while public notes, downloads and checksums keep identifying the
available release. Merge the candidate source through the normal checks, then
package that clean verified merge commit. Publish the actual signed artifacts
before updating public metadata; remove the candidate file in that metadata
change. This staging record does not waive source verification, notarization,
artifact validation or immutable-tag checks.

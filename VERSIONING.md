# Terento versioning

Terento uses semantic-style beta versions:

```text
MAJOR.MINOR.PATCH-beta.N
```

Git tags use the same version with a leading `v`, for example
`v0.1.0-beta.1`.

- **MAJOR** is reserved for intentionally incompatible public changes after
  stable maturity.
- **MINOR** marks a meaningful new capability line.
- **PATCH** marks a backward-compatible fix or correction within that line.
- **beta.N** increments for each published beta of the same base version.

Beta releases are pre-releases, not stable production releases. A beta may
contain implemented code whose final real-device validation gate is still
pending; release notes must state that limitation explicitly. Deferred gates
must not be described as passed, and a genuinely new capability line may start
the next base version.

Published tags are immutable: never reuse, overwrite, or force-push a tag.
The annotated Git tag is the canonical public release version. Package
metadata that carries the release identity must mirror that version; API
schema and catalog contract versions are separate compatibility versions and
are not release versions.

For every publicly distributed Terento build, `CFBundleVersion` is the
canonical ordering value used by the macOS update check and must increase
monotonically. Human-readable beta labels such as `1.0.0-beta.7` do not replace
the build-number requirement. The release manifest must carry the matching
version/build, public release label, update channel, minimum macOS, canonical
DMG URL, concise summary, and trusted full release-notes URL.

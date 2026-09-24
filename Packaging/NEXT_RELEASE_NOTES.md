# Terento 1.0.0-beta.14 (build 35) — unpublished draft

This draft describes source changes since beta.13 build 34, not an available
download. The published manifest and RELEASE_NOTES.md remain authoritative for
the currently distributed app. Candidate identity is staged after the source
audit; artifact checksums await the build gates. No installer is published by
merging this preparation.

- Installation and Update check the current Garmin catalog before acquiring a
  map and again before writing. Active models with Maps=Yes can be authorized
  without a public successful-install record.
- Missing size or display details do not prevent installation when every
  plausible catalog variant supports maps. Unknown or ambiguous models remain
  pending; an unavailable policy temporarily prevents installation.
- Garmin Edge installation is not supported yet by the current catalog. Edge
  support is planned for a future release, not permanently blocked by model name.
- Authorization refusals do not create failed-installation evidence. Optional
  per-map result identity improves correlation between diagnostic streams while
  preserving existing privacy controls and legacy payload acceptance.

Existing ownership, protected-map, safe update and explicit removal rules remain
unchanged. There is no new provider, native MTP transport, automatic cleanup or
claim that issues #278 or #276 have been fixed.

Server-side schema reconciliation, statistics exclusions, daily retention and
read-only health checks are deployed backend changes, not new app features.
Website IndexNow/deployment and compatibility-refresh CI changes are likewise
not app functionality. They do not authorize publishing this draft or a build.

# Terento v1.0.0-beta.12 (build 28) — release preparation

Status: PREPARING, unpublished. The owner approved the English changelog and
three-item update summary, then explicitly selected public build28 (last public
build27; builds28–31-local were private tests). The next private candidate uses
32-local to distinguish it from earlier private packages. Public metadata uses
28 as requested; a local build32 user must install the public DMG manually,
since the updater orders CFBundleVersion and must not be weakened for this case.

## Scope

One new provider BBBike, with two independent types BBBike and BBBike (Ontrail),
continent filtering, geographic names in Install/Manage, larger catalog window,
Install presentation/filter performance and Manage filters. Same-region opposite
BBBike types are blocked; exact owned conflicts name the removal target;
unverified ownership never promises a Manage removal. Provider IMG names/bytes
are unchanged. Full fallback adds the validated current MapRando and BBBike
snapshots to the existing reviewed FZK/OTM fallback, preserving their historical
package identities/proofs. Expected packages:63+177+160+760=1160, four providers.

## Evidence and remaining acceptance

Build31 owner-reported hardware checklist PASS is retained. One MapRando
Lithuania verification read failed without user disconnect; safe cleanup PASS,
retry PASS, root cause unresolved. It remains a documented beta limitation,
not a claimed fix. The owner explicitly waived the actual newer-map update test
for this release and requested the Known issues note that map updates have not
yet been tested; the update feature remains unchanged and the evidence pending.

Before final publication: final source regression/runtime contracts, local32
candidate conflict/offline checks and MapRando install/reconnect/watch check,
Developer ID signed/notarized public28 package validation, real checksum in
manifest/notes, source CI and reviewed public deployment. The current zero SHA
is a temporary marker and must never be deployed. No public release, app/site
deployment, or device file write was performed by this preparation checkpoint.

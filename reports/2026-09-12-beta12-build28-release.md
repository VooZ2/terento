# Terento v1.0.0-beta.12 (build 28) — release preparation

Status: PREPARING, unpublished. The owner approved the English changelog and
three-item update summary, then explicitly selected public build28 (last public
build27; builds28–31-local were private tests). The final private candidate used
33-local to distinguish it from earlier private packages. Public metadata uses
28 as requested; a local build33 user must install the public DMG manually,
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

Final local33 MapRando reinstall/watch-visible acceptance is PASS, reported by
the owner. This is owner-reported hardware evidence, not an independent
on-watch review.
The final public packaging run uses source `adb7e431`: all69/69 test runners
passed in278.5s and Developer ID signing passed. Apple notarization is Accepted
(submission `7155de79-6abc-444c-9c51-cb5919f20264`); stapling, Gatekeeper and
final ZIP/DMG launch checks PASS. Publication remains pending. Full source CI passed before release preparation.

The final DMG checksum is synchronized in manifest and release notes. Before
publication: final metadata/source CI and the reviewed release/site publication. README
contains approved final publication copy, staged locally for that same gate;
its publication wording is not evidence of completed publication.
No public release or app/site deployment was performed by this checkpoint.

The release tag will point at the final reviewed metadata commit. Packaged app
source remains `adb7e431`; verify that intervening changes contain only release
metadata, documentation and generated site content, with no app/runtime or
packaging changes. This avoids the tag-triggered website workflow deploying the
packaged source's placeholder checksum. Record the final metadata commit at publication.

## Final catalog determinism correction

The full regression gate caught two identical fallback decodes producing
different region ordering. Provider-scoped regions with equal name and region
ID lacked a provider tie-break, exposing dictionary iteration order. The fix
adds that tie-break; equality is unchanged. Regression checks exact equality
over12 full1160 catalog reloads and ordering for actual cross-provider name/ID
collisions. Shared contract PASS. The not-yet-handed-off local32 artifact is
superseded; a fresh local33 and public28 are built from the corrected source.

## Final publication copy checks

README publication copy is prepared. Release documentation synchronization and
legal content tests PASS; the complete site plan PASS11/11 runners, including
generator parity, accessibility, provider/API cards, structured data and SEO.
These checks do not establish publication completion. No app, runtime or packaging files changed in this step.

## Final signed artifact receipt — PASS

Packaged app source: `adb7e431`. No app code changed afterward.

- DMG:6800709 bytes; SHA256 `ccf5cd707c2d27d48b523c44c7c93a3045a126d22c3f9dd2458dbb00430b8304`.
- ZIP:6135164 bytes; SHA256 `6293b4e7a49d2796cf38d766412e1c7f19899b544795f11c7be94c6563ec9890`.

Developer ID signing, Apple acceptance, Gatekeeper and both final artifact
launch checks PASS as reported by the completed official packaging pipeline.

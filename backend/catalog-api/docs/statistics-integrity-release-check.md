# Statistics integrity candidate — release checks

This candidate changes derived statistics, never retained telemetry outcomes or
review history. Migration 067 preserves the view's column names, order and types;
068 adds nullable acquisition purpose. Old writers may omit the new column.
Historical purpose remains unknown. Independently selectable MapRando France
contours is a main-map package; attached contours remain optional components.

Before release, run the complete backend suite with PGlite enabled, including
`test_statistics_integrity`, `test_activity_models`, `test_update_activity`, and
`test_map_event_delivery`. The native map-statistics runner generates actual Swift
payloads and sends them through the loopback HTTP/storage contract test. The
operation-diagnostics runner covers a main + contours + second-map failure and
checks both report streams. Neither runner writes a real device.

Use the normal immutable-image deployment path; do not replay old migrations or
run separate manual migration commands. Deploy/verify API acceptance of
`acquisitionPurpose` and migrations before publishing the new app. A rollback to
the previous API keeps additive schema compatibility; publishing the new app
against an older rejecting API is not approved by local tests.

At the deployment gate, compare read-only snapshots for identical period,
timezone, provider and map filters:

- One logical result contributes once; whole-period totals equal bucket totals.
- Resolve/Reopen changes review work only, not retained success/failure counts.
- Fresh diagnostic coverage uses result identity and cannot gain excluded or
  ambiguous matches. Legacy operation/session fields retain their separate scope.
- All-purpose Downloads equals the install/update/unknown breakdown. Do not infer
  historical purpose from missing install/update terminal events.
- Provider dates use eligible successful install/update rows separately; raw
  Event detail retains event timestamps, while statistics uses canonical time.
- Before-write update diagnostics appear with reason/report link, without adding
  a failed-write attempt. Missing identity stays unknown.

Recheck the owner's Lithuania operations against retained server reports and
exact model identity. Local uploaded flags are not proof of server assignment.
The original 137/140 and 16:31/14:16 differences are not considered independently
reconciled merely because local regressions pass. Do not rewrite raw history to
force equal counts. A real Garmin/provider lifecycle retest and any public
compatibility claim remain separate evidence gates.

Checking progress UI, physical write sequencing, releases, packaging versions,
and public compatibility publication are outside this candidate.

The native runner also bootstraps the backend test extra on clean hosts. The
shared workflow contracts exercise that missing-dependency path under available
POSIX, Bash and Zsh shells, including repository paths containing spaces.

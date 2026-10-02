# Immutable production deployment receipt

Use one receipt for each authorized production deployment review. This is an
evidence template, not an instruction to mutate production.

## Candidate identity

- Repository: `VooZ2/terento`
- Branch: `beta`
- Commit: `[40 lowercase hex characters]`
- API image: `ghcr.io/vooz2/terento-catalog@sha256:[64 lowercase hex characters]`
- Image source/revision labels: `[verified]`
- Image build workflow and run: `[URL/ID]`
- Candidate migration inventory: `[001..NNN; exact evidence]`
- Database ledger before deployment: `[exact ordered versions]`

## Required checks

| Evidence | Result | Link or bounded output |
| --- | --- | --- |
| Backend regression suite | `[PASS/FAIL]` | `[CI URL/job]` |
| PostgreSQL migration and idempotency checks | `[PASS/FAIL]` | `[CI URL/job]` |
| Production operations contract suite | `[PASS/FAIL]` | `[CI URL/job]` |
| Workflow and documentation contracts | `[PASS/FAIL]` | `[CI URL/job]` |
| Candidate image source, revision, and digest | `[PASS/FAIL]` | `[receipt/check]` |
| Candidate inventory is canonical and contiguous | `[PASS/FAIL]` | `[bounded output]` |
| Ledger is an exact candidate prefix | `[PASS/FAIL]` | `[bounded output]` |
| Pending runner output and postcheck ledger | `[PASS/FAIL/N/A]` | `[bounded output]` |
| API/scheduler health and release identity | `[PASS/FAIL]` | `[bounded output]` |

## Deployment semantics

The only normal GitHub request is `deploy <digest> <revision>`. The root
helper holds one operations lock from candidate validation through migration,
ledger postcheck, service replacement, health verification, and state update.
The same immutable image is used for the audit, one-shot migration, and
API/scheduler services. The database container and volumes are retained.

The receipt must explicitly record one of:

- `migration: none` — the live ledger already equals the candidate inventory;
- `migration: applied [ordered versions]` — pending versions ran and the exact
  postcondition ledger was confirmed;
- `migration: refused [reason]` — no service replacement was attempted.

If the runner fails or the postcheck does not equal the image inventory, the
old services remain the active deployment. No automatic schema downgrade is
allowed.

## Authorization and privacy

- Production confirmation: `[confirm_production_deploy evidence]`
- Fixed-ops activation guard: `[bounded result]`
- Active forced API target inspected separately: `/usr/local/bin/terento-ci-api-entry`
- Credentials, private keys, environment values, SQL rows, and raw logs: `not included`

Exceptional migrations that are destructive, non-transactional,
downtime-requiring, or dependent on an external backfill stop this normal
receipt flow and require an architecture review. They do not create a second
routine protocol.

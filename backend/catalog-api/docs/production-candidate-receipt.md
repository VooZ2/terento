# Production candidate receipt — template and process

This receipt binds one catalog API OCI image to the exact reviewed source and
records the evidence needed before a separately authorized production
operation. It is evidence, not approval to migrate, deploy, or release.

## Candidate-build gate

Do not build a production candidate until all normative source inputs for that
candidate are committed and Git-tracked. Build from that commit only, with a
clean checkout; do not use a dirty working tree, untracked files, or ignored
operator material as build inputs or as the only source of truth. In
particular, ignored `internal/` or `deploy/` files do not satisfy this gate.
Any required root-owned operation, SSH dispatch, installation, or test source
must have a tracked canonical source and a recorded revision/hash before the
candidate is considered usable for a production migration.

The receipt template itself must be committed before the candidate build. Fill
the completed receipt after the build and retain it as an immutable CI/build
artifact associated with that run; do not amend the source commit just to add
the resulting image digest to it.

Before building, verify at minimum that the commit tracks the complete
canonical migration set through 062, the target-limited migration runner, its
tests, the 062 precheck and postcheck, and the reviewed schema/operations
contracts. Audit the actual image build context and workflow for additional
normative inputs. The candidate must not contain an unreviewed migration after
062. If a required input is missing, ignored, untracked, or differs from the
reviewed content, stop; do not build.

### Migration 060/061 source provenance

The originating dirty working tree contained alternate 060 and 061 SQL files
that were untracked and have no matching commit in its available Git history.
The current beta already has canonical, tracked migrations
`060_missing_diagnostic_review_tasks.sql` and
`061_indexnow_operational_observations.sql`. Keep those as the only executable
060/061 entries. The alternate files are preserved byte-for-byte as `.sql.txt`
provenance records under `docs/migration-source-provenance/`; they are not
migrations and must never be replayed. Production's ledger records versions
060/061 as applied but stores no SQL hash, so neither the alternate local bytes
nor the current beta source prove production-byte parity. Record the archived
source SHA-256 values and retain this limitation in the completed receipt. Do
not replay or edit either source to repair the historical record.

Migration 062 must remain independently applicable to the audited schema
state. The live-like regression must demonstrate that 062 alone reconciles the
missing objects while 060/061 remain only ledger entries; it must not execute
or depend on replaying either migration. Passing this test does not resolve
the historical 060/061 byte-provenance limitation.

The API Dockerfile copies the complete backend source tree. Therefore every
imported runtime module is normative even if it is not named in a migration
list: statistics_exclusions.py and its focused test must be tracked alongside
the event-classification source that imports it. The candidate workflow must
also inspect the immutable image itself and record the exact migration
inventory and in-image hashes before retaining the receipt.

## Completed receipt

Create one copy per candidate. Replace every bracketed field with a value or
`N/A — reason`; do not leave a blank that could be mistaken for a verified
value.

### Artifact identity

- Repository: `VooZ2/terento`
- Candidate purpose / scope: `[e.g. migration-only candidate for target 062]`
- Source commit (full immutable Git SHA): `[40-character SHA]`
- Source ref: `[ref]`
- Clean source checkout verified: `[yes/no; CI run or evidence]`
- OCI image name: `[registry/name]`
- OCI image digest (immutable `sha256:...`, not a tag): `[digest]`
- Embedded OCI revision (for example `org.opencontainers.image.revision`): `[full SHA]`
- Embedded revision equals source commit: `[yes/no; inspection evidence]`
- Build workflow and run URL/ID: `[workflow; URL/ID]`
- Build timestamp (UTC, RFC 3339): `[YYYY-MM-DDThh:mm:ssZ]`

### Migration and contract identity

- Canonical migration set present in image: `[001–062; verification evidence]`
- Later/unreviewed migration files present: `[none, or list — any item is STOP]`
- 060/061 source SHA-256 and provenance limitation: `[values plus explicit no-live-byte-parity statement]`
- `062_reconcile_installation_statistics_schema.sql` SHA-256: `[64 lowercase hex characters]`
- `terento_catalog/migrate.py` source path in image: `[path]`
- `migrate.py` SHA-256: `[64 lowercase hex characters]`
- Migration runner version/revision: `[package version plus source commit; do not infer from tag]`
- Runner invocation validated for this artifact: `[exact --target 062 evidence]`
- Installation-policy schema version: [integer from the tracked schema source]
- Authorization contract revision: [source commit and tracked contract path/hash]
- Schema/contract revision: `[commit SHA and relevant tracked paths/versions]`
- Schema/contract files in the image/build source match that revision: `[yes/no; evidence]`

Record hashes from the committed source and independently verify the
corresponding bytes inside the image identified by the immutable digest. A
source-tree hash alone does not prove what the image contains.

### Test receipt

| Required evidence | Result | Run / log reference |
| --- | --- | --- |
| Backend migration target and ledger validation tests | `[PASS/FAIL]` | `[CI URL, job, log]` |
| 061/062 migration reconciliation and rollback tests | `[PASS/FAIL]` | `[CI URL, job, log]` |
| PostgreSQL-backed 062 migration regression (when required by the workflow) | `[PASS/FAIL/N/A with reason]` | `[CI URL, job, log]` |
| Backend regression suite for the candidate commit | `[PASS/FAIL]` | `[CI URL, job, log]` |
| Image build and image-content verification | `[PASS/FAIL]` | `[CI URL, job, log]` |
| Production operations, target, lock, and SSH boundary contracts | `[PASS/FAIL]` | `[CI URL, job, log]` |
| Workflow contracts and tracked documentation checks | `[PASS/FAIL]` | `[CI URL, job, log]` |
| Native installation-authorization Swift tests (when shared contracts change) | `[PASS/FAIL/N/A with reason]` | `[CI URL, job, log]` |
| Candidate commit whitespace check | `[PASS/FAIL]` | `[CI URL, job, log]` |

Record the exact commit tested. A passing test run for another commit, a local
dirty tree, or a mutable image tag is not a valid receipt.

### Operator verification (before any separately authorized production action)

- Operator: `[name / approved identity]`
- Verification timestamp (UTC, RFC 3339): `[timestamp]`
- Exact target/environment confirmed independently: `[yes/no; non-secret evidence]`
- Candidate digest and embedded revision re-verified: `[yes/no; evidence]`
- 062 SQL and `migrate.py` hashes re-verified inside the candidate image: `[yes/no; evidence]`
- Root-owned fixed operation accepts only the approved immutable digest, expected revision, and explicit target `062`: `[yes/no; installed version/source hash]`
- Migration-only path is serialized against deployment and does not restart/replace API or scheduler: `[yes/no; test/evidence]`
- Read-only precheck and recovery gates satisfied: `[yes/no; references]`
- Operator decision: `[STOP / eligible for a separate explicit approval]`

Any `no`, mismatch, unavailable verification, or ambiguous result is a STOP.
This receipt does not authorize a live SQL write, production deployment,
backup/snapshot creation or restore, or Edge data operation.

## Normative inputs to track before candidate build

At minimum, audit and track the applicable files below at the source commit.
This is a gate list, not an assertion that every path is currently tracked or
that the list exhausts the image build context.

- Migration SQL: the beta's canonical `060_missing_diagnostic_review_tasks.sql` and `061_indexnow_operational_observations.sql`, plus `062_reconcile_installation_statistics_schema.sql`. The alternate 060/061 source files are tracked only as non-executable `.sql.txt` provenance records under `backend/catalog-api/docs/migration-source-provenance/`.
- Exact-target runner and packaging: `backend/catalog-api/src/terento_catalog/migrate.py`, `backend/catalog-api/pyproject.toml`, and `backend/catalog-api/Dockerfile`.
- 062 verification SQL: `backend/catalog-api/tools/installation-statistics-schema-preflight.sql`, `installation-statistics-062-live-precheck.sql`, and `installation-statistics-062-live-postcheck.sql`.
- Migration regressions: `backend/catalog-api/tests/test_migration_061_reconciliation.py` (version uniqueness and archived-source integrity), `test_migration_target_062.py`, `test_migration_062_reconciliation.py`, and `migration_062_postgres.cjs`, plus any shared migration tests exercised by the workflow.
- Reviewed contracts and operator procedure: `backend/catalog-api/docs/schema.md`, `backend/catalog-api/docs/operations.md`, `backend/catalog-api/docs/installation-statistics-062-live-runbook.md`, and `contracts/STATISTICS_CONTRACT.md` when affected by the candidate.
- Build/deploy definition: `.github/workflows/publish-vps-images.yml` and `.github/workflows/deploy-catalog-api.yml`, plus any scripts they invoke that affect the artifact or its production authorization.
- Production operation boundary for a 062 candidate: `scripts/infra/terento-deploy.py`, `terento-deploy-migration.py`, `install-terento-production-ops.py`, `terento-deploy-ssh-entry.py.in` if remote status/migrate is required, and all corresponding tests (`test-terento-deploy.py`, `test-terento-deploy-migration.py`, `test-install-terento-production-ops.py`, `test-terento-deploy-ssh-entry.py`). The SSH template is not installed by the helper installer; include its separately reviewed install/configuration source if it is needed.
- Operation test integration: `Tests/run-ci-production-operations-contract-tests.sh`, `Tests/test-suites.json`, `Tests/README.md`, `Tests/ci-workflow-contract-tests.py`, and `Tests/run-ci-workflow-contract-tests.sh` where affected.
- Candidate/deployment definitions: `.github/workflows/build-catalog-migration-candidate.yml`, `publish-vps-images.yml`, and `deploy-catalog-api.yml`; the candidate workflow is manual and must not acquire production SSH credentials or deploy.
- Current operator truth: `backend/catalog-api/docs/production-operations-protocol.md`, `production-db-recovery.md`, `operations.md`, and `installation-statistics-062-live-runbook.md`.
- Health/retention behavior and regression sources for this candidate: `backend/catalog-api/src/terento_catalog/http_api.py`, `scheduler.py`, and `db.py`; tests `backend/catalog-api/tests/test_http_api.py` and `test_scheduler.py`; plus `backend/catalog-api/README.md` and `Tests/run-backend-api-unit-tests.sh`.
- The source tree/build context and all tested backend migration files remain normative. Ignored files under `internal/` or `deploy/` are insufficient; record the exact tracked paths and installed source revision/hash in the receipt.

Re-run the tracking and clean-checkout gate at build time. A path listed here
that has since been superseded must be replaced with its tracked canonical
successor in the receipt/process before building; never silently omit it.

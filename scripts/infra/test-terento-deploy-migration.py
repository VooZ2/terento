"""Focused, offline tests for the standalone 062 migration operation."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location(
    "terento_deploy_migration", ROOT / "terento-deploy-migration.py"
)
migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration
SPEC.loader.exec_module(migration)

DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40
RECEIPT_SHA = "c" * 64
RUNNER_SHA = "e" * 64
IMAGE = migration.API_IMAGE_REPOSITORY + "@" + DIGEST
DB_ID = "d" * 64
DB_SHORT_ID = DB_ID[:12]


def canonical_inventory(include_063=False):
    last = 64 if include_063 else 63
    return [
        {"name": f"{version:03d}_migration.sql", "version": f"{version:03d}"}
        for version in range(1, last)
    ]


def ledger_through(version):
    return [f"{item:03d}" for item in range(1, version + 1)]


class FakeHost:
    def __init__(self, *, ledger=None):
        self.ledger = ledger if ledger is not None else ledger_through(61)
        self.inventory = canonical_inventory()
        self.actual_sha = RECEIPT_SHA
        self.label_sha = RECEIPT_SHA
        self.actual_runner_sha = RUNNER_SHA
        self.label_runner_sha = RUNNER_SHA
        self.target_enforcement = "verified"
        self.source = migration.EXPECTED_SOURCE
        self.revision = REVISION
        self.repo_digests = [IMAGE]
        self.db_running = True
        self.db_identity_ok = True
        self.db_inspected_id = DB_ID
        self.migration_error = None
        self.migration_output = "Applied migrations: 062\n"
        self.ledger_after_migration = None
        self.docker_calls = []
        self.compose_calls = []
        self.events = []

    def docker(self, *args, timeout=240):
        self.docker_calls.append((args, timeout))
        self.events.append(("docker", args))
        if args == ("pull", IMAGE):
            return ""
        if args == ("image", "inspect", IMAGE):
            return json.dumps([{
                "RepoDigests": self.repo_digests,
                "Config": {"Labels": {
                    "org.opencontainers.image.source": self.source,
                    "org.opencontainers.image.revision": self.revision,
                    "io.terento.migration.062.sha256": self.label_sha,
                    "io.terento.migrate.py.sha256": self.label_runner_sha,
                }},
            }])
        if args[0:1] == ("run",):
            return json.dumps({
                "inventory": self.inventory,
                "migration_062_sha256": self.actual_sha,
                "migrate_py_sha256": self.actual_runner_sha,
                "target_enforcement": self.target_enforcement,
            })
        if args == ("inspect", "--type=container", DB_SHORT_ID):
            return json.dumps([{
                "Id": self.db_inspected_id,
                "Config": {"Labels": {
                    "com.docker.compose.project": (
                        migration.COMPOSE_PROJECT if self.db_identity_ok else "wrong-project"
                    ),
                    "com.docker.compose.service": migration.DB_SERVICE,
                }},
                "State": {"Running": self.db_running},
            }])
        if args[:3] == ("exec", "--user", "postgres"):
            self.assert_read_only_ledger_command(args)
            return json.dumps(self.ledger)
        raise AssertionError(f"Unexpected Docker command: {args!r}")

    @staticmethod
    def assert_read_only_ledger_command(args):
        assert args[3] == DB_ID
        assert args[-1] == migration.LEDGER_SQL
        assert "BEGIN TRANSACTION READ ONLY" in args[-1]
        assert "ROLLBACK" in args[-1]
        assert "CREATE" not in args[-1].upper()

    def compose(self, project, image, *args):
        self.compose_calls.append((project, image, args))
        self.events.append(("compose", (project, image, *args)))
        if args == ("ps", "-q", migration.DB_SERVICE):
            return DB_SHORT_ID + "\n"
        if migration.MIGRATION_SERVICE in args:
            if self.migration_error is not None:
                raise subprocess.CalledProcessError(self.migration_error, "docker compose run")
            if self.ledger_after_migration is not None:
                self.ledger = self.ledger_after_migration
            elif self.migration_output.strip() == "Applied migrations: 062":
                self.ledger = ledger_through(62)
            return self.migration_output
        raise AssertionError(f"Unexpected Compose command: {(project, image, args)!r}")


def request_args(**overrides):
    values = {
        "--target": "062",
        "--image": DIGEST,
        "--revision": REVISION,
        "--expected-migration-062-sha256": RECEIPT_SHA,
        "--expected-migrate-py-sha256": RUNNER_SHA,
    }
    values.update(overrides)
    return [part for pair in values.items() for part in pair]


def run(host, args=None, output=None):
    def emit(message):
        host.events.append(("emit", message))
        if output is not None:
            output.append(message)

    return migration.run_migration(
        request_args() if args is None else args,
        docker=host.docker,
        compose=host.compose,
        emit=emit,
    )


def verify_deploy_schema(host, output=None):
    def emit(message):
        host.events.append(("emit", message))
        if output is not None:
            output.append(message)

    return migration.verify_deploy_schema(
        request_args(), docker=host.docker, compose=host.compose, emit=emit
    )


class MigrationArgumentsTests(unittest.TestCase):
    def test_requires_explicit_target_and_all_immutable_receipt_fields(self):
        expected = migration.MigrationRequest("062", DIGEST, REVISION, RECEIPT_SHA, RUNNER_SHA)
        self.assertEqual(migration.parse_arguments(request_args()), expected)
        invalid_requests = (
            request_args(**{"--target": "061"}),
            request_args(**{"--target": ""}),
            request_args(**{"--image": "latest"}),
            request_args(**{"--image": migration.API_IMAGE_REPOSITORY + ":latest"}),
            request_args(**{"--image": "sha256:" + "A" * 64}),
            request_args(**{"--revision": "working-tree"}),
            request_args(**{"--revision": "b" * 39}),
            request_args(**{"--revision": "B" * 40}),
            request_args(**{"--expected-migration-062-sha256": "c" * 63}),
            request_args(**{"--expected-migrate-py-sha256": "e" * 63}),
            request_args()[:-2],
            request_args() + ["--image", DIGEST],
            request_args(**{"--target": 62}),
            ["--target", "062", "--image", DIGEST, "--revision", REVISION,
             "--expected-sha256", RECEIPT_SHA],
        )
        for args in invalid_requests:
            with self.subTest(args=args), self.assertRaises(migration.MigrationError):
                migration.parse_arguments(args)

    def test_invalid_request_runs_no_host_commands(self):
        host = FakeHost()
        with self.assertRaises(migration.MigrationError):
            run(host, request_args(**{"--image": "terento-catalog:latest"}))
        self.assertEqual(host.docker_calls, [])
        self.assertEqual(host.compose_calls, [])


class EmbeddedArtifactAuditTests(unittest.TestCase):
    def test_read_only_audit_accepts_current_062_runner_contract(self):
        repository = ROOT.parents[1]
        script = migration.IMAGE_AUDIT_PYTHON.replace(
            "/app/src/terento_catalog/migrations",
            str((repository / "backend/catalog-api/src/terento_catalog/migrations").resolve()),
        ).replace(
            "/app/src/terento_catalog/migrate.py",
            str((repository / "backend/catalog-api/src/terento_catalog/migrate.py").resolve()),
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads(result.stdout)
        self.assertEqual(
            [entry["version"] for entry in audit["inventory"]],
            list(migration.EXPECTED_MIGRATION_VERSIONS),
        )
        self.assertRegex(audit["migration_062_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(audit["migrate_py_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(audit["target_enforcement"], "verified")


class MigrationOperationTests(unittest.TestCase):
    def test_pulls_and_verifies_only_fixed_api_digest_then_applies_062(self):
        host = FakeHost()
        output = []
        result = run(host, output=output)

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["target"], "062")
        self.assertEqual(result["image"], IMAGE)
        self.assertEqual(result["revision"], REVISION)
        self.assertEqual(result["migration_062_sha256"], RECEIPT_SHA)
        self.assertEqual(result["migrate_py_sha256"], RUNNER_SHA)
        self.assertEqual(result["migration_inventory"], canonical_inventory())
        self.assertIn("Applied migrations: 062", output)
        self.assertEqual(host.docker_calls[0][0], ("pull", IMAGE))
        self.assertEqual(host.docker_calls[1][0], ("image", "inspect", IMAGE))
        audit_args = host.docker_calls[2][0]
        self.assertEqual(audit_args[0], "run")
        self.assertIn("--pull=never", audit_args)
        self.assertEqual(audit_args[audit_args.index("--network") + 1], "none")
        self.assertIn("--read-only", audit_args)
        self.assertEqual(audit_args[audit_args.index("--cap-drop") + 1], "ALL")
        self.assertEqual(audit_args[audit_args.index("--security-opt") + 1], "no-new-privileges")
        self.assertEqual(audit_args[audit_args.index("--entrypoint") + 1], "python")
        self.assertIn(IMAGE, audit_args)
        audit_program = audit_args[audit_args.index("-c") + 1]
        self.assertIn("/app/src/terento_catalog/migrate.py", audit_program)
        self.assertIn("ast.parse", audit_program)
        self.assertIn("expected_target_branch", audit_program)
        self.assertEqual(
            next(call for call in reversed(host.compose_calls)
                 if migration.MIGRATION_SERVICE in call[2]),
            ("api", IMAGE, (
                "--profile", "manual", "run", "--rm", "--no-deps", "-T",
                "catalog-migrate", "terento-catalog-migrate", "--target", "062",
            )),
        )
        self.assertEqual(
            [
                call[2][-1] if call[2][0] == "ps" else call[2][call[2].index("-T") + 1]
                for call in host.compose_calls
            ],
            ["catalog-db", "catalog-db", "catalog-migrate", "catalog-db"],
        )
        self.assertTrue(any("MIGRATION_CANDIDATE" in line
                            and IMAGE in line
                            and REVISION in line
                            and RECEIPT_SHA in line
                            and RUNNER_SHA in line
                            and "target_enforcement=verified" in line for line in output))
        candidate_event = next(i for i, event in enumerate(host.events)
                               if event[0] == "emit" and "MIGRATION_CANDIDATE" in event[1])
        migration_event = next(i for i, event in enumerate(host.events)
                               if event[0] == "compose" and migration.MIGRATION_SERVICE in event[1])
        self.assertLess(candidate_event, migration_event)
        rendered_commands = repr(host.events)
        self.assertNotIn("catalog-api", rendered_commands)
        self.assertNotIn("catalog-scheduler", rendered_commands)
        self.assertNotIn("docker-compose down", rendered_commands)

    def test_expected_receipt_hash_must_match_actual_file_sha(self):
        host = FakeHost()
        host.actual_sha = "e" * 64
        host.label_sha = host.actual_sha
        output = []
        with self.assertRaisesRegex(migration.MigrationError, "receipt"):
            run(host, request_args(**{"--expected-migration-062-sha256": RECEIPT_SHA}), output)
        self.assertTrue(any("migration_062_sha256=" + host.actual_sha in line for line in output))
        self.assertEqual(host.compose_calls, [])
        self.assertFalse(any(call[0][0] == "exec" for call in host.docker_calls))

    def test_expected_runner_receipt_hash_must_match_actual_file_sha(self):
        host = FakeHost()
        host.actual_runner_sha = "f" * 64
        host.label_runner_sha = host.actual_runner_sha
        output = []
        with self.assertRaisesRegex(migration.MigrationError, "migrate.py SHA-256"):
            run(host, request_args(**{"--expected-migrate-py-sha256": RUNNER_SHA}), output)
        self.assertTrue(any("migrate_py_sha256=" + host.actual_runner_sha in line for line in output))
        self.assertEqual(host.compose_calls, [])

    def test_actual_sha_must_match_candidate_image_label(self):
        host = FakeHost()
        host.label_sha = "e" * 64
        with self.assertRaisesRegex(migration.MigrationError, "image label"):
            run(host)
        self.assertEqual(host.compose_calls, [])

    def test_runner_sha_label_and_artifact_enforcement_are_required(self):
        cases = (
            ("label_runner_sha", "not-a-sha", "migrate.py SHA-256 label"),
            ("label_runner_sha", "f" * 64, "does not match its image label"),
            ("actual_runner_sha", "f" * 64, "does not match its image label"),
            ("target_enforcement", "uncertain", "target enforcement"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                host = FakeHost()
                setattr(host, field, value)
                with self.assertRaisesRegex(migration.MigrationError, message):
                    run(host)
                self.assertEqual(host.compose_calls, [])
                self.assertFalse(any(call[0][0] == "exec" for call in host.docker_calls))

    def test_candidate_repository_digest_must_be_exact(self):
        invalid_repo_digests = (
            [migration.API_IMAGE_REPOSITORY + "@sha256:" + "e" * 64],
            IMAGE,
        )
        for repo_digests in invalid_repo_digests:
            with self.subTest(repo_digests=repo_digests):
                host = FakeHost()
                host.repo_digests = repo_digests
                with self.assertRaisesRegex(migration.MigrationError, "digest"):
                    run(host)
                self.assertEqual(host.compose_calls, [])

    def test_source_revision_and_label_are_verified(self):
        cases = (
            ("source", "https://example.invalid/wrong", "source label"),
            ("revision", "e" * 40, "revision label"),
            ("label_sha", "not-a-sha", "SHA-256 label"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                host = FakeHost()
                setattr(host, field, value)
                with self.assertRaisesRegex(migration.MigrationError, message):
                    run(host)
                self.assertEqual(host.compose_calls, [])

    def test_noncanonical_or_later_candidate_migration_inventory_is_rejected(self):
        cases = (
            canonical_inventory(include_063=True),
            canonical_inventory()[:-1],
            canonical_inventory() + [{"name": "062_duplicate.sql", "version": "062"}],
        )
        for inventory in cases:
            with self.subTest(count=len(inventory)), self.assertRaises(migration.MigrationError):
                host = FakeHost()
                host.inventory = inventory
                run(host)
            self.assertEqual(host.compose_calls, [])

    def test_later_migration_is_named_for_operator_and_never_executed(self):
        host = FakeHost()
        host.inventory = canonical_inventory(include_063=True)
        output = []
        with self.assertRaisesRegex(migration.MigrationError, r"after target 062: 063_migration\.sql"):
            run(host, output=output)
        self.assertEqual(host.compose_calls, [])
        self.assertFalse(any(call[0][0] == "exec" for call in host.docker_calls))

    def test_db_service_must_already_be_running_and_identified(self):
        for field, value in (
                ("db_running", False), ("db_identity_ok", False),
                ("db_inspected_id", "f" * 64)):
            with self.subTest(field=field):
                host = FakeHost()
                setattr(host, field, value)
                with self.assertRaises(migration.MigrationError):
                    run(host)
                self.assertEqual(
                    host.compose_calls,
                    [("api", IMAGE, ("ps", "-q", "catalog-db"))],
                )
                self.assertFalse(any(call[0][0] == "exec" for call in host.docker_calls))

    def test_exact_001_through_061_ledger_runs_only_catalog_migrate(self):
        host = FakeHost(ledger=ledger_through(61))
        run(host)
        migration_call = next(call for call in reversed(host.compose_calls)
                              if migration.MIGRATION_SERVICE in call[2])
        self.assertEqual(
            migration_call[2][-4:],
            ("catalog-migrate", "terento-catalog-migrate", "--target", "062"),
        )
        self.assertTrue(any(
            call[0][0:1] == ("exec",) and "BEGIN TRANSACTION READ ONLY" in call[0][-1]
            for call in host.docker_calls
        ))

    def test_compose_run_receives_explicit_migration_executable(self):
        """Compose run SERVICE COMMAND replaces the service command."""
        host = FakeHost(ledger=ledger_through(61))
        run(host)
        migration_call = next(call for call in reversed(host.compose_calls)
                              if migration.MIGRATION_SERVICE in call[2])
        args = migration_call[2]
        service_index = args.index(migration.MIGRATION_SERVICE)
        self.assertEqual(
            args[service_index + 1:service_index + 4],
            ("terento-catalog-migrate", "--target", "062"),
        )

    def test_exact_001_through_062_is_explicit_noop(self):
        host = FakeHost(ledger=ledger_through(62))
        output = []
        result = run(host, output=output)
        self.assertEqual(result["status"], "already_applied")
        self.assertIn("ALREADY APPLIED 062; no migration container was run.", output)
        self.assertFalse(any(migration.MIGRATION_SERVICE in call[2] for call in host.compose_calls))

    def test_concurrent_apply_returning_noop_is_confirmed_as_already_applied(self):
        host = FakeHost()
        host.migration_output = "Applied migrations: none\n"
        host.ledger_after_migration = ledger_through(62)
        output = []
        result = run(host, output=output)
        self.assertEqual(result["status"], "already_applied")
        self.assertIn(
            "ALREADY APPLIED 062; no migration change was made by this invocation.",
            output,
        )

    def test_runner_noop_without_confirmed_062_ledger_is_not_pass(self):
        host = FakeHost()
        host.migration_output = "Applied migrations: none\n"
        with self.assertRaisesRegex(migration.MigrationError, "no-op"):
            run(host)
        self.assertFalse(any("MIGRATION_PASS" in event[1]
                             for event in host.events if event[0] == "emit"))

    def test_success_output_requires_exact_read_only_ledger_postcondition(self):
        host = FakeHost()
        host.ledger_after_migration = ledger_through(61)
        with self.assertRaisesRegex(migration.MigrationError, "exact 001-062 ledger"):
            run(host)
        self.assertFalse(any("MIGRATION_PASS" in event[1]
                             for event in host.events if event[0] == "emit"))
        self.assertTrue(any(event[0] == "docker" and event[1][0] == "exec"
                            for event in host.events))

    def test_gapped_earlier_or_later_ledgers_are_refused(self):
        invalid_ledgers = (
            ledger_through(60),
            [version for version in ledger_through(61) if version != "017"],
            ledger_through(62) + ["063"],
            ["001", "1", *ledger_through(2)[1:]],
        )
        for ledger in invalid_ledgers:
            with self.subTest(ledger=ledger[-3:]), self.assertRaises(migration.MigrationError):
                host = FakeHost(ledger=ledger)
                run(host)
                self.assertFalse(any(migration.MIGRATION_SERVICE in call[2]
                                     for call in host.compose_calls))
            self.assertFalse(any(migration.MIGRATION_SERVICE in call[2]
                                 for call in host.compose_calls))

    def test_failed_migration_propagates_without_api_or_scheduler_mutation(self):
        host = FakeHost()
        host.migration_error = 17
        with self.assertRaisesRegex(migration.MigrationError, "exit status 17"):
            run(host)
        migration_calls = [event for event in host.events
                           if event[0] == "compose" and migration.MIGRATION_SERVICE in event[1]]
        self.assertEqual(len(migration_calls), 1)
        self.assertEqual(
            migration_calls[0][1][-4:],
            ("catalog-migrate", "terento-catalog-migrate", "--target", "062"),
        )
        self.assertEqual(host.events[-1], migration_calls[0])
        self.assertFalse(any("catalog-api" in repr(event) or "catalog-scheduler" in repr(event)
                             for event in host.events))


class DeploymentSchemaGateTests(unittest.TestCase):
    def test_deploy_requires_exact_candidate_and_live_001_through_062(self):
        host = FakeHost(ledger=ledger_through(62))
        output = []
        result = verify_deploy_schema(host, output)
        self.assertEqual(result["ledger"], "001-062")
        self.assertEqual(result["migration_inventory"], canonical_inventory())
        self.assertIn("DEPLOY_SCHEMA_PASS applied=001-062", output)
        self.assertEqual(host.compose_calls, [
            ("api", IMAGE, ("ps", "-q", "catalog-db")),
        ])
        self.assertFalse(any(migration.MIGRATION_SERVICE in call[2]
                             for call in host.compose_calls))

    def test_deploy_refuses_pending_062_without_running_any_migration(self):
        host = FakeHost(ledger=ledger_through(61))
        with self.assertRaisesRegex(migration.MigrationError, "separately approved migration-only"):
            verify_deploy_schema(host)
        self.assertEqual(host.compose_calls, [
            ("api", IMAGE, ("ps", "-q", "catalog-db")),
        ])
        self.assertFalse(any(migration.MIGRATION_SERVICE in call[2]
                             for call in host.compose_calls))

    def test_deploy_refuses_063_candidate_before_query_or_service_mutation(self):
        host = FakeHost(ledger=ledger_through(62))
        host.inventory = canonical_inventory(include_063=True)
        with self.assertRaisesRegex(migration.MigrationError, r"after target 062: 063_migration\.sql"):
            verify_deploy_schema(host)
        self.assertEqual(host.compose_calls, [])
        self.assertFalse(any(call[0][0] == "exec" for call in host.docker_calls))


if __name__ == "__main__":
    unittest.main()

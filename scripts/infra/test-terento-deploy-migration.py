"""Offline contracts for the generic migration stage of deployment."""

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("terento_deploy_migration", ROOT / "terento-deploy-migration.py")
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)

DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40
IMAGE = migration.API_IMAGE_REPOSITORY + "@" + DIGEST
DB_ID = "d" * 64
DB_SHORT_ID = DB_ID[:12]


def inventory_through(version):
    return [
        {"name": f"{number:03d}_migration.sql", "version": f"{number:03d}"}
        for number in range(1, version + 1)
    ]


def ledger_through(version):
    return [f"{number:03d}" for number in range(1, version + 1)]


class FakeHost:
    def __init__(self, *, inventory=None, ledger=None):
        self.inventory = inventory or inventory_through(63)
        self.ledger = ledger if ledger is not None else ledger_through(62)
        self.migration_output = None
        self.migration_error = None
        self.ledger_after_migration = None
        self.compose_calls = []
        self.docker_calls = []

    def docker(self, *args, timeout=240):
        self.docker_calls.append((args, timeout))
        if args == ("image", "inspect", IMAGE):
            return json.dumps([{
                "RepoDigests": [IMAGE],
                "Config": {"Labels": {
                    "org.opencontainers.image.source": migration.EXPECTED_SOURCE,
                    "org.opencontainers.image.revision": REVISION,
                }},
            }])
        if args[:1] == ("run",):
            return json.dumps({"inventory": self.inventory})
        if args == ("inspect", "--type=container", DB_SHORT_ID):
            return json.dumps([{
                "Id": DB_ID,
                "Config": {"Labels": {
                    "com.docker.compose.project": migration.COMPOSE_PROJECT,
                    "com.docker.compose.service": migration.DB_SERVICE,
                }},
                "State": {"Running": True},
            }])
        if args[:3] == ("exec", "--user", "postgres"):
            return json.dumps(self.ledger)
        raise AssertionError(f"unexpected docker call: {args!r}")

    def compose(self, project, image, *args):
        self.compose_calls.append((project, image, args))
        if args == ("ps", "-q", migration.DB_SERVICE):
            return DB_SHORT_ID + "\n"
        if migration.MIGRATION_SERVICE in args:
            if self.migration_error is not None:
                raise subprocess.CalledProcessError(self.migration_error, "docker compose run")
            pending = [entry["version"] for entry in self.inventory[len(self.ledger):]]
            self.ledger = self.ledger_after_migration if self.ledger_after_migration is not None else self.ledger + pending
            return self.migration_output or "Applied migrations: " + ", ".join(pending)
        raise AssertionError(f"unexpected compose call: {(project, image, args)!r}")


def run(host, output=None):
    output = [] if output is None else output
    result = migration.migrate_candidate(
        IMAGE, DIGEST, REVISION, docker=host.docker, compose=host.compose, emit=output.append,
    )
    return result, output


class GenericMigrationTests(unittest.TestCase):
    def test_062_to_063_applies_only_pending_migration_from_candidate_image(self):
        host = FakeHost()
        host.migration_output = "Applied migrations: 063\n"
        result, output = run(host)
        self.assertEqual(result["applied"], ["063"])
        self.assertEqual(host.ledger, ledger_through(63))
        migration_calls = [args for _, _, args in host.compose_calls if migration.MIGRATION_SERVICE in args]
        self.assertEqual(len(migration_calls), 1)
        self.assertIn("--no-deps", migration_calls[0])
        self.assertNotIn("--target", migration_calls[0])
        self.assertTrue(any("pending=063" in line for line in output))
        self.assertTrue(all(image == IMAGE for _, image, _ in host.compose_calls))

    def test_063_to_065_applies_multiple_pending_migrations_in_order(self):
        host = FakeHost(inventory=inventory_through(65), ledger=ledger_through(63))
        host.migration_output = "Applied migrations: 064, 065\n"
        result, _ = run(host)
        self.assertEqual(result["applied"], ["064", "065"])
        self.assertEqual(host.ledger, ledger_through(65))

    def test_equal_inventory_is_a_verified_noop(self):
        host = FakeHost(ledger=ledger_through(63))
        result, _ = run(host)
        self.assertEqual(result["status"], "already_applied")
        self.assertFalse(any(migration.MIGRATION_SERVICE in args for _, _, args in host.compose_calls))

    def test_db_gap_and_ahead_are_rejected_before_runner(self):
        for ledger in (ledger_through(60) + ["062"], ledger_through(63) + ["064"]):
            with self.subTest(ledger=ledger):
                host = FakeHost(ledger=ledger)
                with self.assertRaisesRegex(migration.MigrationError, "exact canonical prefix"):
                    run(host)
                self.assertFalse(any(migration.MIGRATION_SERVICE in args for _, _, args in host.compose_calls))

    def test_missing_ledger_fails_closed(self):
        host = FakeHost()
        original = host.docker

        def missing(*args, **kwargs):
            if args[:3] == ("exec", "--user", "postgres"):
                raise subprocess.CalledProcessError(1, "psql")
            return original(*args, **kwargs)

        host.docker = missing
        with self.assertRaisesRegex(migration.MigrationError, "Docker operation"):
            run(host)

    def test_candidate_inventory_gaps_aliases_and_malformed_names_are_rejected(self):
        cases = (
            inventory_through(62) + [{"name": "064_gap.sql", "version": "064"}],
            inventory_through(63) + [{"name": "063_alias.sql", "version": "063"}],
            inventory_through(62) + [{"name": "063 bad.sql", "version": "063"}],
        )
        for inventory in cases:
            with self.subTest(inventory=inventory[-1]):
                with self.assertRaises(migration.MigrationError):
                    run(FakeHost(inventory=inventory))

    def test_runner_failure_and_postcheck_mismatch_never_pass(self):
        host = FakeHost()
        host.migration_error = 1
        with self.assertRaisesRegex(migration.MigrationError, "Compose operation"):
            run(host)
        host = FakeHost()
        host.migration_output = "Applied migrations: 063\n"
        host.ledger_after_migration = ledger_through(62)
        with self.assertRaisesRegex(migration.MigrationError, "ledger was not confirmed"):
            run(host)


if __name__ == "__main__":
    unittest.main()

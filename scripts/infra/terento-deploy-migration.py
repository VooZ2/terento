#!/usr/bin/env python3
"""Generic forward-migration checks used inside the immutable deploy path.

This module is not an operator command. The root deployment helper imports it
after acquiring the shared operations lock, verifies the exact candidate image,
applies only the candidate image's pending migrations, and verifies the ledger
again before service replacement.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Callable, Protocol


API_IMAGE_REPOSITORY = "ghcr.io/vooz2/terento-catalog"
EXPECTED_SOURCE = "https://github.com/VooZ2/terento"
COMPOSE_PROJECT = "terento-catalog"
DB_SERVICE = "catalog-db"
MIGRATION_SERVICE = "catalog-migrate"

LEDGER_SQL = """BEGIN TRANSACTION READ ONLY;
SELECT COALESCE(json_agg(version ORDER BY version), '[]'::json)::text
FROM schema_migrations;
ROLLBACK;"""

# This runs in a network-disabled, read-only container of the already pulled
# candidate image. The image is the source of truth for the migration list.
IMAGE_AUDIT_PYTHON = r'''import glob, json, os, re
root = "/app/src/terento_catalog/migrations"
paths = sorted(glob.glob(root + "/*.sql"))
inventory = []
for path in paths:
    name = os.path.basename(path)
    match = re.fullmatch(r"(\d{3})_[A-Za-z0-9_.-]+\.sql", name)
    if match is None:
        raise SystemExit("malformed migration filename: " + name)
    inventory.append({"name": name, "version": match.group(1)})
if not inventory:
    raise SystemExit("candidate image contains no SQL migrations")
versions = [entry["version"] for entry in inventory]
expected = [f"{index:03d}" for index in range(1, len(versions) + 1)]
if versions != expected:
    raise SystemExit("candidate image migration inventory is not contiguous")
print(json.dumps({"inventory": inventory}, sort_keys=True))
'''


class MigrationError(RuntimeError):
    """A safe, operator-facing refusal or failed migration operation."""


class DockerCall(Protocol):
    def __call__(self, *args: str, timeout: int = ...) -> str: ...


class ComposeCall(Protocol):
    def __call__(self, project: str, image: str | None, *args: str) -> str: ...


def _json_object(raw: str, description: str) -> dict:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise MigrationError(f"Could not validate {description}.") from None
    if not isinstance(value, dict):
        raise MigrationError(f"Could not validate {description}.")
    return value


def _single_inspect_object(raw: str, description: str) -> dict:
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise MigrationError(f"Could not validate {description}.") from None
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise MigrationError(f"Could not validate {description}.")
    return values[0]


def _docker(docker: DockerCall, *args: str, timeout: int = 240) -> str:
    try:
        return docker(*args, timeout=timeout)
    except subprocess.CalledProcessError as error:
        raise MigrationError(f"Docker operation failed with exit status {error.returncode}.") from None


def _compose(compose: ComposeCall, project: str, image: str | None, *args: str) -> str:
    try:
        return compose(project, image, *args)
    except subprocess.CalledProcessError as error:
        raise MigrationError(f"Compose operation failed with exit status {error.returncode}.") from None


def _image_labels(image: str, digest: str, revision: str, docker: DockerCall) -> dict:
    data = _single_inspect_object(
        _docker(docker, "image", "inspect", image, timeout=30),
        "candidate image",
    )
    if image not in data.get("RepoDigests", []):
        raise MigrationError("Pulled image digest does not match the requested candidate.")
    config = data.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        raise MigrationError("Candidate image labels are missing or malformed.")
    if labels.get("org.opencontainers.image.source") != EXPECTED_SOURCE:
        raise MigrationError("Candidate image source label is not the Terento repository.")
    if labels.get("org.opencontainers.image.revision") != revision:
        raise MigrationError("Candidate image revision label does not match the requested revision.")
    return labels


def candidate_inventory(image: str, digest: str, revision: str, docker: DockerCall) -> list[dict]:
    """Validate identity and return the canonical migration inventory in the image."""
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        or not re.fullmatch(r"[0-9a-f]{40}", revision)
        or image != f"{API_IMAGE_REPOSITORY}@{digest}"
    ):
        raise MigrationError("Candidate image identity is not an immutable Terento API reference.")
    _image_labels(image, digest, revision, docker)
    audit = _json_object(
        _docker(
            docker,
            "run", "--rm", "--pull=never", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit=64", "--memory=128m", "--entrypoint", "python", image,
            "-B", "-c", IMAGE_AUDIT_PYTHON, timeout=60,
        ),
        "candidate migration inventory",
    )
    inventory = audit.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise MigrationError("Candidate image did not provide a migration inventory.")
    if any(
        not isinstance(entry, dict)
        or not isinstance(entry.get("name"), str)
        or not re.fullmatch(r"\d{3}_[A-Za-z0-9_.-]+\.sql", entry["name"])
        or entry.get("version") != entry["name"][:3]
        for entry in inventory
    ):
        raise MigrationError("Candidate image contains a malformed migration filename.")
    versions = [entry["version"] for entry in inventory]
    if versions != [f"{index:03d}" for index in range(1, len(versions) + 1)]:
        raise MigrationError("Candidate image migration inventory is not contiguous.")
    return inventory


def _running_database_container(compose: ComposeCall, docker: DockerCall, image: str) -> str:
    ids = _compose(compose, "api", image, "ps", "-q", DB_SERVICE).split()
    if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", ids[0]):
        raise MigrationError("Expected exactly one existing catalog database container.")
    data = _single_inspect_object(
        _docker(docker, "inspect", "--type=container", ids[0], timeout=30),
        "catalog database container",
    )
    config = data.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    state = data.get("State")
    if (
        not isinstance(labels, dict)
        or not isinstance(state, dict)
        or labels.get("com.docker.compose.project") != COMPOSE_PROJECT
        or labels.get("com.docker.compose.service") != DB_SERVICE
        or state.get("Running") is not True
    ):
        raise MigrationError("The existing catalog database service is not running with the expected identity.")
    container_id = data.get("Id")
    if not isinstance(container_id, str) or not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise MigrationError("Could not validate the existing catalog database container identity.")
    return container_id


def read_ledger(database_id: str, docker: DockerCall) -> list[str]:
    """Read the existing ledger without creating or changing database state."""
    raw = _docker(
        docker, "exec", "--user", "postgres", database_id, "sh", "-c",
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"',
        "terento-migration-precheck", LEDGER_SQL, timeout=30,
    )
    try:
        ledger = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise MigrationError("Could not validate the read-only migration ledger precheck.") from None
    if not isinstance(ledger, list) or any(not isinstance(version, str) for version in ledger):
        raise MigrationError("Could not validate the read-only migration ledger precheck.")
    return ledger


def _validate_ledger(ledger: list[str], inventory: list[dict]) -> None:
    versions = [entry["version"] for entry in inventory]
    if ledger != versions[: len(ledger)]:
        raise MigrationError(
            "Database migration ledger is not an exact canonical prefix of the candidate inventory."
        )


def migrate_candidate(
    image: str,
    digest: str,
    revision: str,
    *,
    docker: DockerCall,
    compose: ComposeCall,
    emit: Callable[[str], None] = print,
) -> dict:
    """Apply pending migrations from one immutable image and verify the ledger."""
    inventory = candidate_inventory(image, digest, revision, docker)
    versions = [entry["version"] for entry in inventory]
    database_id = _running_database_container(compose, docker, image)
    ledger = read_ledger(database_id, docker)
    _validate_ledger(ledger, inventory)
    pending = versions[len(ledger):]
    emit(
        "MIGRATION_PRECHECK_PASS "
        f"image={image} revision={revision} applied={','.join(ledger) or 'none'} "
        f"pending={','.join(pending) or 'none'}"
    )
    if not pending:
        emit("MIGRATION_PASS applied=none")
        return {
            "status": "already_applied",
            "image": image,
            "revision": revision,
            "inventory": inventory,
            "applied": [],
            "ledger": ledger,
        }

    if _running_database_container(compose, docker, image) != database_id:
        raise MigrationError("Catalog database container changed after the ledger precheck; migration refused.")
    result = _compose(
        compose, "api", image, "--profile", "manual", "run", "--rm", "--no-deps", "-T",
        MIGRATION_SERVICE, "terento-catalog-migrate",
    )
    expected_output = "Applied migrations: " + ", ".join(pending)
    if [line.strip() for line in result.splitlines() if line.strip()] != [expected_output]:
        raise MigrationError(f"Migration runner did not report exactly '{expected_output}'.")
    if _running_database_container(compose, docker, image) != database_id:
        raise MigrationError("Catalog database container changed before the migration postcondition check.")
    final_ledger = read_ledger(database_id, docker)
    if final_ledger != versions:
        raise MigrationError("Migration runner reported success but the candidate ledger was not confirmed.")
    emit("MIGRATION_POSTCONDITION_PASS applied=" + ",".join(final_ledger))
    return {
        "status": "applied",
        "image": image,
        "revision": revision,
        "inventory": inventory,
        "applied": pending,
        "ledger": final_ledger,
    }

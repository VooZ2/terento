#!/usr/bin/env python3
"""Migration-only production operation for the Terento catalog.

The tracked root-helper imports this module and calls ``run_migration`` after
acquiring its shared, exclusive production-operations lock. This module does
not create or acquire a lock. The caller must hold the same lock used by deploy
for the full call, so migrations cannot race deployments or other migrations.

Dependencies are injected to keep this module importable and testable without
root access or a live VPS:

* ``docker(*args, timeout=...)`` runs the fixed Docker CLI on the production
  host and returns stdout.
* ``compose(project, image, *args)`` runs the existing root-owned Compose
  wrapper. Only ``catalog-db`` inspection and the ``catalog-migrate`` one-shot
  are requested here; ``catalog-api`` and ``catalog-scheduler`` are never
  started, stopped, recreated, or otherwise operated on.

The CLI-facing arguments are exactly equivalent to:
``migrate --target 062 --image sha256:<digest> --revision <40hex>
--expected-migration-062-sha256 <64hex>``.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence


API_IMAGE_REPOSITORY = "ghcr.io/vooz2/terento-catalog"
EXPECTED_SOURCE = "https://github.com/VooZ2/terento"
COMPOSE_PROJECT = "terento-catalog"
DB_SERVICE = "catalog-db"
MIGRATION_SERVICE = "catalog-migrate"
EXPECTED_MIGRATION_VERSIONS = tuple(f"{version:03d}" for version in range(1, 63))

LEDGER_SQL = """BEGIN TRANSACTION READ ONLY;
SELECT COALESCE(json_agg(version ORDER BY version), '[]'::json)::text
FROM schema_migrations;
ROLLBACK;"""

# This runs only in a fresh, network-disabled container of the pinned candidate
# image. It reads the migration directory, hashes migration 062 and migrate.py,
# and statically checks the artifact's target/ledger enforcement. It never
# imports or executes the migration runner.
IMAGE_AUDIT_PYTHON = r'''import glob, hashlib, json, os, re
import ast
root = "/app/src/terento_catalog/migrations"
paths = sorted(path for path in glob.glob(root + "/*.sql")
               if not os.path.basename(path).startswith("._"))
inventory = []
for path in paths:
    name = os.path.basename(path)
    match = re.match(r"^(\d+)_.*\.sql$", name)
    inventory.append({"name": name, "version": match.group(1) if match else None})
targets = [path for path in paths
           if re.match(r"^062_.+\.sql$", os.path.basename(path))]
digest = None
if len(targets) == 1:
    with open(targets[0], "rb") as migration:
        digest = hashlib.sha256(migration.read()).hexdigest()
runner_path = "/app/src/terento_catalog/migrate.py"
with open(runner_path, "rb") as runner_file:
    runner_bytes = runner_file.read()
runner_sha = hashlib.sha256(runner_bytes).hexdigest()
runner = ast.parse(runner_bytes.decode("utf-8"), filename=runner_path)

def dump(source):
    return ast.dump(ast.parse(source).body[0], include_attributes=False)

functions = {node.name: node for node in runner.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
apply_fn = functions.get("apply_migrations")
main_fn = functions.get("main")
if apply_fn is None or main_fn is None or not apply_fn.body:
    raise SystemExit("migration runner enforcement is not recognizable")
expected_guard = "\n".join((
    'if target not in (None, "062"):',
    '    raise RuntimeError("only the exact --target 062 is supported")',
))
if dump(ast.unparse(apply_fn.body[0])) != dump(expected_guard):
    raise SystemExit("migration runner target guard differs from reviewed contract")
expected_target_branch = "\n".join((
    'if target == "062":',
    '    expected_files = [f"{version:03d}" for version in range(1, 63)]',
    '    actual_files = [_migration_version(file) for file in files]',
    '    if actual_files != expected_files:',
    '        raise RuntimeError("--target 062 requires exactly one canonical migration file for every version 001 through 062, with no later files")',
))
expected_ledger_branch = "\n".join((
    'if target == "062":',
    '    expected_applied = set(expected_files[:-1])',
    '    if applied == expected_applied | {"062"}:',
    '        return []',
    '    if applied != expected_applied:',
    '        raise RuntimeError("--target 062 requires the exact applied ledger 001 through 061; 060-only, aliases, holes, and later versions are rejected")',
    '    files = [files[-1]]',
))
branches = [node for node in ast.walk(apply_fn)
            if isinstance(node, ast.If)
            and dump(ast.unparse(node)) in
                {dump(expected_target_branch), dump(expected_ledger_branch)}]
if len(branches) != 2 or {dump(ast.unparse(node)) for node in branches} != {
        dump(expected_target_branch), dump(expected_ledger_branch)}:
    raise SystemExit("migration runner 062 inventory or ledger enforcement differs from reviewed contract")
target_args = [node for node in ast.walk(main_fn)
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and node.func.attr == "add_argument"
               and node.args and isinstance(node.args[0], ast.Constant)
               and node.args[0].value == "--target"]
if len(target_args) != 1:
    raise SystemExit("migration runner does not expose one explicit --target option")
choices = next((keyword.value for keyword in target_args[0].keywords
                if keyword.arg == "choices"), None)
if (not isinstance(choices, ast.Tuple) or len(choices.elts) != 1
        or not isinstance(choices.elts[0], ast.Constant)
        or choices.elts[0].value != "062"):
    raise SystemExit("migration runner target choices are not restricted to 062")
target_calls = [node for node in ast.walk(main_fn)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "apply_migrations"]
if len(target_calls) != 1 or not any(
        keyword.arg == "target" and isinstance(keyword.value, ast.Attribute)
        and isinstance(keyword.value.value, ast.Name)
        and keyword.value.value.id == "args" and keyword.value.attr == "target"
        for keyword in target_calls[0].keywords):
    raise SystemExit("migration runner does not pass the explicit target to its executor")
print(json.dumps({"inventory": inventory, "migration_062_sha256": digest,
                  "migrate_py_sha256": runner_sha,
                  "target_enforcement": "verified"}, sort_keys=True))
'''


class MigrationError(RuntimeError):
    """A safe, operator-facing refusal or failed migration operation."""


class DockerCall(Protocol):
    def __call__(self, *args: str, timeout: int = ...) -> str: ...


class ComposeCall(Protocol):
    def __call__(self, project: str, image: str | None, *args: str) -> str: ...


@dataclass(frozen=True)
class MigrationRequest:
    target: str
    digest: str
    revision: str
    expected_migration_062_sha256: str
    expected_migrate_py_sha256: str

    @property
    def image(self) -> str:
        return f"{API_IMAGE_REPOSITORY}@{self.digest}"


def parse_arguments(arguments: Sequence[str]) -> MigrationRequest:
    """Validate the complete, explicit migration request without side effects."""
    if not isinstance(arguments, (list, tuple)) or any(
            not isinstance(argument, str) for argument in arguments):
        raise MigrationError("Migration arguments must be a list of strings.")
    if "--target" not in arguments:
        raise MigrationError("Migration requires an explicit --target 062.")
    expected_options = {
        "--target",
        "--image",
        "--revision",
        "--expected-migration-062-sha256",
        "--expected-migrate-py-sha256",
    }
    if len(arguments) != len(expected_options) * 2:
        raise MigrationError("Migration requires target, image digest, revision, SQL SHA-256, and runner SHA-256.")

    values: dict[str, str] = {}
    for index in range(0, len(arguments), 2):
        option, value = arguments[index], arguments[index + 1]
        if option not in expected_options or option in values:
            raise MigrationError("Invalid migration arguments.")
        values[option] = value
    if set(values) != expected_options:
        raise MigrationError("Migration requires target, image digest, revision, SQL SHA-256, and runner SHA-256.")
    if values["--target"] != "062":
        raise MigrationError("Only explicit migration target 062 is permitted.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", values["--image"]):
        raise MigrationError("Image must be an immutable sha256 digest, not a tag or working-tree reference.")
    if not re.fullmatch(r"[0-9a-f]{40}", values["--revision"]):
        raise MigrationError("Revision must be a full 40-character lowercase commit hash.")
    if not re.fullmatch(r"[0-9a-f]{64}", values["--expected-migration-062-sha256"]):
        raise MigrationError("Expected migration receipt must be a full lowercase SHA-256 hash.")
    if not re.fullmatch(r"[0-9a-f]{64}", values["--expected-migrate-py-sha256"]):
        raise MigrationError("Expected migrate.py receipt must be a full lowercase SHA-256 hash.")
    return MigrationRequest(
        target="062",
        digest=values["--image"],
        revision=values["--revision"],
        expected_migration_062_sha256=values["--expected-migration-062-sha256"],
        expected_migrate_py_sha256=values["--expected-migrate-py-sha256"],
    )


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
        # Docker/psql stderr can contain environment-derived values. Keep the
        # failure visible without forwarding arbitrary command output.
        raise MigrationError(f"Docker operation failed with exit status {error.returncode}.") from None


def _compose(compose: ComposeCall, project: str, image: str | None, *args: str) -> str:
    try:
        return compose(project, image, *args)
    except subprocess.CalledProcessError as error:
        raise MigrationError(f"Compose operation failed with exit status {error.returncode}.") from None


def _verify_pulled_image(
    request: MigrationRequest, docker: DockerCall
) -> tuple[str, str, list[dict]]:
    image_data = _single_inspect_object(
        _docker(docker, "image", "inspect", request.image, timeout=30),
        "pulled candidate image",
    )
    repo_digests = image_data.get("RepoDigests")
    if (not isinstance(repo_digests, list)
            or any(not isinstance(value, str) for value in repo_digests)
            or request.image not in repo_digests):
        raise MigrationError("Pulled image digest does not match the requested API image.")
    config = image_data.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        raise MigrationError("Candidate image labels are missing or malformed.")
    if labels.get("org.opencontainers.image.source") != EXPECTED_SOURCE:
        raise MigrationError("Candidate image source label is not the Terento repository.")
    if labels.get("org.opencontainers.image.revision") != request.revision:
        raise MigrationError("Candidate image revision label does not match the requested revision.")
    label_sha = labels.get("io.terento.migration.062.sha256")
    if not isinstance(label_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", label_sha):
        raise MigrationError("Candidate image is missing a valid migration 062 SHA-256 label.")
    label_runner_sha = labels.get("io.terento.migrate.py.sha256")
    if not isinstance(label_runner_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", label_runner_sha):
        raise MigrationError("Candidate image is missing a valid migrate.py SHA-256 label.")

    audit_raw = _docker(
        docker,
        "run",
        "--rm",
        "--pull=never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit=64",
        "--memory=128m",
        "--entrypoint",
        "python",
        request.image,
        "-B",
        "-c",
        IMAGE_AUDIT_PYTHON,
        timeout=60,
    )
    audit = _json_object(audit_raw, "candidate migration inventory")
    inventory = audit.get("inventory")
    actual_sha = audit.get("migration_062_sha256")
    actual_runner_sha = audit.get("migrate_py_sha256")
    if (not isinstance(inventory, list)
            or not isinstance(actual_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", actual_sha)
            or not isinstance(actual_runner_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", actual_runner_sha)):
        raise MigrationError("Candidate image did not provide a valid migration inventory and SHA-256.")
    if audit.get("target_enforcement") != "verified":
        raise MigrationError("Candidate migration runner target enforcement could not be verified.")
    if inventory != [
        {"name": entry.get("name"), "version": entry.get("version")}
        for entry in inventory
        if isinstance(entry, dict)
    ]:
        raise MigrationError("Candidate image migration inventory is malformed.")
    if any(
        not isinstance(entry.get("name"), str)
        or not re.fullmatch(r"\d{3}_[A-Za-z0-9_.-]+\.sql", entry["name"])
        or not isinstance(entry.get("version"), str)
        or not re.fullmatch(r"\d{3}", entry["version"])
        for entry in inventory
    ):
        raise MigrationError("Candidate image contains a malformed migration filename.")
    versions = [entry.get("version") for entry in inventory]
    names = [entry.get("name") for entry in inventory]
    if versions != list(EXPECTED_MIGRATION_VERSIONS):
        later = [name for version, name in zip(versions, names) if version > "062"]
        if later:
            raise MigrationError(
                "Candidate image includes migration(s) after target 062: "
                + ", ".join(later)
                + ". This reviewed target-062 runner requires exactly migrations 001 through 062; no migration was run."
            )
        raise MigrationError("Candidate image must contain exactly canonical migrations 001 through 062, with no later migrations.")
    if label_sha != actual_sha:
        raise MigrationError("Candidate migration 062 SHA-256 does not match its image label.")
    if label_runner_sha != actual_runner_sha:
        raise MigrationError("Candidate migrate.py SHA-256 does not match its image label.")
    return actual_sha, actual_runner_sha, inventory


def _running_database_container(
    compose: ComposeCall, docker: DockerCall, image: str
) -> str:
    # Pass the already-verified image so Compose interpolation is deterministic;
    # `ps` remains a read-only query scoped to the existing database service.
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
    if (not isinstance(labels, dict)
            or not isinstance(state, dict)
            or labels.get("com.docker.compose.project") != COMPOSE_PROJECT
            or labels.get("com.docker.compose.service") != DB_SERVICE
            or state.get("Running") is not True):
        raise MigrationError("The existing catalog database service is not running with the expected identity.")
    container_id = data.get("Id")
    if (not isinstance(container_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", container_id)
            or not container_id.startswith(ids[0])):
        raise MigrationError("Could not validate the existing catalog database container identity.")
    return container_id


def _read_ledger(database_id: str, docker: DockerCall) -> list[str]:
    raw = _docker(
        docker,
        "exec",
        "--user",
        "postgres",
        database_id,
        "sh",
        "-c",
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"',
        "terento-migration-precheck",
        LEDGER_SQL,
        timeout=30,
    )
    try:
        ledger = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise MigrationError("Could not validate the read-only migration ledger precheck.") from None
    if not isinstance(ledger, list) or any(not isinstance(version, str) for version in ledger):
        raise MigrationError("Could not validate the read-only migration ledger precheck.")
    return ledger


def _classify_ledger(ledger: list[str]) -> str:
    if ledger == list(EXPECTED_MIGRATION_VERSIONS[:-1]):
        return "pending"
    if ledger == list(EXPECTED_MIGRATION_VERSIONS):
        return "already_applied"
    raise MigrationError("Database migration ledger is not exactly 001 through 061 or 001 through 062.")


def verify_deploy_schema(
    arguments: Sequence[str],
    *,
    docker: DockerCall,
    compose: ComposeCall,
    emit: Callable[[str], None] = print,
) -> dict:
    """Prove the API candidate has no pending schema change before DEPLOY.

    DEPLOY must never run the generic migrator. This currently supports only
    the reviewed 001-062 image/ledger pair; future migration versions require
    a separately reviewed extension to this gate.
    """
    request = parse_arguments(arguments)
    actual_sha, actual_runner_sha, inventory = _verify_pulled_image(request, docker)
    if actual_sha != request.expected_migration_062_sha256:
        raise MigrationError("Deployment candidate migration 062 hash does not match its image label.")
    if actual_runner_sha != request.expected_migrate_py_sha256:
        raise MigrationError("Deployment candidate migration runner hash does not match its image label.")
    emit(
        "DEPLOY_SCHEMA_CANDIDATE "
        f"image={request.image} revision={request.revision} "
        f"migration_062_sha256={actual_sha} migrate_py_sha256={actual_runner_sha} "
        "inventory=001-062"
    )
    database_id = _running_database_container(compose, docker, request.image)
    ledger_state = _classify_ledger(_read_ledger(database_id, docker))
    if ledger_state != "already_applied":
        raise MigrationError(
            "DEPLOY refused: the candidate schema is not fully applied; "
            "run a separately approved migration-only operation first."
        )
    emit("DEPLOY_SCHEMA_PASS applied=001-062")
    return {
        "image": request.image,
        "revision": request.revision,
        "migration_062_sha256": actual_sha,
        "migrate_py_sha256": actual_runner_sha,
        "migration_inventory": inventory,
        "ledger": "001-062",
    }


def run_migration(
    arguments: Sequence[str],
    *,
    docker: DockerCall,
    compose: ComposeCall,
    emit: Callable[[str], None] = print,
) -> dict:
    """Verify a pinned candidate and run only its 062 migration one-shot.

    The caller must hold the deployment helper's global exclusive operations
    lock before invoking this function. No lock is created here.
    """
    request = parse_arguments(arguments)

    # The only registry access is an immutable repository@digest pull.
    _docker(docker, "pull", request.image, timeout=600)
    actual_sha, actual_runner_sha, inventory = _verify_pulled_image(request, docker)

    # Print safe, validated artifact identity before any migration execution.
    emit(
        "MIGRATION_CANDIDATE "
        f"image={request.image} revision={request.revision} "
        f"migration_062_sha256={actual_sha} migrate_py_sha256={actual_runner_sha} "
        "target_enforcement=verified inventory=001-062"
    )
    if actual_sha != request.expected_migration_062_sha256:
        raise MigrationError("Actual migration 062 SHA-256 does not match the production candidate receipt.")
    if actual_runner_sha != request.expected_migrate_py_sha256:
        raise MigrationError("Actual migrate.py SHA-256 does not match the production candidate receipt.")
    emit("MIGRATION_RECEIPT_PASS expected_sha256=" + request.expected_migration_062_sha256)

    database_id = _running_database_container(compose, docker, request.image)
    ledger_state = _classify_ledger(_read_ledger(database_id, docker))
    if ledger_state == "already_applied":
        emit("ALREADY APPLIED 062; no migration container was run.")
        return {
            "operation": "migrate",
            "target": "062",
            "status": "already_applied",
            "image": request.image,
            "revision": request.revision,
            "migration_062_sha256": actual_sha,
            "migrate_py_sha256": actual_runner_sha,
            "migration_inventory": inventory,
        }

    # Recheck the DB container immediately before execution. Never use `up`,
    # `start`, or `restart`; Compose's `run --no-deps` must not start services.
    if _running_database_container(compose, docker, request.image) != database_id:
        raise MigrationError("Catalog database container changed after the ledger precheck; migration refused.")
    emit("LEDGER_PRECHECK_PASS applied=001-061 target=062")
    result_output = _compose(
        compose,
        "api",
        request.image,
        "--profile",
        "manual",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        MIGRATION_SERVICE,
        "--target",
        "062",
    )
    output_lines = [line.strip() for line in result_output.splitlines() if line.strip()]
    if output_lines == ["Applied migrations: none"]:
        # A legacy/non-cooperating operator may have applied 062 after our
        # precheck. Treat only the exact resulting ledger as an explicit
        # successful no-op; never misreport it as this command applying SQL.
        if _running_database_container(compose, docker, request.image) != database_id:
            raise MigrationError("Catalog database container changed during the migration attempt.")
        if _classify_ledger(_read_ledger(database_id, docker)) != "already_applied":
            raise MigrationError("Migration runner returned no-op but the exact 062 ledger was not confirmed.")
        emit("ALREADY APPLIED 062; no migration change was made by this invocation.")
        return {
            "operation": "migrate",
            "target": "062",
            "status": "already_applied",
            "image": request.image,
            "revision": request.revision,
            "migration_062_sha256": actual_sha,
            "migrate_py_sha256": actual_runner_sha,
            "migration_inventory": inventory,
        }
    if output_lines != ["Applied migrations: 062"]:
        raise MigrationError("Migration runner did not report exactly 'Applied migrations: 062'.")
    if _running_database_container(compose, docker, request.image) != database_id:
        raise MigrationError("Catalog database container changed before the migration postcondition check.")
    if _classify_ledger(_read_ledger(database_id, docker)) != "already_applied":
        raise MigrationError("Migration runner reported success but the exact 001-062 ledger was not confirmed.")
    emit("MIGRATION_POSTCONDITION_PASS applied=001-062")
    emit("Applied migrations: 062")
    emit("MIGRATION_PASS target=062 revision=" + request.revision)
    return {
        "operation": "migrate",
        "target": "062",
        "status": "applied",
        "image": request.image,
        "revision": request.revision,
        "migration_062_sha256": actual_sha,
        "migrate_py_sha256": actual_runner_sha,
        "migration_inventory": inventory,
    }

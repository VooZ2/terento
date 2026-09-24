#!/usr/bin/env python3
"""Install the committed Terento production helper pair on the VPS.

Owner procedure: run this from a clean, committed checkout as root. A plain
invocation performs a read-only preflight and prints only the commit and source
file hashes. Apply only with both ``--apply`` and
``--confirm-production-helper-update``. Apply records a durable root-only
rollback state before replacing either target, atomically replaces each file,
and attempts to restore the recorded state if a caught install step fails.
Before applying, the owner must ensure the installed helper and any deployment
are quiescent: an older helper may not share the operations lock used here.

This preparation/install utility replaces only the existing root-owned
``/usr/local/sbin/terento-deploy`` and its sibling
``terento-deploy-migration.py``. It does not alter accounts, SSH keys, sudoers,
Compose files, or secrets. It never invokes Docker, a service manager, or a
database operation. Parent directories must already exist.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager


REPOSITORY = Path(__file__).resolve().parents[2]
DEPLOY_SOURCE = "scripts/infra/terento-deploy.py"
MIGRATION_SOURCE = "scripts/infra/terento-deploy-migration.py"
DEPLOY_TARGET = Path("/usr/local/sbin/terento-deploy")
MIGRATION_TARGET = DEPLOY_TARGET.with_name("terento-deploy-migration.py")
OPERATIONS_LOCK = Path("/var/lib/terento/deployment/operations.lock")
BACKUP_ROOT = OPERATIONS_LOCK.parent
BACKUP_MANIFEST = "manifest.json"
EXPECTED_MODE = 0o755
BACKUP_MODE = 0o600
ROOT_UID = 0
ROOT_GID = 0
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
BACKUP_ID_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{40}\Z")


class InstallerError(RuntimeError):
    """A safe refusal or failed local installation step."""


def _git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    git_environment = {
        name: value for name, value in os.environ.items()
        if not name.startswith("GIT_")
    }
    git_environment.update({
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "false",
    })
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=REPOSITORY,
            env=git_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        raise InstallerError("Could not inspect the committed checkout.") from None
    if result.returncode != 0:
        raise InstallerError("Could not verify the committed checkout.")
    return result


def _committed_sources() -> dict[str, bytes]:
    status = _git("status", "--porcelain")
    if status.stdout:
        raise InstallerError("The checkout must be clean, including untracked files.")

    tracked = _git("ls-files", "--error-unmatch", "--", DEPLOY_SOURCE, MIGRATION_SOURCE)
    try:
        listed = tracked.stdout.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        raise InstallerError("Git returned an invalid tracked-path list.") from None
    if len(listed) != 2 or set(listed) != {DEPLOY_SOURCE, MIGRATION_SOURCE}:
        raise InstallerError("Both production helper inputs must be tracked.")

    revision_result = _git("rev-parse", "HEAD")
    try:
        revision = revision_result.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        raise InstallerError("Git returned an invalid commit identifier.") from None
    if not COMMIT_RE.fullmatch(revision):
        raise InstallerError("HEAD is not a full commit identifier.")

    sources: dict[str, bytes] = {}
    for relative_path in (DEPLOY_SOURCE, MIGRATION_SOURCE):
        result = _git("show", f"HEAD:{relative_path}")
        source_bytes = result.stdout
        try:
            ast.parse(source_bytes.decode("utf-8", errors="strict"), filename=relative_path)
        except (UnicodeDecodeError, SyntaxError, ValueError):
            raise InstallerError("A committed production helper is not valid Python.") from None
        sources[relative_path] = source_bytes

    try:
        final_revision = _git("rev-parse", "HEAD").stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        raise InstallerError("Git returned an invalid commit identifier.") from None
    if final_revision != revision or _git("status", "--porcelain").stdout:
        raise InstallerError("The checkout changed while committed helper inputs were being read.")
    sources["__revision__"] = revision.encode("ascii")
    return sources


def _path_components(path: Path) -> list[Path]:
    absolute = path if path.is_absolute() else Path.cwd() / path
    parts = absolute.parts
    current = Path(parts[0])
    result = [current]
    for part in parts[1:]:
        current = current / part
        result.append(current)
    return result


def _lstat(path: Path) -> os.stat_result:
    try:
        return os.lstat(path)
    except OSError:
        raise InstallerError("A required production path is missing or inaccessible.") from None


def _assert_no_symlink_components(path: Path, *, allow_missing_leaf: bool = False):
    components = _path_components(path)
    for index, component in enumerate(components):
        try:
            entry = os.lstat(component)
        except FileNotFoundError:
            if allow_missing_leaf and index == len(components) - 1:
                return None
            raise InstallerError("A required production path is missing or inaccessible.") from None
        except OSError:
            raise InstallerError("A required production path is missing or inaccessible.") from None
        if stat.S_ISLNK(entry.st_mode):
            raise InstallerError("Production paths must not contain symlinks.")
        if index < len(components) - 1 and not stat.S_ISDIR(entry.st_mode):
            raise InstallerError("A production path parent is not a directory.")
    return entry


def _validate_parent(path: Path) -> None:
    parent = path.parent
    _assert_no_symlink_components(parent)
    entry = _lstat(parent)
    if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != ROOT_UID
            or entry.st_mode & 0o022):
        raise InstallerError("Production helper parent must be a secure root-owned directory.")


def _validate_target(path: Path, *, allow_absent: bool = False):
    _validate_parent(path)
    entry = _assert_no_symlink_components(path, allow_missing_leaf=allow_absent)
    if entry is None:
        return None
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        raise InstallerError("An existing production helper must be a regular file.")
    if entry.st_uid != ROOT_UID or entry.st_gid != ROOT_GID:
        raise InstallerError("An existing production helper must be owned by root.")
    if stat.S_IMODE(entry.st_mode) != EXPECTED_MODE:
        raise InstallerError("An existing production helper must have mode 0755.")
    return entry


def _validate_destinations():
    migration = _validate_target(MIGRATION_TARGET, allow_absent=True)
    deploy = _validate_target(DEPLOY_TARGET)
    return {MIGRATION_TARGET: migration, DEPLOY_TARGET: deploy}


def _validate_backup_root() -> None:
    entry = _assert_no_symlink_components(BACKUP_ROOT)
    if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != ROOT_UID
            or entry.st_gid != ROOT_GID or stat.S_IMODE(entry.st_mode) != 0o700):
        raise InstallerError("Rollback state directory must be root:root mode 0700.")


def _target_bytes(path: Path, expected_stat: os.stat_result | None = None) -> tuple[bytes, os.stat_result] | None:
    """Read a regular target without following a final symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    except OSError:
        raise InstallerError("Could not read a production helper safely.") from None
    try:
        entry = os.fstat(descriptor)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != ROOT_UID
                or entry.st_gid != ROOT_GID or stat.S_IMODE(entry.st_mode) != EXPECTED_MODE):
            raise InstallerError("An existing production helper changed to an unsafe file.")
        if expected_stat is not None and (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns) != (
                expected_stat.st_dev, expected_stat.st_ino, expected_stat.st_size, expected_stat.st_mtime_ns):
            raise InstallerError("A production helper changed during installer preflight.")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise InstallerError("A production helper changed while it was being backed up.")
        return b"".join(chunks), entry
    finally:
        os.close(descriptor)


def _write_private_file(path: Path, contents: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, BACKUP_MODE)
        try:
            os.fchown(descriptor, ROOT_UID, ROOT_GID)
            view = memoryview(contents)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fchmod(descriptor, BACKUP_MODE)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise InstallerError("Could not create root-only rollback state.") from None


def _create_rollback_record(sources: dict[str, bytes], old_targets: dict[Path, os.stat_result | None]) -> str:
    _validate_backup_root()
    revision = sources["__revision__"].decode("ascii")
    backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + revision
    backup_directory = BACKUP_ROOT / backup_id
    try:
        os.mkdir(backup_directory, 0o700)
        os.chown(backup_directory, ROOT_UID, ROOT_GID)
        os.chmod(backup_directory, 0o700)
    except OSError:
        raise InstallerError("Could not create a unique root-only rollback directory.") from None

    records: dict[str, dict[str, object]] = {}
    source_by_target = {DEPLOY_TARGET: DEPLOY_SOURCE, MIGRATION_TARGET: MIGRATION_SOURCE}
    backup_name_by_target = {DEPLOY_TARGET: "terento-deploy.py", MIGRATION_TARGET: "terento-deploy-migration.py"}
    for target in (DEPLOY_TARGET, MIGRATION_TARGET):
        expected_stat = old_targets[target]
        original = _target_bytes(target, expected_stat)
        if original is None:
            if expected_stat is not None:
                raise InstallerError("A production helper disappeared during installer preflight.")
            records[str(target)] = {
                "state": "ABSENT",
                "installed_sha256": hashlib.sha256(sources[source_by_target[target]]).hexdigest(),
            }
            continue
        contents, entry = original
        backup_name = backup_name_by_target[target]
        _write_private_file(backup_directory / backup_name, contents)
        records[str(target)] = {
            "state": "PRESENT",
            "backup_file": backup_name,
            "sha256": hashlib.sha256(contents).hexdigest(),
            "size_bytes": len(contents),
            "uid": entry.st_uid,
            "gid": entry.st_gid,
            "mode": stat.S_IMODE(entry.st_mode),
            "installed_sha256": hashlib.sha256(sources[source_by_target[target]]).hexdigest(),
        }
    manifest = {
        "format": 1,
        "rollback_id": backup_id,
        "source_revision": revision,
        "targets": records,
    }
    encoded_manifest = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_private_file(backup_directory / BACKUP_MANIFEST, encoded_manifest)
    _sync_directory(backup_directory)
    _sync_directory(BACKUP_ROOT)
    return backup_id


def _read_rollback_record(backup_id: str) -> tuple[Path, dict[str, object]]:
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise InstallerError("Rollback id has an invalid format.")
    _validate_backup_root()
    backup_directory = BACKUP_ROOT / backup_id
    entry = _assert_no_symlink_components(backup_directory)
    if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != ROOT_UID
            or entry.st_gid != ROOT_GID or stat.S_IMODE(entry.st_mode) != 0o700):
        raise InstallerError("Rollback record directory must be root:root mode 0700.")
    manifest_path = backup_directory / BACKUP_MANIFEST
    manifest_stat = _assert_no_symlink_components(manifest_path)
    if (not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_uid != ROOT_UID
            or manifest_stat.st_gid != ROOT_GID or stat.S_IMODE(manifest_stat.st_mode) != BACKUP_MODE):
        raise InstallerError("Rollback manifest must be root:root mode 0600.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise InstallerError("Rollback manifest is unreadable or invalid.") from None
    expected_targets = {str(DEPLOY_TARGET), str(MIGRATION_TARGET)}
    if (not isinstance(manifest, dict) or manifest.get("format") != 1
            or manifest.get("rollback_id") != backup_id
            or not isinstance(manifest.get("source_revision"), str)
            or not COMMIT_RE.fullmatch(manifest["source_revision"])
            or not isinstance(manifest.get("targets"), dict)
            or set(manifest["targets"]) != expected_targets):
        raise InstallerError("Rollback manifest does not match this helper pair.")
    return backup_directory, manifest


def _read_backup_file(backup_directory: Path, record: dict[str, object]) -> bytes:
    name = record.get("backup_file")
    if name not in {"terento-deploy.py", "terento-deploy-migration.py"}:
        raise InstallerError("Rollback manifest contains an invalid backup filename.")
    path = backup_directory / str(name)
    entry = _assert_no_symlink_components(path)
    if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != ROOT_UID
            or entry.st_gid != ROOT_GID or stat.S_IMODE(entry.st_mode) != BACKUP_MODE):
        raise InstallerError("Rollback helper copy must be root:root mode 0600.")
    try:
        contents = path.read_bytes()
    except OSError:
        raise InstallerError("Rollback helper copy could not be read.") from None
    if (len(contents) != record.get("size_bytes")
            or hashlib.sha256(contents).hexdigest() != record.get("sha256")):
        raise InstallerError("Rollback helper copy failed its size or SHA-256 check.")
    return contents


def _rollback(backup_id: str) -> None:
    backup_directory, manifest = _read_rollback_record(backup_id)
    records = manifest["targets"]
    restore: dict[Path, bytes | None] = {}
    for target in (DEPLOY_TARGET, MIGRATION_TARGET):
        record = records[str(target)]
        if not isinstance(record, dict):
            raise InstallerError("Rollback manifest target record is invalid.")
        state = record.get("state")
        installed_sha = record.get("installed_sha256")
        if not isinstance(installed_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", installed_sha):
            raise InstallerError("Rollback manifest has an invalid installed helper hash.")
        current_stat = _validate_target(target, allow_absent=(target == MIGRATION_TARGET))
        current = _target_bytes(target, current_stat) if current_stat is not None else None
        current_sha = hashlib.sha256(current[0]).hexdigest() if current is not None else None
        if state == "ABSENT":
            if target != MIGRATION_TARGET or current_sha not in (None, installed_sha):
                raise InstallerError("Absent-before-install target changed unexpectedly; rollback refused.")
            restore[target] = None
        elif state == "PRESENT":
            if (record.get("uid"), record.get("gid"), record.get("mode")) != (ROOT_UID, ROOT_GID, EXPECTED_MODE):
                raise InstallerError("Rollback manifest contains unsafe original ownership or mode.")
            original = _read_backup_file(backup_directory, record)
            original_sha = hashlib.sha256(original).hexdigest()
            if current_sha not in (original_sha, installed_sha):
                raise InstallerError("Installed helper changed since backup; rollback refused.")
            restore[target] = original
        else:
            raise InstallerError("Rollback manifest target state is invalid.")

    # Installation publishes the module before the executable helper; rollback
    # reverses that order so the existing entry helper is restored before its
    # module is restored or a first-install module is removed.
    for target in (DEPLOY_TARGET, MIGRATION_TARGET):
        contents = restore[target]
        if contents is None:
            if _validate_target(target, allow_absent=True) is not None:
                os.unlink(target)
                _sync_directory(target.parent)
        else:
            current = _target_bytes(target, _validate_target(target, allow_absent=(target == MIGRATION_TARGET)))
            if current is None:
                raise InstallerError("A helper disappeared during rollback; no further changes were made.")
            if hashlib.sha256(contents).hexdigest() == hashlib.sha256(current[0]).hexdigest():
                continue
            temporary = _stage_bytes(target, contents)
            try:
                _validate_target(target, allow_absent=(target == MIGRATION_TARGET))
                os.replace(temporary, target)
                _sync_directory(target.parent)
            except OSError:
                raise InstallerError("Could not atomically restore a production helper.") from None
            finally:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass


def _validate_lock_parent() -> None:
    _validate_parent(OPERATIONS_LOCK)


@contextmanager
def _operations_lock():
    _validate_lock_parent()
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(OPERATIONS_LOCK, flags, 0o600)
    except OSError:
        raise InstallerError("Could not open the production operations lock safely.") from None
    try:
        lock_stat = os.fstat(descriptor)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != ROOT_UID
                or lock_stat.st_mode & 0o022):
            raise InstallerError("The production operations lock has unsafe ownership or mode.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise InstallerError("Another production operation currently holds the lock.") from None
        yield
    finally:
        os.close(descriptor)


def _stage_bytes(target: Path, contents: bytes) -> Path:
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
    except OSError:
        raise InstallerError("Could not stage a production helper in its target directory.") from None

    temporary = Path(temporary_name)
    try:
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        view = memoryview(contents)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fchmod(descriptor, EXPECTED_MODE)
        os.fsync(descriptor)
    except OSError:
        os.close(descriptor)
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise InstallerError("Could not safely prepare a production helper file.") from None
    else:
        os.close(descriptor)
    return temporary


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(directory, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise InstallerError("Could not sync a production helper directory.") from None


def _install(sources: dict[str, bytes]) -> None:
    # Validate again under the lock, then stage both files before changing either.
    old_targets = _validate_destinations()
    staged: list[tuple[Path, Path]] = []
    backup_id: str | None = None
    try:
        staged.append((MIGRATION_TARGET, _stage_bytes(MIGRATION_TARGET, sources[MIGRATION_SOURCE])))
        staged.append((DEPLOY_TARGET, _stage_bytes(DEPLOY_TARGET, sources[DEPLOY_SOURCE])))
        backup_id = _create_rollback_record(sources, old_targets)
        print(f"rollback-state {backup_id}", flush=True)
        # The module is replaced first; the entry helper becomes visible last.
        for target, temporary in staged:
            _validate_target(target, allow_absent=(target == MIGRATION_TARGET))
            try:
                os.replace(temporary, target)
            except OSError:
                raise InstallerError("Could not atomically install a production helper.") from None
            _sync_directory(target.parent)
    except InstallerError:
        if backup_id is None:
            raise
        try:
            _rollback(backup_id)
        except InstallerError:
            raise InstallerError(
                f"Install failed; automatic rollback did not complete. "
                f"Rollback state {backup_id} is retained for explicit recovery."
            ) from None
        raise InstallerError(
            f"Install failed; the previous helper state was restored. "
            f"Rollback state {backup_id} is retained."
        ) from None
    finally:
        for _, temporary in staged:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _receipt(sources: dict[str, bytes]) -> None:
    revision = sources["__revision__"].decode("ascii")
    print(f"commit {revision}")
    print(f"file {Path(DEPLOY_SOURCE).name} sha256:{hashlib.sha256(sources[DEPLOY_SOURCE]).hexdigest()}")
    print(f"file {Path(MIGRATION_SOURCE).name} sha256:{hashlib.sha256(sources[MIGRATION_SOURCE]).hexdigest()}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="install the committed helper pair with recorded rollback state")
    parser.add_argument("--rollback", metavar="ROLLBACK_ID", help="restore one recorded pre-install helper state")
    parser.add_argument(
        "--confirm-production-helper-update",
        action="store_true",
        help="confirm the production helper update when used with --apply",
    )
    parser.add_argument(
        "--confirm-production-helper-rollback",
        action="store_true",
        help="confirm the production helper rollback when used with --rollback",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    if args.apply and args.rollback:
        print("error: --apply and --rollback are mutually exclusive", file=sys.stderr)
        return 2
    if args.confirm_production_helper_update and not args.apply:
        print("error: --confirm-production-helper-update requires --apply", file=sys.stderr)
        return 2
    if args.confirm_production_helper_rollback and not args.rollback:
        print("error: --confirm-production-helper-rollback requires --rollback", file=sys.stderr)
        return 2
    if args.apply and not args.confirm_production_helper_update:
        print("error: apply requires --confirm-production-helper-update", file=sys.stderr)
        return 2
    if args.rollback and not args.confirm_production_helper_rollback:
        print("error: rollback requires --confirm-production-helper-rollback", file=sys.stderr)
        return 2
    if (args.apply or args.rollback) and os.geteuid() != ROOT_UID:
        print("error: apply and rollback require root", file=sys.stderr)
        return 2

    try:
        _validate_destinations()
        if args.apply or args.rollback:
            _validate_lock_parent()
            _validate_backup_root()
        sources = _committed_sources()
        if args.apply:
            with _operations_lock():
                _install(sources)
        elif args.rollback:
            with _operations_lock():
                _rollback(args.rollback)
            print(f"rollback-restored {args.rollback}")
        _receipt(sources)
        return 0
    except InstallerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

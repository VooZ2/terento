#!/usr/bin/env python3
"""Install the committed Terento production helper pair on the VPS.

Owner procedure: run this from a clean, committed checkout as root. A plain
invocation performs a read-only preflight and prints only the commit and source
file hashes. Apply only with both ``--apply`` and
``--confirm-production-helper-update``. Before applying, the owner must ensure
the installed helper and any deployment are quiescent: an older helper may not
share the operations lock used here.

This preparation/install utility replaces only the existing root-owned
``/usr/local/sbin/terento-deploy`` and its sibling
``terento-deploy-migration.py``. It does not alter accounts, SSH keys, sudoers,
Compose files, or secrets. It never invokes Docker, a service manager, or a
database operation. Parent directories must already exist.
"""

from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
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
EXPECTED_MODE = 0o755
ROOT_UID = 0
ROOT_GID = 0
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


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


def _assert_no_symlink_components(path: Path) -> None:
    components = _path_components(path)
    for index, component in enumerate(components):
        entry = _lstat(component)
        if stat.S_ISLNK(entry.st_mode):
            raise InstallerError("Production paths must not contain symlinks.")
        if index < len(components) - 1 and not stat.S_ISDIR(entry.st_mode):
            raise InstallerError("A production path parent is not a directory.")


def _validate_parent(path: Path) -> None:
    parent = path.parent
    _assert_no_symlink_components(parent)
    entry = _lstat(parent)
    if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != ROOT_UID
            or entry.st_mode & 0o022):
        raise InstallerError("Production helper parent must be a secure root-owned directory.")


def _validate_target(path: Path) -> None:
    _validate_parent(path)
    _assert_no_symlink_components(path)
    entry = _lstat(path)
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        raise InstallerError("An existing production helper must be a regular file.")
    if entry.st_uid != ROOT_UID:
        raise InstallerError("An existing production helper must be owned by root.")
    if stat.S_IMODE(entry.st_mode) != EXPECTED_MODE:
        raise InstallerError("An existing production helper must have mode 0755.")


def _validate_destinations() -> None:
    for target in (MIGRATION_TARGET, DEPLOY_TARGET):
        _validate_target(target)


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
    _validate_destinations()
    staged: list[tuple[Path, Path]] = []
    try:
        staged.append((MIGRATION_TARGET, _stage_bytes(MIGRATION_TARGET, sources[MIGRATION_SOURCE])))
        staged.append((DEPLOY_TARGET, _stage_bytes(DEPLOY_TARGET, sources[DEPLOY_SOURCE])))
        # The module is replaced first; the entry helper becomes visible last.
        for target, temporary in staged:
            _validate_target(target)
            try:
                os.replace(temporary, target)
            except OSError:
                raise InstallerError("Could not atomically install a production helper.") from None
            _sync_directory(target.parent)
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
    parser.add_argument("--apply", action="store_true", help="atomically install the committed helper pair")
    parser.add_argument(
        "--confirm-production-helper-update",
        action="store_true",
        help="confirm the production helper update when used with --apply",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    if args.confirm_production_helper_update and not args.apply:
        print("error: --confirm-production-helper-update requires --apply", file=sys.stderr)
        return 2
    if args.apply and not args.confirm_production_helper_update:
        print("error: apply requires --confirm-production-helper-update", file=sys.stderr)
        return 2
    if args.apply and os.geteuid() != ROOT_UID:
        print("error: apply requires root", file=sys.stderr)
        return 2

    try:
        _validate_destinations()
        if args.apply:
            _validate_lock_parent()
        sources = _committed_sources()
        if args.apply:
            with _operations_lock():
                _install(sources)
        _receipt(sources)
        return 0
    except InstallerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

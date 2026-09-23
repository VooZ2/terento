#!/usr/bin/env python3
"""Scoped tests for the owner-run production helper installer."""

from __future__ import annotations

import hashlib
import importlib.util
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("install-terento-production-ops.py")
SPEC = importlib.util.spec_from_file_location("install_terento_production_ops", SCRIPT)
INSTALLER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = INSTALLER
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    revision = "a" * 40
    deploy_source = b"#!/usr/bin/env python3\nVALUE = 'committed deploy'\n"
    migration_source = b"#!/usr/bin/env python3\nVALUE = 'committed migration'\n"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name).resolve()
        self.sbin = root / "usr" / "local" / "sbin"
        self.sbin.mkdir(parents=True)
        os.chmod(self.sbin, 0o755)
        self.state = root / "var" / "lib" / "terento" / "deployment"
        self.state.mkdir(parents=True)
        os.chmod(self.state, 0o700)
        self.deploy_target = self.sbin / "terento-deploy"
        self.migration_target = self.sbin / "terento-deploy-migration.py"
        self.lock_path = self.state / "operations.lock"
        self.deploy_target.write_bytes(b"old deployment helper\n")
        self.migration_target.write_bytes(b"old migration module\n")
        os.chmod(self.deploy_target, 0o755)
        os.chmod(self.migration_target, 0o755)

        self.git_calls: list[list[str]] = []
        self.git_status = b""
        self.tracked_output = (
            INSTALLER.DEPLOY_SOURCE + "\n" + INSTALLER.MIGRATION_SOURCE + "\n"
        ).encode()
        self.git_fail: set[tuple[str, ...]] = set()

        def fake_run(command, **kwargs):
            command = list(command)
            self.git_calls.append(command)
            self.assertEqual(command[0], "git")
            self.assertEqual(kwargs["cwd"], INSTALLER.REPOSITORY)
            self.assertEqual(kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(kwargs["env"]["GIT_CONFIG_VALUE_0"], "false")
            self.assertNotIn("GIT_DIR", kwargs["env"])
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            args = tuple(command[1:])
            if args in self.git_fail:
                return subprocess.CompletedProcess(command, 1, b"", b"ignored")
            if args == ("status", "--porcelain"):
                output = self.git_status
            elif args == (
                "ls-files", "--error-unmatch", "--", INSTALLER.DEPLOY_SOURCE,
                INSTALLER.MIGRATION_SOURCE,
            ):
                output = self.tracked_output
            elif args == ("rev-parse", "HEAD"):
                output = (self.revision + "\n").encode()
            elif args == ("show", f"HEAD:{INSTALLER.DEPLOY_SOURCE}"):
                output = self.deploy_source
            elif args == ("show", f"HEAD:{INSTALLER.MIGRATION_SOURCE}"):
                output = self.migration_source
            else:
                self.fail(f"unexpected command: {command!r}")
            return subprocess.CompletedProcess(command, 0, output, b"")

        self.fake_run = fake_run
        self.patches = [
            mock.patch.object(INSTALLER, "DEPLOY_TARGET", self.deploy_target),
            mock.patch.object(INSTALLER, "MIGRATION_TARGET", self.migration_target),
            mock.patch.object(INSTALLER, "OPERATIONS_LOCK", self.lock_path),
            mock.patch.object(INSTALLER.subprocess, "run", side_effect=fake_run),
            mock.patch.object(INSTALLER.os, "geteuid", return_value=0),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _lstat_with_root_owned_targets(self, *, uid_overrides=None, mode_overrides=None):
        uid_overrides = uid_overrides or {}
        mode_overrides = mode_overrides or {}
        original = INSTALLER.os.lstat

        def spoofed(path):
            entry = original(path)
            key = Path(path)
            uid = uid_overrides.get(key, entry.st_uid)
            mode = mode_overrides.get(key, entry.st_mode)
            if uid == entry.st_uid and mode == entry.st_mode:
                return entry
            class Entry:
                st_mode = mode
                st_uid = uid
            return Entry()

        return mock.patch.object(INSTALLER.os, "lstat", side_effect=spoofed)

    def _successful_metadata_patches(self):
        lstat_patch = self._lstat_with_root_owned_targets(
            uid_overrides={
                self.sbin: 0,
                self.state: 0,
                self.deploy_target: 0,
                self.migration_target: 0,
            }
        )
        fstat_original = INSTALLER.os.fstat

        def root_fstat(fd):
            entry = fstat_original(fd)
            return type("RootStat", (), {
                "st_mode": entry.st_mode,
                "st_uid": 0,
            })()

        return [lstat_patch, mock.patch.object(INSTALLER.os, "fstat", side_effect=root_fstat)]

    def _invoke(self, arguments):
        with mock.patch.object(INSTALLER, "REPOSITORY", Path(self.temporary_directory.name)):
            return INSTALLER.main(arguments)

    def test_default_is_read_only_preflight_and_prints_only_hash_receipt(self):
        before = {
            self.deploy_target: self.deploy_target.read_bytes(),
            self.migration_target: self.migration_target.read_bytes(),
        }
        with self._successful_metadata_patches()[0], mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as stdout:
            result = self._invoke([])
        self.assertEqual(result, 0)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(self.lock_path.exists())
        self.assertEqual(len(list(self.sbin.iterdir())), 2)
        self.assertEqual(stdout.getvalue().splitlines(), [
            f"commit {self.revision}",
            f"file terento-deploy.py sha256:{hashlib.sha256(self.deploy_source).hexdigest()}",
            f"file terento-deploy-migration.py sha256:{hashlib.sha256(self.migration_source).hexdigest()}",
        ])
        self.assertEqual(self.git_calls[-2:], [
            ["git", "rev-parse", "HEAD"],
            ["git", "status", "--porcelain"],
        ])
        self.assertIn(["git", "show", f"HEAD:{INSTALLER.DEPLOY_SOURCE}"], self.git_calls)
        self.assertIn(["git", "show", f"HEAD:{INSTALLER.MIGRATION_SOURCE}"], self.git_calls)

    def test_git_environment_cannot_redirect_source_checkout(self):
        with self._successful_metadata_patches()[0], mock.patch.dict(
            os.environ, {"GIT_DIR": "/unrelated/repository/.git"}
        ), mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
            self.assertEqual(self._invoke([]), 0)
        self.assertTrue(self.git_calls)

    def test_confirmation_is_required_before_apply(self):
        for arguments in (["--apply"], ["--confirm-production-helper-update"]):
            with self.subTest(arguments=arguments), mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
                self.assertEqual(self._invoke(list(arguments)), 2)
        self.assertEqual(self.deploy_target.read_bytes(), b"old deployment helper\n")
        self.assertEqual(self.migration_target.read_bytes(), b"old migration module\n")
        self.assertFalse(self.lock_path.exists())
        self.assertEqual(self.git_calls, [])

    def test_apply_requires_root(self):
        with mock.patch.object(INSTALLER.os, "geteuid", return_value=501), mock.patch(
            "sys.stderr", new_callable=__import__("io").StringIO
        ) as stderr:
            self.assertEqual(self._invoke(["--apply", "--confirm-production-helper-update"]), 2)
        self.assertIn("requires root", stderr.getvalue())
        self.assertFalse(self.lock_path.exists())

    def test_dirty_and_untracked_checkout_are_refused(self):
        for status in (b" M tracked.py\n", b"?? untracked.py\n"):
            with self.subTest(status=status), self._successful_metadata_patches()[0], mock.patch(
                "sys.stderr", new_callable=__import__("io").StringIO
            ):
                self.git_status = status
                self.assertEqual(self._invoke([]), 2)
                self.assertEqual(self.git_calls, [["git", "status", "--porcelain"]])
                self.git_calls.clear()
        self.assertEqual(self.deploy_target.read_bytes(), b"old deployment helper\n")

    def test_missing_tracked_inputs_are_refused(self):
        self.tracked_output = (INSTALLER.DEPLOY_SOURCE + "\n").encode()
        with self._successful_metadata_patches()[0], mock.patch(
            "sys.stderr", new_callable=__import__("io").StringIO
        ):
            self.assertEqual(self._invoke([]), 2)
        self.assertEqual(self.git_calls[-1][1:3], ["ls-files", "--error-unmatch"])
        self.assertFalse(self.lock_path.exists())

    def test_git_tracking_command_failure_is_refused(self):
        self.git_fail.add((
            "ls-files", "--error-unmatch", "--", INSTALLER.DEPLOY_SOURCE,
            INSTALLER.MIGRATION_SOURCE,
        ))
        with self._successful_metadata_patches()[0], mock.patch(
            "sys.stderr", new_callable=__import__("io").StringIO
        ):
            self.assertEqual(self._invoke([]), 2)
        self.assertFalse(self.lock_path.exists())

    def test_symlink_non_root_and_mode_mismatch_targets_are_rejected(self):
        with self.subTest(case="symlink"):
            self.migration_target.unlink()
            self.migration_target.symlink_to(self.deploy_target)
            with mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
                self.assertEqual(self._invoke([]), 2)
            self.migration_target.unlink()
            self.migration_target.write_bytes(b"old migration module\n")
            os.chmod(self.migration_target, 0o755)

        with self.subTest(case="non-root"):
            with self._lstat_with_root_owned_targets(
                uid_overrides={self.sbin: 0, self.state: 0, self.deploy_target: 501, self.migration_target: 0}
            ), mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
                self.assertEqual(self._invoke([]), 2)

        with self.subTest(case="mode mismatch"):
            original = INSTALLER.os.lstat(self.deploy_target)
            wrong_mode = (original.st_mode & ~0o777) | 0o644
            with self._lstat_with_root_owned_targets(
                uid_overrides={self.sbin: 0, self.state: 0, self.deploy_target: 0, self.migration_target: 0},
                mode_overrides={self.deploy_target: wrong_mode},
            ), mock.patch("sys.stderr", new_callable=__import__("io").StringIO):
                self.assertEqual(self._invoke([]), 2)
        self.assertFalse(self.lock_path.exists())

    def test_missing_target_and_parent_are_rejected_without_creation(self):
        self.migration_target.unlink()
        with self._successful_metadata_patches()[0], mock.patch(
            "sys.stderr", new_callable=__import__("io").StringIO
        ):
            self.assertEqual(self._invoke([]), 2)
        self.assertTrue(self.migration_target.parent.is_dir())
        self.assertFalse(self.migration_target.exists())

        missing_parent = self.sbin / "not-created"
        missing_target = missing_parent / "terento-deploy-migration.py"
        with mock.patch.object(INSTALLER, "MIGRATION_TARGET", missing_target), mock.patch(
            "sys.stderr", new_callable=__import__("io").StringIO
        ):
            self.assertEqual(self._invoke([]), 2)
        self.assertFalse(missing_parent.exists())

    def test_apply_uses_nonblocking_operations_lock(self):
        root_patches = self._successful_metadata_patches()
        for patcher in root_patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        with self.lock_path.open("a") as held_lock:
            fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch("sys.stderr", new_callable=__import__("io").StringIO) as stderr:
                self.assertEqual(
                    self._invoke(["--apply", "--confirm-production-helper-update"]), 2
                )
            self.assertIn("currently holds the lock", stderr.getvalue())
        self.assertEqual(self.deploy_target.read_bytes(), b"old deployment helper\n")
        self.assertEqual(self.migration_target.read_bytes(), b"old migration module\n")
        self.assertEqual(len(list(self.sbin.iterdir())), 2)

    def test_apply_stages_and_atomically_replaces_module_then_helper(self):
        root_patches = self._successful_metadata_patches()
        for patcher in root_patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        replacements = []
        real_replace = os.replace

        def recorded_replace(source, destination):
            source_path, destination_path = Path(source), Path(destination)
            self.assertEqual(source_path.parent, destination_path.parent)
            self.assertTrue(source_path.name.startswith(f".{destination_path.name}."))
            self.assertTrue(source_path.name.endswith(".tmp"))
            replacements.append(destination_path.name)
            real_replace(source, destination)

        fchown_calls = []
        real_fchmod = os.fchmod
        fchmod_modes = []
        fsync_calls = []
        real_fsync = os.fsync

        def record_fchown(fd, uid, gid):
            fchown_calls.append((uid, gid))

        def record_fchmod(fd, mode):
            fchmod_modes.append(mode)
            real_fchmod(fd, mode)

        def record_fsync(fd):
            fsync_calls.append(fd)
            real_fsync(fd)

        with mock.patch.object(INSTALLER.os, "replace", side_effect=recorded_replace), mock.patch.object(
            INSTALLER.os, "fchown", side_effect=record_fchown
        ), mock.patch.object(INSTALLER.os, "fchmod", side_effect=record_fchmod), mock.patch.object(
            INSTALLER.os, "fsync", side_effect=record_fsync
        ), mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as stdout:
            result = self._invoke(["--apply", "--confirm-production-helper-update"])

        self.assertEqual(result, 0)
        self.assertEqual(replacements, ["terento-deploy-migration.py", "terento-deploy"])
        self.assertEqual(self.migration_target.read_bytes(), self.migration_source)
        self.assertEqual(self.deploy_target.read_bytes(), self.deploy_source)
        self.assertEqual(stat.S_IMODE(self.migration_target.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.deploy_target.stat().st_mode), 0o755)
        self.assertEqual(fchown_calls, [(0, 0), (0, 0)])
        self.assertEqual(fchmod_modes, [0o755, 0o755])
        self.assertGreaterEqual(len(fsync_calls), 4)
        self.assertEqual(len(list(self.sbin.iterdir())), 2)
        self.assertIn(self.revision, stdout.getvalue())
        self.assertIn(hashlib.sha256(self.deploy_source).hexdigest(), stdout.getvalue())
        self.assertIn(hashlib.sha256(self.migration_source).hexdigest(), stdout.getvalue())
        self.assertTrue(all(call[0] == "git" for call in self.git_calls))
        self.assertFalse(any(
            word in " ".join(call).lower()
            for call in self.git_calls
            for word in ("docker", "systemctl", "service", "compose")
        ))


if __name__ == "__main__":
    unittest.main()

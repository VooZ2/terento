"""Focused contracts for the single immutable deploy path."""

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("terento_deploy", ROOT / "terento-deploy.py")
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)

DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40
IMAGE = deploy.PROJECTS["api"]["image"] + "@" + DIGEST


class DeployPathTests(unittest.TestCase):
    def _paths(self, root):
        base = Path(root) / "config"
        state = Path(root) / "state"
        (base / "api").mkdir(parents=True)
        (base / "api" / "enabled").touch()
        return base, state

    def test_dispatch_has_no_remote_migration_operation(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.dispatch(["api", "migrate"])
        with self.assertRaises(deploy.DeploymentError):
            deploy.dispatch(["migrate"])

    def test_api_migration_runs_inside_deploy_before_service_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            base, state = self._paths(root)
            events = []
            locked = [False]

            @contextmanager
            def lock():
                locked[0] = True
                events.append(("lock", "enter"))
                try:
                    yield
                finally:
                    events.append(("lock", "exit"))
                    locked[0] = False

            def compose(project, image, *args):
                if "up" in args:
                    self.assertTrue(locked[0])
                events.append(("compose", project, image, args))
                return ""

            def docker(*args, **kwargs):
                events.append(("docker", args))
                if args[:2] == ("image", "inspect"):
                    return json.dumps([{"Config": {"Labels": {
                        "org.opencontainers.image.source": deploy.STATUS_SQL and "https://github.com/VooZ2/terento",
                        "org.opencontainers.image.revision": REVISION,
                    }}}])
                return ""

            with patch.object(deploy, "BASE", base), patch.object(deploy, "STATE", state), \
                    patch.object(deploy, "operations_lock", side_effect=lock), \
                    patch.object(deploy, "compose", side_effect=compose), \
                    patch.object(deploy, "docker", side_effect=docker), \
                    patch.object(deploy, "migrate_candidate", side_effect=lambda *args: (self.assertTrue(locked[0]), events.append(("migrate", *args)))), \
                    patch.object(deploy, "healthy_ids", return_value={"api": {}, "scheduler": {}}), \
                    patch.object(deploy, "register"), patch.object(deploy, "run"):
                deploy.deploy("api", DIGEST, REVISION)

            migrate_index = next(index for index, event in enumerate(events) if event[0] == "migrate")
            up_index = next(index for index, event in enumerate(events) if event[0] == "compose" and "up" in event[3])
            self.assertLess(migrate_index, up_index)
            self.assertEqual(events[migrate_index][1:], (IMAGE, DIGEST, REVISION))
            self.assertEqual(events[up_index][2], IMAGE)
            self.assertEqual(events[0], ("lock", "enter"))
            self.assertEqual(events[-1], ("lock", "exit"))

    def test_migration_failure_leaves_services_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            base, state = self._paths(root)
            compose_calls = []

            def compose(project, image, *args):
                compose_calls.append(args)
                return ""

            image_inspect = json.dumps([{"Config": {"Labels": {
                "org.opencontainers.image.source": "https://github.com/VooZ2/terento",
                "org.opencontainers.image.revision": REVISION,
            }}}])
            with patch.object(deploy, "BASE", base), patch.object(deploy, "STATE", state), \
                    patch.object(deploy, "compose", side_effect=compose), \
                    patch.object(deploy, "docker", side_effect=lambda *a, **k: image_inspect), \
                    patch.object(deploy, "migrate_candidate", side_effect=deploy.DeploymentError("migration failed")), \
                    patch.object(deploy, "healthy_ids") as healthy, patch.object(deploy, "register") as register:
                with self.assertRaisesRegex(deploy.DeploymentError, "migration failed"):
                    deploy.deploy("api", DIGEST, REVISION)
            self.assertEqual(compose_calls, [("config", "--quiet")])
            healthy.assert_not_called()
            register.assert_not_called()
            self.assertFalse((state / "api.json").exists())

    def test_prune_keeps_current_and_rollback_images_and_ignores_refusals(self):
        previous = deploy.PROJECTS["api"]["image"] + "@sha256:" + "c" * 64
        removed = []

        def docker(*args, **kwargs):
            if args[:3] == ("image", "inspect", "--format"):
                return {IMAGE: "sha256:current\n", previous: "sha256:previous\n"}[args[4]]
            if args[:2] == ("image", "ls"):
                self.assertEqual(args[-1], deploy.PROJECTS["api"]["image"])
                return "sha256:current\nsha256:old1\nsha256:previous\nsha256:inuse\nsha256:old1\n"
            if args[:2] == ("image", "rm"):
                self.assertNotIn("--force", args)
                if args[2] == "sha256:inuse":
                    raise deploy.subprocess.CalledProcessError(1, args)
                removed.append(args[2])
                return ""
            raise AssertionError(args)

        with patch.object(deploy, "docker", side_effect=docker):
            deploy.prune_old_images("api", [IMAGE, previous])
        self.assertEqual(removed, ["sha256:old1"])

    def test_prune_removes_nothing_when_a_kept_image_cannot_be_resolved(self):
        def docker(*args, **kwargs):
            if args[:2] == ("image", "inspect"):
                raise deploy.subprocess.CalledProcessError(1, args)
            raise AssertionError(args)

        with patch.object(deploy, "docker", side_effect=docker):
            deploy.prune_old_images("api", [IMAGE])

    def test_prune_runs_only_after_recorded_success(self):
        with tempfile.TemporaryDirectory() as root:
            base, state = self._paths(root)
            image_inspect = json.dumps([{"Config": {"Labels": {
                "org.opencontainers.image.source": "https://github.com/VooZ2/terento",
                "org.opencontainers.image.revision": REVISION,
            }}}])
            with patch.object(deploy, "BASE", base), patch.object(deploy, "STATE", state), \
                    patch.object(deploy, "compose", return_value=""), \
                    patch.object(deploy, "docker", return_value=image_inspect), \
                    patch.object(deploy, "migrate_candidate"), patch.object(deploy, "register"), \
                    patch.object(deploy, "healthy_ids", return_value={}), patch.object(deploy, "run"), \
                    patch.object(deploy, "prune_old_images") as prune:
                deploy.deploy("api", DIGEST, REVISION)
                prune.assert_called_once_with("api", [IMAGE])
                self.assertTrue((state / "api.json").exists())

                prune.reset_mock()
                with patch.object(deploy, "run", side_effect=deploy.DeploymentError("verify failed")):
                    with self.assertRaises(deploy.DeploymentError):
                        deploy.deploy("api", "sha256:" + "d" * 64, REVISION)
                prune.assert_not_called()

    def test_status_and_ssh_boundary_are_read_only_or_deploy_only(self):
        self.assertNotIn("migration_063", deploy.STATUS_SQL)
        self.assertNotIn("--target", deploy.STATUS_SQL)
        template = (ROOT / "terento-deploy-ssh-entry.py.in").read_text(encoding="utf-8")
        self.assertIn("DEPLOY", template)
        self.assertNotIn("MIGRATE", template)
        self.assertNotIn("STATUS =", template)

    def test_candidate_status_accepts_only_digest_and_revision(self):
        self.assertEqual(
            deploy.validate_status(["--candidate-digest", DIGEST, "--candidate-revision", REVISION]),
            {"digest": DIGEST, "revision": REVISION},
        )
        with self.assertRaises(deploy.DeploymentError):
            deploy.validate_status(["--candidate-digest", DIGEST])


if __name__ == "__main__":
    unittest.main()

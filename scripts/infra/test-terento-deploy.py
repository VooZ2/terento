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


def image_id(char):
    return "sha256:" + char * 64


class ImagePruneTests(unittest.TestCase):
    def _docker(self, removed, fail_rmi=()):
        # Images a..f and 0, newest first by creation time; c is used by a stopped container.
        created = {image_id(c): "2026-10-0%dT00:00:00Z" % (9 - n) for n, c in enumerate("abcdef0")}
        references = {"current": image_id("a"), "previous": image_id("d")}

        def docker(*args, **kwargs):
            if args[:3] == ("image", "inspect", "--format") and args[3] == "{{.Id}}":
                return references[args[4]] + "\n"
            if args[:3] == ("image", "inspect", "--format"):
                return created[args[4]] + "\n"
            if args[0] == "ps":
                return "container1\ncontainer2\n"
            if args[:2] == ("inspect", "--type=container"):
                return image_id("c") + "\n" + image_id("9") + "\n"
            if args[0] == "images":
                self.assertEqual(args[-1], deploy.PROJECTS["api"]["image"])
                return "\n".join(created) + "\n" + image_id("a") + "\n"
            if args[0] == "rmi":
                self.assertEqual(len(args), 2, "rmi must never be forced or batched")
                if args[1] in fail_rmi:
                    raise deploy.subprocess.CalledProcessError(1, "docker rmi")
                removed.append(args[1])
                return ""
            raise AssertionError(args)

        return docker

    def test_keeps_current_previous_in_use_and_two_newest_others(self):
        removed = []
        with patch.object(deploy, "docker", side_effect=self._docker(removed)):
            result = deploy.prune_images("api", ["current", "previous"])
        # Kept: a (current), d (previous), c (container), b and e (two newest others).
        self.assertEqual(removed, [image_id("f"), image_id("0")])
        self.assertEqual(result, (2, 0))

    def test_failures_are_counted_and_never_raised(self):
        removed = []
        with patch.object(deploy, "docker", side_effect=self._docker(removed, fail_rmi={image_id("f")})):
            self.assertEqual(deploy.prune_images("api", ["current", "previous"]), (1, 1))
        with patch.object(deploy, "docker", side_effect=deploy.subprocess.CalledProcessError(1, "docker")):
            self.assertEqual(deploy.prune_images("api", ["current"]), (0, 1))

    def test_deploy_prunes_only_after_recorded_success_and_tolerates_prune_failure(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "config"
            state = Path(root) / "state"
            (base / "site").mkdir(parents=True)
            (base / "site" / "enabled").touch()
            state.mkdir()
            old_image = deploy.PROJECTS["site"]["image"] + "@sha256:" + "c" * 64
            (state / "site.json").write_text(json.dumps({"image": old_image, "commit": "d" * 40, "previous": None}))
            image = deploy.PROJECTS["site"]["image"] + "@" + DIGEST
            image_inspect = json.dumps([{"Config": {"Labels": {
                "org.opencontainers.image.source": "https://github.com/VooZ2/terento",
                "org.opencontainers.image.revision": REVISION,
            }}}])

            def prune(project, references):
                self.assertTrue(json.loads((state / "site.json").read_text())["image"] == image)
                self.assertEqual(references, [image, old_image])
                return (0, 3)

            with patch.object(deploy, "BASE", base), patch.object(deploy, "STATE", state), \
                    patch.object(deploy, "compose", return_value=""), \
                    patch.object(deploy, "docker", return_value=image_inspect), \
                    patch.object(deploy, "healthy_ids", return_value={"site": {}}), \
                    patch.object(deploy, "register"), patch.object(deploy, "run"), \
                    patch.object(deploy, "prune_images", side_effect=prune) as pruned:
                deploy.deploy("site", DIGEST, REVISION)
            pruned.assert_called_once()

    def test_failed_deploy_does_not_prune(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "config"
            (base / "api").mkdir(parents=True)
            (base / "api" / "enabled").touch()
            image_inspect = json.dumps([{"Config": {"Labels": {
                "org.opencontainers.image.source": "https://github.com/VooZ2/terento",
                "org.opencontainers.image.revision": REVISION,
            }}}])
            with patch.object(deploy, "BASE", base), patch.object(deploy, "STATE", Path(root) / "state"), \
                    patch.object(deploy, "compose", return_value=""), \
                    patch.object(deploy, "docker", return_value=image_inspect), \
                    patch.object(deploy, "migrate_candidate", side_effect=deploy.DeploymentError("migration failed")), \
                    patch.object(deploy, "prune_images") as pruned:
                with self.assertRaises(deploy.DeploymentError):
                    deploy.deploy("api", DIGEST, REVISION)
            pruned.assert_not_called()


if __name__ == "__main__":
    unittest.main()

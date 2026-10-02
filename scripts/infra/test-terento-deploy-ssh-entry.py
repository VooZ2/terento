"""Offline tests for the deploy-only fixed-role SSH command boundary."""

import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent
TEMPLATE = (ROOT / "terento-deploy-ssh-entry.py.in").read_text(encoding="utf-8")
DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40


def invoke(project, command):
    with tempfile.TemporaryDirectory() as directory:
        entry = Path(directory) / "entry.py"
        entry.write_text(TEMPLATE.replace("@PROJECT@", project), encoding="utf-8")
        with patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": command}, clear=True), \
                patch("subprocess.call", return_value=0) as call:
            with unittest.TestCase().assertRaises(SystemExit) as stopped:
                runpy.run_path(str(entry), run_name="__main__")
        return stopped.exception.code, call


class SSHEntryTests(unittest.TestCase):
    def test_api_deploy_is_the_only_forwarded_command(self):
        result, call = invoke("api", f"deploy {DIGEST} {REVISION}")
        self.assertEqual(result, 0)
        self.assertEqual(call.call_args.args[0], [
            "/usr/bin/sudo", "-n", "/usr/local/sbin/terento-deploy", "api", DIGEST, REVISION,
        ])
        self.assertEqual(call.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_site_and_api_reject_status_migrate_and_shell_injection(self):
        commands = ("status", "migrate", "migrate --target 063", f"deploy {DIGEST} {REVISION}; id")
        for project in ("site", "api"):
            for command in commands:
                with self.subTest(project=project, command=command):
                    result, call = invoke(project, command)
                    self.assertEqual(result, 64)
                    call.assert_not_called()

    def test_unknown_project_is_rejected(self):
        result, call = invoke("worker", f"deploy {DIGEST} {REVISION}")
        self.assertEqual(result, 64)
        call.assert_not_called()

    def test_invalid_deploy_identity_is_rejected(self):
        for command in ("deploy latest " + REVISION, "deploy " + DIGEST + " short"):
            result, call = invoke("api", command)
            self.assertEqual(result, 64)
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()

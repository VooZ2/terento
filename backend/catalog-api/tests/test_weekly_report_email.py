from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "send-weekly-health-report.py"
SPEC = importlib.util.spec_from_file_location("send_weekly_health_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class WeeklyReportEmailTests(unittest.TestCase):
    def test_message_contains_recipient_status_suites_and_run_link(self) -> None:
        message = MODULE.build_message(
            {
                "status": "FAILED", "summary": "One suite failed.",
                "releaseVersion": "1.0.0-beta.10", "buildNumber": "11",
                "commitSha": "a" * 40, "observedAt": "2026-09-02T20:00:00Z",
                "sourceRunUrl": "https://github.com/VooZ2/terento/actions/runs/123",
                "details": {"site": "success", "native": "failure"},
            },
            "report@terento.app",
            "report@terento.app",
        )
        self.assertEqual(message["To"], "report@terento.app")
        self.assertIn("Weekly project health: Failed", message["Subject"])
        body = message.get_content()
        self.assertIn("Native: failure", body)
        self.assertIn("actions/runs/123", body)
        self.assertNotIn("SMTP_PASSWORD", body)


if __name__ == "__main__":
    unittest.main()

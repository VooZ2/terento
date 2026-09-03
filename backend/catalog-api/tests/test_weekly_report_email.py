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
                "details": {
                    "site": "success", "native": "failure",
                    "catalog_freizeitkarte_status": "HEALTHY",
                    "catalog_freizeitkarte_latest_release": "2026-09",
                    "catalog_freizeitkarte_last_success": "2026-09-02T03:00:00Z",
                    "catalog_freizeitkarte_release_detected_at": "2026-09-02T03:00:00Z",
                    "catalog_freizeitkarte_new_release": True,
                    "catalog_freizeitkarte_reason": "Current.",
                    "catalog_opentopomap_status": "WARNING",
                    "catalog_opentopomap_reason": "Collection is stale.",
                },
            },
            "report@terento.app",
            "report@terento.app",
        )
        self.assertEqual(message["To"], "report@terento.app")
        self.assertIn("Weekly project health: Failed", message["Subject"])
        body = message.get_content()
        self.assertIn("Native device safety: failure", body)
        self.assertIn("Provider catalogs:", body)
        self.assertIn("Freizeitkarte: HEALTHY", body)
        self.assertIn("OpenTopoMap: WARNING", body)
        self.assertIn("Collection is stale.", body)
        self.assertIn("New release detected in the last 7 days: yes", body)
        self.assertIn("actions/runs/123", body)
        self.assertNotIn("SMTP_PASSWORD", body)


if __name__ == "__main__":
    unittest.main()

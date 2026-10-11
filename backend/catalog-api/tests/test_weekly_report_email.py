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
                },
            },
            "report@terento.app",
            "report@terento.app",
            {"schemaVersion": 1, "providers": [
                {"id": "freizeitkarte", "name": "Freizeitkarte", "status": "HEALTHY",
                 "latestRelease": "2026-09", "lastCollectionSuccess": "2026-09-02T03:00:00Z",
                 "latestReleaseDetectedAt": "2026-09-02T03:00:00Z",
                 "newReleaseDetectedInLast7Days": True, "reason": "Current."},
                {"id": "opentopomap", "name": "OpenTopoMap", "status": "WARNING",
                 "reason": "Collection is stale."},
                {"id": "maprando", "name": "MapRando", "status": "HEALTHY", "reason": "Current."},
                {"id": "bbbike", "name": "BBBike", "status": "FAILED", "reason": "Source failed."},
            ]},
        )
        self.assertEqual(message["To"], "report@terento.app")
        self.assertIn("Weekly project health: Failed", message["Subject"])
        body = message.get_content()
        self.assertIn("Native device safety: failure", body)
        self.assertIn("Provider catalogs:", body)
        self.assertIn("Freizeitkarte: HEALTHY", body)
        self.assertIn("OpenTopoMap: WARNING", body)
        self.assertIn("Collection is stale.", body)
        self.assertIn("MapRando: HEALTHY", body)
        self.assertIn("BBBike: FAILED", body)
        self.assertIn("New release detected in the last 7 days: yes", body)
        self.assertIn("actions/runs/123", body)
        self.assertNotIn("SMTP_PASSWORD", body)

    def test_missing_report_context_is_stated(self) -> None:
        body = MODULE.build_message(
            {"status": "HEALTHY", "details": {}}, "report@terento.app", "report@terento.app",
            {"schemaVersion": 1, "providers": []},
        ).get_content()
        self.assertIn("Catalog report context was unavailable.", body)


if __name__ == "__main__":
    unittest.main()

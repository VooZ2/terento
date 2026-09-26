from __future__ import annotations

import importlib.util
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from terento_catalog.admin import _system_health_cards, system_health_page
from terento_catalog.db import Database
from terento_catalog.operational_health import OperationalObservationError, validate_observation


ROOT = Path(__file__).resolve().parents[3]


def load_sender():
    spec = importlib.util.spec_from_file_location(
        "terento_submit_indexnow_observability", ROOT / "scripts/submit-indexnow.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SENDER = load_sender()


def observation(*, result: str = "submitted", status: str = "HEALTHY", details: dict | None = None) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = {
        "schemaVersion": 1,
        "observationId": "indexnow-123-1",
        "kind": "INDEXNOW",
        "component": "indexnow",
        "status": status,
        "observedAt": now.isoformat(),
        "sourceRunId": "123-1",
        "sourceRunUrl": "https://github.com/VooZ2/terento/actions/runs/123",
        "commitSha": "a" * 40,
        "summary": "IndexNow notification was accepted with HTTP 200.",
        "details": {
            "publication_id": "deployment-site-123-1",
            "result": result,
            "last_submission_at": now.isoformat(),
            "last_successful_submission_at": now.isoformat(),
            "attempted_url_count": 2,
            "http_200_count": 2,
            "http_202_count": 0,
            "http_status": 200,
            "pending_url_count": 0,
            "oldest_pending_at": None,
            "error_code": None,
            "error_summary": None,
            "url_preview": "https://terento.app/\nhttps://terento.app/about/",
            "url_preview_count": 2,
            "url_preview_total": 2,
        },
    }
    base["details"].update(details or {})
    return base


def site_observation(*, age: timedelta = timedelta(minutes=1), expected: bool = True) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0) - age
    return {
        "component": "site",
        "status": "HEALTHY",
        "observed_at": now,
        "source_run_url": "https://github.com/VooZ2/terento/actions/runs/123",
        "details": {
            "indexnow_expected": expected,
            "indexnow_publication_id": "deployment-site-123-1" if expected else None,
            "indexnow_grace_seconds": 1800,
        },
    }


class IndexNowObservationTests(unittest.TestCase):
    def test_migration_extends_existing_observation_store_only(self) -> None:
        migration = (ROOT / "backend/catalog-api/src/terento_catalog/migrations/061_indexnow_operational_observations.sql").read_text(encoding="utf-8")
        self.assertIn("operational_observation_kind_check", migration)
        self.assertIn("'INDEXNOW'", migration)
        self.assertIn("'indexnow'", migration)
        self.assertNotIn("CREATE TABLE", migration)
        self.assertNotIn("DROP TABLE", migration)

    def test_snapshot_uses_latest_per_component_without_a_generic_history_limit(self) -> None:
        source = inspect.getsource(Database.operational_health_snapshot)
        self.assertIn("DISTINCT ON (component)", source)
        self.assertIn("ORDER BY component, observed_at DESC, id DESC", source)
        self.assertNotIn("LIMIT 1", source.split("observations =", 1)[1].split("weekly =", 1)[0])

    def test_indexnow_contract_accepts_distinct_http_results(self) -> None:
        for status, result, count in ((200, "submitted", "http_200_count"), (202, "validation_pending", "http_202_count")):
            document = observation(result=result, status="HEALTHY" if status == 200 else "WARNING")
            document["details"].update({"http_status": status, "http_200_count": 0, "http_202_count": 0, count: 2})
            normalized = validate_observation(document)
            self.assertEqual(normalized["kind"], "INDEXNOW")
            self.assertEqual(normalized["details"][count], 2)

    def test_indexnow_contract_rejects_nested_unallowlisted_or_foreign_payload(self) -> None:
        for change in (
            {"raw_request": "secret"},
            {"url_preview": "https://example.com/"},
            {"url_preview": json.dumps(["https://terento.app/"])},
        ):
            document = observation(details=change)
            with self.subTest(change=change), self.assertRaises(OperationalObservationError):
                validate_observation(document)

    def test_sender_report_persists_submission_history_without_secret_material(self) -> None:
        state = {
            "schemaVersion": 1,
            "status": "published",
            "published": {"pages": []},
            "indexNow": {
                "accepted": [], "pending": [],
                "lastSubmissionAt": "2026-09-20T10:00:00Z",
                "lastSuccessfulSubmissionAt": "2026-09-20T10:00:00Z",
            },
        }
        report = SENDER.build_report(
            state, {"entries": []}, result="no_changes", publication_id="deployment-site-123-1"
        )
        self.assertEqual(report["status"], "HEALTHY")
        self.assertEqual(report["details"]["last_submission_at"], "2026-09-20T10:00:00Z")
        self.assertEqual(report["details"]["last_successful_submission_at"], "2026-09-20T10:00:00Z")
        serialized = json.dumps(report)
        self.assertNotIn("keyLocation", serialized)
        self.assertNotIn("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", serialized)

    def test_card_exposes_actionable_status_and_hides_technical_evidence(self) -> None:
        now = datetime.now(timezone.utc)
        for report, expected_status, expected_text in (
            (observation(), "HEALTHY", "Submitted"),
            (observation(result="validation_pending", status="WARNING", details={"http_status": 202, "http_200_count": 0, "http_202_count": 2, "last_successful_submission_at": None}), "WARNING", "Validation pending"),
            (observation(result="action_required", status="FAILED", details={"http_status": 403, "http_200_count": 0, "http_202_count": 0, "error_code": "http_403", "error_summary": "IndexNow returned a permanent request error."}), "FAILED", "Action required"),
            (observation(result="partial_success", status="HEALTHY", details={"http_status": 200, "http_200_count": 1, "http_202_count": 0, "error_code": None, "error_summary": "The IndexNow submission was only partially accepted."}), "WARNING", "Partial success"),
        ):
            cards, _, _ = _system_health_cards({"providers": [], "observations": [report], "scheduler": None})
            card = next(item for item in cards if item["title"] == "IndexNow submissions")
            self.assertEqual(card["status"], expected_status)
            self.assertIn(expected_text, card["html"])
            visible = card["html"].split("<details class='admin-disclosure system-health-technical'>", 1)[0]
            self.assertIn("<h2>IndexNow submissions</h2>", visible)
            self.assertEqual(visible.count("system-health-badge"), 1)
            self.assertIn("class='system-health-action'", visible)
            self.assertIn("Last checked", visible)
            self.assertNotIn("Result:", visible)
            self.assertNotIn("Pending URLs", visible)
        cards, _, _ = _system_health_cards({"providers": [], "observations": [], "scheduler": None})
        card = next(item for item in cards if item["title"] == "IndexNow submissions")
        self.assertEqual(card["status"], "UNKNOWN")
        visible = card["html"].split("<details class='admin-disclosure system-health-technical'>", 1)[0]
        details = card["html"].split("<div class='disclosure-body'>", 1)[1].split("</div></details>", 1)[0]
        self.assertIn("No IndexNow production report has been retained.", visible)
        self.assertNotIn("Pending URLs", visible)
        self.assertIn("Result: Not initialized", details)
        self.assertIn("Pending URLs", details)
        self.assertIn("Submission status only. This does not confirm search indexing.", card["html"])

    def test_pending_unknown_is_not_rendered_as_zero_and_missing_report_has_grace_period(self) -> None:
        unknown = observation(details={"pending_url_count": None, "last_submission_at": None, "last_successful_submission_at": None})
        cards, _, _ = _system_health_cards({"providers": [], "observations": [unknown], "scheduler": None})
        card = next(item for item in cards if item["title"] == "IndexNow submissions")
        self.assertIn("<dt>Pending URLs</dt><dd>—</dd>", card["html"])

        recent_site = site_observation(age=timedelta(minutes=1))
        cards, _, _ = _system_health_cards({"providers": [], "observations": [recent_site], "scheduler": None})
        card = next(item for item in cards if item["title"] == "IndexNow submissions")
        self.assertEqual(card["status"], "UNKNOWN")
        self.assertNotIn("IndexNow report missing for the latest deployment.", card["html"])

        old_site = site_observation(age=timedelta(minutes=31))
        cards, _, _ = _system_health_cards({"providers": [], "observations": [old_site], "scheduler": None})
        card = next(item for item in cards if item["title"] == "IndexNow submissions")
        self.assertEqual(card["status"], "WARNING")
        self.assertIn("IndexNow report missing for the latest deployment.", card["html"])

    def test_latest_deployment_is_not_overwritten_by_late_older_report(self) -> None:
        site = site_observation(age=timedelta(minutes=31))
        old_report = observation(details={"publication_id": "deployment-site-100-1"})
        cards, _, _ = _system_health_cards({"providers": [], "observations": [site, old_report], "scheduler": None})
        card = next(item for item in cards if item["title"] == "IndexNow submissions")
        self.assertEqual(card["status"], "WARNING")
        self.assertIn("IndexNow report missing for the latest deployment.", card["html"])

    def test_page_has_one_indexnow_card_and_does_not_offer_submission_controls(self) -> None:
        body = system_health_page(
            {"api": "HEALTHY", "database": "HEALTHY", "providers": [], "observations": [], "weekly": None, "scheduler": None},
            {"username": "operator"}, "csrf",
        ).decode()
        self.assertEqual(body.count("IndexNow submissions</h2>"), 1)
        self.assertNotIn("Retry", body)
        self.assertNotIn("Submit all", body)
        self.assertNotIn("Bing indexed", body)
        self.assertNotIn("keyLocation", body)


if __name__ == "__main__":
    unittest.main()

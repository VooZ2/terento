from __future__ import annotations

import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from terento_catalog.operational_health import (
    OperationalObservationError,
    provider_catalog_health,
    validate_observation,
)
from terento_catalog.config import Settings


def valid_observation() -> dict:
    return {
        "schemaVersion": 1,
        "observationId": "deployment-site-123",
        "kind": "DEPLOYMENT",
        "component": "site",
        "status": "HEALTHY",
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "sourceRunId": "123",
        "sourceRunUrl": "https://github.com/VooZ2/terento/actions/runs/123",
        "commitSha": "a" * 40,
        "releaseVersion": "1.0.0-beta.9",
        "buildNumber": "9",
        "summary": "Website deployment verified.",
        "details": {"manifest": "success"},
    }


class OperationalHealthTests(unittest.TestCase):
    def test_provider_catalog_observability_migration_is_additive(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "src/terento_catalog/migrations/031_provider_catalog_observability.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS latest_release", migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS catalog_fingerprint", migration)
        self.assertIn("release_change_detected", migration)
        self.assertNotIn("DROP TABLE", migration)
        self.assertNotIn("BYTEA", migration)

    def test_provider_catalog_health_distinguishes_failure_staleness_and_success(self) -> None:
        now = datetime.now(timezone.utc)
        base = {
            "id": "freizeitkarte", "name": "Freizeitkarte",
            "health": "HEALTHY", "lastCollectionStatus": "SUCCEEDED",
            "lastCollectionSuccess": now.isoformat(), "latestRelease": "2026-09",
        }
        self.assertEqual(provider_catalog_health(base, now=now)["status"], "HEALTHY")
        stale = {**base, "lastCollectionSuccess": (now - timedelta(days=3)).isoformat()}
        self.assertEqual(provider_catalog_health(stale, now=now)["status"], "WARNING")
        paused = {**base, "status": "PAUSED"}
        self.assertEqual(provider_catalog_health(paused, now=now)["status"], "WARNING")
        failed = {
            **base, "lastCollectionStatus": "FAILED",
            "lastCollectionErrorDetail": "provider timeout",
        }
        result = provider_catalog_health(failed, now=now)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("provider timeout", result["reason"])

    def test_provider_without_success_has_actionable_unknown_state(self) -> None:
        result = provider_catalog_health({"id": "opentopomap", "name": "OpenTopoMap"})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("Run the provider collector", result["action"])

    def test_valid_observation_is_normalized(self) -> None:
        result = validate_observation(valid_observation())
        self.assertEqual(result["component"], "site")
        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["details"], {"manifest": "success"})

    def test_non_terento_actions_url_is_rejected(self) -> None:
        document = valid_observation()
        document["sourceRunUrl"] = "https://example.com/actions/runs/123"
        with self.assertRaisesRegex(OperationalObservationError, "invalid_source_run_url"):
            validate_observation(document)

    def test_nested_or_oversized_details_are_rejected(self) -> None:
        document = valid_observation()
        document["details"] = {"rawLog": {"secret": "must not be stored"}}
        with self.assertRaisesRegex(OperationalObservationError, "invalid_detail_value"):
            validate_observation(document)

    def test_stale_replayed_observation_is_rejected(self) -> None:
        document = valid_observation()
        document["observedAt"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        with self.assertRaisesRegex(OperationalObservationError, "observed_at_out_of_range"):
            validate_observation(document)

    def test_ingestion_secret_requires_independent_high_entropy_value(self) -> None:
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://example", "OPERATIONS_INGEST_SECRET": "short"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "32–512"):
                Settings.from_env()
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://example", "OPERATIONS_INGEST_SECRET": "x" * 48}, clear=True):
            self.assertEqual(Settings.from_env().operations_ingest_secret, "x" * 48)


if __name__ == "__main__":
    unittest.main()

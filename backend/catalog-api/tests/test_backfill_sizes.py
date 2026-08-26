from __future__ import annotations

import unittest

from terento_catalog.backfill_sizes import backfill_sizes
from terento_catalog.collectors.freizeitkarte.range_zip import (
    ZipPayloadMeasurement,
    ZipRangeError,
)


class FakeDatabase:
    def __init__(self) -> None:
        self.targets = [
            {
                "id": 1,
                "source_url": "https://download.example/deu.zip",
                "install_payload_path": None,
                "download_size_bytes": None,
                "install_size_bytes": None,
            }
        ]
        self.updates: list[dict[str, object]] = []

    def map_size_targets(self):
        return self.targets

    def update_map_size_metadata(self, **values):
        self.updates.append(values)
        target = self.targets[0]
        changed = target["download_size_bytes"] != values["download_size_bytes"] or target["install_size_bytes"] != values["install_size_bytes"]
        if values["download_size_bytes"] is not None:
            target["download_size_bytes"] = values["download_size_bytes"]
        if values["install_size_bytes"] is not None:
            target["install_size_bytes"] = values["install_size_bytes"]
        return changed


class FakeInspector:
    def __init__(self, measurement=None, error: Exception | None = None) -> None:
        self.measurement = measurement
        self.error = error
        self.calls = 0

    def inspect(self, url: str, *, expected_payload_path: str):
        self.calls += 1
        if self.error:
            raise self.error
        return self.measurement


class SizeBackfillTests(unittest.TestCase):
    def test_backfill_persists_explicit_sizes_and_is_idempotent(self) -> None:
        database = FakeDatabase()
        inspector = FakeInspector(
            ZipPayloadMeasurement(298, 348, "gmapsupp.img", "zip-central-directory-range")
        )

        first = backfill_sizes(database, inspector=inspector)
        second = backfill_sizes(database, inspector=inspector)

        self.assertEqual(first.known_install_size, 1)
        self.assertEqual(first.changed, 1)
        self.assertEqual(second.changed, 0)
        self.assertEqual(inspector.calls, 2)
        self.assertEqual(database.targets[0]["download_size_bytes"], 298)
        self.assertEqual(database.targets[0]["install_size_bytes"], 348)

    def test_unknown_install_size_does_not_become_zero(self) -> None:
        database = FakeDatabase()
        inspector = FakeInspector(
            ZipPayloadMeasurement(298, None, None, "head-content-length-fallback", "Range unavailable")
        )

        result = backfill_sizes(database, inspector=inspector)

        self.assertEqual(result.unknown_install_size, 1)
        self.assertEqual(database.targets[0]["download_size_bytes"], 298)
        self.assertIsNone(database.targets[0]["install_size_bytes"])

    def test_failed_measurement_preserves_known_values(self) -> None:
        database = FakeDatabase()
        database.targets[0]["download_size_bytes"] = 298
        database.targets[0]["install_size_bytes"] = 348
        result = backfill_sizes(
            database,
            inspector=FakeInspector(error=ZipRangeError("malformed archive")),
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(database.targets[0]["download_size_bytes"], 298)
        self.assertEqual(database.targets[0]["install_size_bytes"], 348)
        self.assertEqual(database.updates[-1]["measurement_method"], "zip-range-error")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from unittest.mock import patch

from terento_catalog.scheduler import _parse_schedule, run_collection_cycle


class SchedulerTests(unittest.TestCase):
    def test_weekly_schedule_is_parsed(self) -> None:
        self.assertEqual(_parse_schedule("MON 03:00"), (0, 3, 0))

    def test_legacy_time_only_schedule_remains_daily(self) -> None:
        self.assertEqual(_parse_schedule("03:00"), (None, 3, 0))

    def test_invalid_weekday_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "MON-SUN"):
            _parse_schedule("FUNDAY 03:00")

    @patch("terento_catalog.scheduler.collect_devices_once")
    @patch("terento_catalog.scheduler.collect_provider_once")
    @patch("terento_catalog.scheduler.collect_once")
    def test_provider_jobs_are_independent(
        self, collect_fzk, collect_otm, collect_devices
    ) -> None:
        collect_fzk.side_effect = RuntimeError("FZK offline")
        run_collection_cycle(object())
        collect_fzk.assert_called_once()
        collect_otm.assert_called_once()
        collect_devices.assert_called_once()


if __name__ == "__main__":
    unittest.main()

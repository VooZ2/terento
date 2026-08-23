from __future__ import annotations

import unittest

from terento_catalog.scheduler import _parse_schedule


class SchedulerTests(unittest.TestCase):
    def test_weekly_schedule_is_parsed(self) -> None:
        self.assertEqual(_parse_schedule("MON 03:00"), (0, 3, 0))

    def test_legacy_time_only_schedule_remains_daily(self) -> None:
        self.assertEqual(_parse_schedule("03:00"), (None, 3, 0))

    def test_invalid_weekday_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "MON-SUN"):
            _parse_schedule("FUNDAY 03:00")


if __name__ == "__main__":
    unittest.main()

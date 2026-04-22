import unittest
from datetime import datetime
from unittest.mock import patch

import pytz

from newspulse.utils.time import calculate_days_old, format_iso_time_friendly, is_within_days


class TimeUtilsTest(unittest.TestCase):
    def test_format_iso_time_friendly_supports_z_suffix_and_naive_values(self):
        self.assertEqual(
            format_iso_time_friendly("2026-04-21T23:30:00Z", timezone="Asia/Shanghai"),
            "04-22 07:30",
        )
        self.assertEqual(
            format_iso_time_friendly(
                "2026-04-21 23:30:00",
                timezone="Asia/Shanghai",
                include_date=False,
            ),
            "07:30",
        )

    def test_format_iso_time_friendly_falls_back_when_timestamp_is_invalid(self):
        self.assertEqual(
            format_iso_time_friendly("2026-04-21T23:30:00.invalid"),
            "04-21 23:30",
        )

    @patch("newspulse.utils.time.get_configured_time")
    def test_is_within_days_and_calculate_days_old_share_the_same_parser(self, mock_now):
        mock_now.return_value = pytz.timezone("Asia/Shanghai").localize(
            datetime(2026, 4, 22, 12, 0, 0)
        )

        self.assertTrue(is_within_days("2026-04-21T12:00:00Z", 2))
        self.assertFalse(is_within_days("2026-04-10T12:00:00Z", 2))
        self.assertAlmostEqual(
            calculate_days_old("2026-04-21T12:00:00Z"),
            16 / 24,
            places=4,
        )


if __name__ == "__main__":
    unittest.main()

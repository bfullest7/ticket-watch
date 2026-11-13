import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import watch  # noqa: E402


class ShouldAlert(unittest.TestCase):
    def test_over_budget(self):
        self.assertFalse(watch.should_alert(600, 500, None, 10))

    def test_first_time_in_budget(self):
        self.assertTrue(watch.should_alert(480, 500, None, 10))

    def test_exactly_budget(self):
        self.assertTrue(watch.should_alert(500, 500, None, 10))

    def test_no_repeat_same_price(self):
        self.assertFalse(watch.should_alert(480, 500, 480, 10))

    def test_small_drop_ignored(self):
        self.assertFalse(watch.should_alert(475, 500, 480, 10))

    def test_bigger_drop_alerts(self):
        self.assertTrue(watch.should_alert(450, 500, 480, 10))

    def test_no_price(self):
        self.assertFalse(watch.should_alert(None, 500, None, 10))


class PricesByDate(unittest.TestCase):
    def test_matches_dates(self):
        events = [
            {"datetime_local": "2027-06-01T19:00:00", "url": "u1",
             "stats": {"lowest_price": 700, "listing_count": 90}},
            {"datetime_local": "2027-05-30T19:00:00", "url": "u0",
             "stats": {"lowest_price": 300}},
        ]
        got = watch.prices_by_date(events, ["2027-06-01"])
        self.assertEqual(list(got), ["2027-06-01"])
        self.assertEqual(got["2027-06-01"]["price"], 700)


if __name__ == "__main__":
    unittest.main()

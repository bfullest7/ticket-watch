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


class ReminderDue(unittest.TestCase):
    start = "2027-06-01T12:00:00+00:00"

    def at(self, minutes):
        import datetime
        return (datetime.datetime.fromisoformat(self.start)
                + datetime.timedelta(minutes=minutes))

    def test_not_before_15(self):
        self.assertFalse(watch.reminder_due(self.start, 0, self.at(5)))

    def test_first_reminder_on_next_check(self):
        self.assertTrue(watch.reminder_due(self.start, 0, self.at(14)))

    def test_second_waits_for_hour(self):
        self.assertFalse(watch.reminder_due(self.start, 1, self.at(30)))
        self.assertTrue(watch.reminder_due(self.start, 1, self.at(60)))

    def test_stops_after_two(self):
        self.assertFalse(watch.reminder_due(self.start, 2, self.at(300)))

    def test_no_alert_yet(self):
        self.assertFalse(watch.reminder_due(None, 0, self.at(60)))


class Emails(unittest.TestCase):
    def test_split(self):
        os.environ["ALERT_EMAIL"] = "a@x.com, b@x.com ,"
        try:
            self.assertEqual(watch.alert_emails(), ["a@x.com", "b@x.com"])
        finally:
            del os.environ["ALERT_EMAIL"]

    def test_skips_without_secrets(self):
        for k in ("ALERT_EMAIL", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
            os.environ.pop(k, None)
        self.assertIn("skipped", watch.send_email("t", "m", None))


if __name__ == "__main__":
    unittest.main()

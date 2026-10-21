import unittest
import datetime
from zoneinfo import ZoneInfo
from app.database import (
    get_athlete_date,
    get_athlete_now,
    get_athlete_timezone_name,
    set_current_timezone_context,
    reset_current_timezone_context,
    set_setting,
    DEFAULT_USER_ID
)
from app.services.review_coach import get_today_and_recent_activities, generate_ai_review_and_outlook

class TestTimezoneContinuity(unittest.TestCase):
    def test_timezone_resolution(self):
        # 1. Default should be America/New_York
        self.assertEqual(get_athlete_timezone_name(), "America/New_York")
        
        # 2. Contextvar override (e.g. from X-Timezone header)
        tok = set_current_timezone_context("America/Los_Angeles")
        try:
            self.assertEqual(get_athlete_timezone_name(), "America/Los_Angeles")
            la_date = get_athlete_date()
            self.assertIsInstance(la_date, datetime.date)
        finally:
            reset_current_timezone_context(tok)

    def test_athlete_date_consistency_at_night(self):
        # Even when UTC rolls over past midnight, Eastern time stays on the current day
        tok = set_current_timezone_context("America/New_York")
        try:
            ny_now = get_athlete_now()
            ny_date = get_athlete_date()
            self.assertEqual(ny_now.date(), ny_date)
            # In EDT (UTC-4), the hour in NY is 4 hours behind UTC
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            self.assertTrue((utc_now.hour - ny_now.hour) % 24 in (4, 5))
        finally:
            reset_current_timezone_context(tok)

if __name__ == "__main__":
    unittest.main()

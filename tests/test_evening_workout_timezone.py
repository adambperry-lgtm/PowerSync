import unittest
import json
import datetime
from app.database import (
    get_db_connection,
    init_db,
    set_setting,
    get_athlete_date,
    get_athlete_timezone
)
from app.services.strava_service import resolve_strava_local_start
from app.services.review_coach import get_activity_date_str
from app.routers.workouts import generate_workout, WorkoutGenerateRequest
from app.routers.dashboard import get_dashboard_data

class TestEveningWorkoutTimezone(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_evening_tz_test"
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (id, email, name, picture)
            VALUES (?, 'evening_test@powersync.local', 'Evening Athlete', '')
        """, (self.user_id,))
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (self.user_id,))
        c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (self.user_id,))
        conn.commit()
        conn.close()

        # Set user's timezone to Eastern Time (America/New_York)
        set_setting("athlete_timezone", "America/New_York", user_id=self.user_id)
        set_setting("athlete_ftp", 250, user_id=self.user_id)
        set_setting("demo_mode", False, user_id=self.user_id)

    def tearDown(self):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (self.user_id,))
        c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (self.user_id,))
        conn.commit()
        conn.close()

    def test_evening_workout_not_marked_as_today(self):
        """
        An activity recorded yesterday evening from 9pm-10pm (e.g. 21:11 local, 01:11 UTC next day)
        must be assigned to yesterday's date, must NOT be considered today's activity, and
        must NOT trigger 'Daily Target Achieved — Rest & Recovery' for today.
        """
        today = get_athlete_date(self.user_id)
        yesterday = today - datetime.timedelta(days=1)
        today_iso = today.isoformat()
        yesterday_iso = yesterday.isoformat()

        # Yesterday 9:11 PM EDT is UTC 01:11 next day (today)
        utc_str = f"{today_iso}T01:11:10Z"
        local_str = f"{yesterday_iso}T21:11:10Z"

        activity_payload = {
            "id": 999901,
            "name": "Zwift - 45-Min Sweet Spot Sustained Blocks",
            "type": "VirtualRide",
            "sport_type": "VirtualRide",
            "start_date": utc_str,
            "start_date_local": local_str,
            "moving_time": 2850,
            "distance": 25000.0,
            "total_elevation_gain": 200.0,
            "average_watts": 180.0,
            "weighted_average_watts": 186.0,
            "average_heartrate": 130.0,
            "max_heartrate": 150.0,
            "suffer_score": 50.0,
            "kilojoules": 500.0
        }

        # 1. Verify resolve_strava_local_start resolves to yesterday's local date
        resolved_start = resolve_strava_local_start(activity_payload, user_id=self.user_id)
        self.assertTrue(resolved_start.startswith(yesterday_iso), f"Resolved {resolved_start} should start with {yesterday_iso}")
        self.assertEqual(get_activity_date_str(activity_payload, user_id=self.user_id), yesterday_iso)

        # 2. Insert into strava_activities table with local start_date
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts,
                weighted_average_watts, average_heartrate, max_heartrate,
                suffer_score, kilojoules, raw_json
            ) VALUES (?, '999901', ?, 'VirtualRide', ?, 2850, 25000, 200, 180, 186, 130, 150, 50, 500, ?)
        """, (
            self.user_id,
            activity_payload["name"],
            resolved_start,
            json.dumps(activity_payload)
        ))

        # Add Whoop metrics for today: 95% recovery, 0.0 strain
        c.execute("""
            INSERT INTO whoop_metrics (
                user_id, date, recovery_score, hrv_rmssd, resting_heart_rate,
                sleep_performance, sleep_duration_hours, day_strain
            ) VALUES (?, ?, 95, 50.0, 55, 89, 7.5, 0.0)
        """, (self.user_id, today_iso))
        conn.commit()
        conn.close()

        # Connect Strava for this user
        set_setting("strava_tokens", json.dumps({"access_token": "mock_valid"}), user_id=self.user_id)
        set_setting("whoop_tokens", json.dumps({"access_token": "mock_valid"}), user_id=self.user_id)

        # 3. Test generate_workout with current user mock
        from unittest.mock import patch
        with patch("app.database.get_current_user_id", return_value=self.user_id), \
             patch("app.routers.workouts.get_current_user_id", return_value=self.user_id), \
             patch("app.routers.dashboard.get_current_user_id", return_value=self.user_id), \
             patch("app.services.review_coach.get_current_user_id", return_value=self.user_id), \
             patch("app.services.strava_service.get_current_user_id", return_value=self.user_id):

            # Check dashboard recent activities start_date
            dash = get_dashboard_data()
            recent_acts = dash["strava"]["recent_activities"]
            self.assertGreaterEqual(len(recent_acts), 1)
            self.assertTrue(
                recent_acts[0]["start_date"].startswith(yesterday_iso),
                f"Dashboard activity date {recent_acts[0]['start_date']} must start with yesterday's date {yesterday_iso}"
            )

            # Generate workout for today
            w_res = generate_workout(WorkoutGenerateRequest())
            active_w = w_res["active_workout"]

            # AI Coach must NOT force 'Daily Target Achieved — Rest & Recovery'
            self.assertNotEqual(
                active_w.get("title"),
                "Daily Target Achieved — Rest & Recovery",
                "AI Coach should not prescribe Rest & Recovery when the workout was done yesterday evening!"
            )
            # Duration must be active session (e.g. 45 or 35 mins), not 20m flush or rest
            self.assertGreaterEqual(active_w.get("duration_minutes", 0), 30)

if __name__ == "__main__":
    unittest.main()

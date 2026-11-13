import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import (
    init_db,
    set_current_user_context,
    set_setting,
    get_db_connection,
    DEFAULT_USER_ID,
    GUEST_USER_ID,
    create_session
)
from app.main import app
from tests.test_multi_user_isolation import ASGIClient

class TestUnauthenticatedPrivacyLockdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        set_current_user_context(DEFAULT_USER_ID)
        # Populate rich private data for usr_default
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO whoop_metrics (
                user_id, date, recovery_score, hrv_rmssd, resting_heart_rate,
                sleep_performance, sleep_duration_hours, day_strain
            ) VALUES ('usr_default', '2026-11-12', 88, 72.5, 48, 92, 8.2, 16.4)
        """)
        c.execute("""
            INSERT OR REPLACE INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, average_watts, weighted_average_watts,
                average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (
                'usr_default', 'act_private_999', 'Secret Alpine Epic 100mi', 'Ride',
                '2026-11-12T10:00:00Z', 18000, 160000, 3200, 240, 265, 145, 178, 180, 4200, '{}'
            )
        """)
        conn.commit()
        conn.close()

        set_setting("athlete_ftp", 310, user_id=DEFAULT_USER_ID)
        set_setting("whoop_tokens", {"access_token": "secret_whoop_token"}, user_id=DEFAULT_USER_ID)
        set_setting("strava_tokens", {"access_token": "secret_strava_token"}, user_id=DEFAULT_USER_ID)

    def test_01_unauthenticated_dashboard_hides_all_user_data(self):
        """Verify that an incognito / unauthenticated guest visitor sees NO private athlete data."""
        guest_client = ASGIClient(app)
        res = guest_client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Auth state must be explicitly unauthenticated
        self.assertFalse(data["authenticated"])
        self.assertTrue(data["user"]["is_guest"])
        self.assertEqual(data["user"]["id"], "usr_guest")

        # Personal biometric telemetry MUST be hidden (None)
        self.assertIsNone(data["whoop"], "Whoop biometrics must be hidden from unauthenticated guests")
        self.assertFalse(data["integrations"]["whoop"]["connected"])

        # Strava activities must be empty
        self.assertEqual(data["strava"]["recent_activities"], [], "Strava activities must not be leaked to guests")
        self.assertFalse(data["integrations"]["strava"]["connected"])

        # Programs & power spiderweb must be hidden
        self.assertIsNone(data["program"], "Program roadmap must be hidden from unauthenticated guests")
        self.assertIsNone(data["power_spiderweb"], "Power spiderweb must be hidden from unauthenticated guests")

    def test_02_unauthenticated_workouts_endpoints_withhold_athlete_schedule(self):
        """Verify workout and scheduled session endpoints do not leak directives to guests."""
        guest_client = ASGIClient(app)

        res_curr = guest_client.get("/api/workouts/current")
        self.assertEqual(res_curr.status_code, 200)
        self.assertIsNone(res_curr.json().get("active_workout"))

        res_sched = guest_client.get("/api/workouts/scheduled")
        self.assertEqual(res_sched.status_code, 200)
        self.assertEqual(res_sched.json().get("scheduled_workouts"), [])

    def test_03_unauthenticated_review_debrief_withheld(self):
        """Verify daily debrief and outlook require authentication and do not leak athlete analysis."""
        guest_client = ASGIClient(app)
        res = guest_client.get("/api/review/daily-debrief")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data.get("today_review"))
        self.assertEqual(data.get("forward_outlook"), [])
        self.assertIn("Sign in", data.get("headline", ""))

    def test_04_unauthenticated_spiderweb_withheld(self):
        """Verify radar chart and target analysis do not expose athlete power profile."""
        guest_client = ASGIClient(app)
        res = guest_client.get("/api/power/spiderweb")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("is_guest"))
        self.assertEqual(data.get("categories"), [])
        self.assertIsNone(data.get("active_goal"))

    def test_05_authenticated_athlete_sees_their_data(self):
        """Verify that when signed in with a valid session cookie, athlete telemetry is fully accessible."""
        auth_token = create_session(DEFAULT_USER_ID)
        auth_client = ASGIClient(app)
        auth_client.cookies["powersync_session"] = auth_token

        res = auth_client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertFalse(data["user"]["is_guest"])
        self.assertIsNotNone(data["whoop"])
        self.assertEqual(data["whoop"]["recovery_score"], 88)
        self.assertEqual(data["whoop"]["day_strain"], 16.4)
        self.assertTrue(len(data["strava"]["recent_activities"]) >= 1)
        self.assertEqual(data["strava"]["recent_activities"][0]["name"], "Secret Alpine Epic 100mi")

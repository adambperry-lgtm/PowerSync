import unittest
import json
import datetime
from app.main import app
from tests.test_multi_user_isolation import ASGIClient
from app.database import (
    get_db_connection,
    init_db,
    set_setting,
    set_current_user_context,
    reset_current_user_context
)
from app.services.power_profile_service import (
    calculate_activity_peak_powers,
    get_power_spiderweb_profile
)

class TestPowerSpiderweb(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_spiderweb_test"
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (id, email, name, picture)
            VALUES (?, 'spiderweb@powersync.local', 'Spiderweb Athlete', '')
        """, (self.user_id,))

        # Clear existing activities for this test user
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (self.user_id,))

        # Insert representative activities across 2 months
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_date = (now - datetime.timedelta(days=5)).isoformat()
        prior_date = (now - datetime.timedelta(days=40)).isoformat()

        # Recent high-intensity workout
        recent_raw = {
            "max_watts": 850,
            "weighted_average_watts": 280,
            "average_watts": 240
        }
        c.execute("""
            INSERT INTO strava_activities (
                id, user_id, name, sport_type, distance_meters, moving_time_sec,
                elapsed_time_sec, total_elevation_gain, start_date,
                average_watts, weighted_average_watts, kilojoules, raw_json
            ) VALUES (?, ?, ?, 'Ride', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "act_spider_1", self.user_id, "Recent Punchy Ride", 35000, 3600,
            3600, 350, recent_date, 240, 280, 864, json.dumps(recent_raw)
        ))

        # Prior base workout
        prior_raw = {
            "max_watts": 620,
            "weighted_average_watts": 220,
            "average_watts": 200
        }
        c.execute("""
            INSERT INTO strava_activities (
                id, user_id, name, sport_type, distance_meters, moving_time_sec,
                elapsed_time_sec, total_elevation_gain, start_date,
                average_watts, weighted_average_watts, kilojoules, raw_json
            ) VALUES (?, ?, ?, 'Ride', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "act_spider_2", self.user_id, "Prior Endurance Ride", 40000, 4200,
            4200, 250, prior_date, 200, 220, 840, json.dumps(prior_raw)
        ))

        conn.commit()
        conn.close()

        self.ctx_token = set_current_user_context(self.user_id)
        set_setting("athlete_ftp", 260, user_id=self.user_id)
        set_setting("athlete_weight", 70.0, user_id=self.user_id)
        self.client = ASGIClient(app)

    def tearDown(self):
        reset_current_user_context(self.ctx_token)

    def test_calculate_activity_peak_powers(self):
        activity = {
            "moving_time_seconds": 3600,
            "average_watts": 250,
            "max_watts": 800,
            "weighted_average_watts": 270,
            "raw_json": json.dumps({"max_watts": 800})
        }
        peaks = calculate_activity_peak_powers(activity, ftp=250)
        self.assertIn("5s", peaks)
        self.assertIn("1m", peaks)
        self.assertIn("5m", peaks)
        self.assertIn("20m", peaks)
        self.assertIn("60m", peaks)
        self.assertGreaterEqual(peaks["5s"], peaks["1m"])
        self.assertGreaterEqual(peaks["1m"], peaks["5m"])
        self.assertGreaterEqual(peaks["5m"], peaks["20m"])
        self.assertGreaterEqual(peaks["20m"], peaks["60m"])

    def test_spiderweb_profile_data_structure(self):
        profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe="30d")
        self.assertEqual(profile["timeframe"], "30d")
        self.assertIn("axes", profile)
        self.assertEqual(len(profile["axes"]), 5)

        axis_keys = [a["key"] for a in profile["axes"]]
        self.assertEqual(axis_keys, ["5s", "1m", "5m", "20m", "60m"])

        for ax in profile["axes"]:
            self.assertIn("current_watts", ax)
            self.assertIn("current_w_kg", ax)
            self.assertIn("current_radar_pct", ax)
            self.assertGreaterEqual(ax["current_radar_pct"], 20.0)
            self.assertLessEqual(ax["current_radar_pct"], 100.0)

        # Verify phenotype classification
        self.assertIn("phenotype", profile)
        self.assertIn("title", profile["phenotype"])
        self.assertIn("primary_strength", profile["phenotype"])
        self.assertIn("growth_focus", profile["phenotype"])

        # Verify progression timeline
        self.assertIn("progression_timeline", profile)
        self.assertGreaterEqual(len(profile["progression_timeline"]), 1)

    def test_spiderweb_timeframe_options(self):
        for tf in ["30d", "60d", "90d", "all_time", "invalid_default"]:
            profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe=tf)
            self.assertIn("axes", profile)
            self.assertEqual(len(profile["axes"]), 5)

    def test_api_power_spiderweb_endpoint(self):
        response = self.client.get(f"/api/power/spiderweb?timeframe=30d", headers={"X-User-ID": self.user_id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["timeframe"], "30d")
        self.assertIn("axes", data)
        self.assertEqual(len(data["axes"]), 5)
        self.assertIn("phenotype", data)
        self.assertIn("progression_timeline", data)

    def test_api_dashboard_includes_power_spiderweb(self):
        response = self.client.get("/api/dashboard", headers={"X-User-ID": self.user_id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("power_spiderweb", data)
        self.assertIsNotNone(data["power_spiderweb"])
        self.assertIn("axes", data["power_spiderweb"])


if __name__ == "__main__":
    unittest.main()

import unittest
import json
import datetime
from app.database import init_db, get_db_connection, set_setting, get_athlete_date
from app.services.coach_tools import (
    tool_get_strava_activity_details,
    tool_get_strava_activity_streams_and_power_curve,
    tool_search_strava_activities,
    tool_get_whoop_biometrics_timeline,
    execute_coach_tool,
    COACH_TOOL_DECLARATIONS
)

class TestCoachTools(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_test_tools"
        today = get_athlete_date(self.user_id)
        yesterday = today - datetime.timedelta(days=1)
        self.today_iso = today.isoformat()
        self.yesterday_iso = yesterday.isoformat()

        conn = get_db_connection()
        c = conn.cursor()

        # Insert test activity
        act_raw = {
            "id": 888801,
            "name": "Zwift - 45-Min Sweet Spot Sustained",
            "type": "VirtualRide",
            "sport_type": "VirtualRide",
            "start_date": f"{self.yesterday_iso}T21:00:00Z",
            "moving_time": 2700,
            "distance": 24000.0,
            "total_elevation_gain": 150.0,
            "average_watts": 190.0,
            "weighted_average_watts": 205.0,
            "average_heartrate": 135.0,
            "max_heartrate": 155.0,
            "suffer_score": 48.0,
            "kilojoules": 510.0,
            "laps": [
                {"lap_index": 1, "name": "Warmup", "moving_time": 420, "average_watts": 140, "average_heartrate": 115},
                {"lap_index": 2, "name": "Sweet Spot 1", "moving_time": 720, "average_watts": 225, "average_heartrate": 148},
                {"lap_index": 3, "name": "Valley", "moving_time": 240, "average_watts": 135, "average_heartrate": 122},
                {"lap_index": 4, "name": "Sweet Spot 2", "moving_time": 720, "average_watts": 228, "average_heartrate": 152},
                {"lap_index": 5, "name": "Cooldown", "moving_time": 300, "average_watts": 120, "average_heartrate": 112}
            ]
        }

        c.execute("""
            INSERT OR REPLACE INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts,
                weighted_average_watts, average_heartrate, max_heartrate,
                suffer_score, kilojoules, raw_json
            ) VALUES (?, '888801', ?, 'VirtualRide', ?, 2700, 24000, 150, 190, 205, 135, 155, 48, 510, ?)
        """, (
            self.user_id,
            act_raw["name"],
            f"{self.yesterday_iso}T17:00:00",
            json.dumps(act_raw)
        ))

        # Insert Whoop metrics
        c.execute("""
            INSERT OR REPLACE INTO whoop_metrics (
                user_id, date, recovery_score, hrv_rmssd, resting_heart_rate,
                sleep_performance, sleep_duration_hours, day_strain
            ) VALUES (?, ?, 88, 55.0, 52, 90, 7.8, 12.5)
        """, (self.user_id, self.yesterday_iso))

        conn.commit()
        conn.close()

    def test_tool_declarations_validity(self):
        self.assertGreaterEqual(len(COACH_TOOL_DECLARATIONS), 4)
        names = [t["name"] for t in COACH_TOOL_DECLARATIONS]
        self.assertIn("get_strava_activity_details", names)
        self.assertIn("get_strava_activity_streams_and_power_curve", names)
        self.assertIn("search_strava_activities", names)
        self.assertIn("get_whoop_biometrics_timeline", names)

    def test_get_strava_activity_details(self):
        res = tool_get_strava_activity_details(activity_id="latest", user_id=self.user_id)
        self.assertTrue(res["found"])
        self.assertEqual(res["activity_id"], "888801")
        self.assertEqual(res["power_summary"]["normalized_power_watts"], 205)
        self.assertTrue(res["has_laps"])
        self.assertEqual(len(res["laps"]), 5)
        self.assertEqual(res["laps"][1]["name"], "Sweet Spot 1")
        self.assertEqual(res["laps"][1]["avg_watts"], 225)

    def test_get_strava_activity_streams_and_power_curve(self):
        res = tool_get_strava_activity_streams_and_power_curve(activity_id="latest", user_id=self.user_id)
        self.assertTrue(res["found"])
        self.assertIn("power_curve", res)
        self.assertGreater(res["power_curve"]["peak_5s_sprint_watts"], 200)

    def test_search_strava_activities(self):
        res = tool_search_strava_activities(query="sweet spot", user_id=self.user_id)
        self.assertGreaterEqual(res["count"], 1)
        self.assertIn("Sweet Spot", res["activities"][0]["name"])

    def test_get_whoop_biometrics_timeline(self):
        res = tool_get_whoop_biometrics_timeline(days=3, user_id=self.user_id)
        self.assertGreaterEqual(res["count"], 1)
        self.assertEqual(res["timeline"][0]["recovery_score_pct"], 88)
        self.assertEqual(res["timeline"][0]["recovery_zone"], "Green")

    def test_execute_coach_tool_dispatcher(self):
        res = execute_coach_tool("get_strava_activity_details", {"activity_id": "888801"}, user_id=self.user_id)
        self.assertTrue(res["found"])
        self.assertIn("Sweet Spot", res["name"])

if __name__ == "__main__":
    unittest.main()

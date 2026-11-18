import datetime
import json
import os
import unittest

from fastapi.testclient import TestClient

from app.database import get_db_connection, init_db
from app.main import app
from app.services.ride_history_service import (
    get_ride_history_analytics,
    get_single_ride_detail,
)


class TestRideHistoryTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.test_uid = "usr_test_history_1"
        self.other_uid = "usr_test_history_2"
        conn = get_db_connection()
        c = conn.cursor()
        for uid in (self.test_uid, self.other_uid):
            c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM settings WHERE user_id = ?", (uid,))

        c.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, 'ftp', '250')",
            (self.test_uid,),
        )
        c.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, 'weight_kg', '75')",
            (self.test_uid,),
        )

        today = datetime.date.today()
        d1 = (today - datetime.timedelta(days=2)).isoformat()
        d2 = (today - datetime.timedelta(days=5)).isoformat()
        d_prev = (today - datetime.timedelta(days=40)).isoformat()

        raw_outdoor = json.dumps(
            {
                "trainer": False,
                "max_watts": 680,
                "map": {"summary_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
            }
        )
        raw_indoor = json.dumps({"trainer": True, "max_watts": 420})

        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, elapsed_time_sec,
                moving_time_sec, distance_meters, total_elevation_gain,
                average_watts, weighted_average_watts, average_heartrate,
                max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.test_uid,
                "ride_out_1",
                "Morning Marin Loop",
                "Ride",
                f"{d1}T08:00:00Z",
                5400,
                5400,
                45000.0,
                750.0,
                210.0,
                225.0,
                148.0,
                176.0,
                90.0,
                1134.0,
                raw_outdoor,
            ),
        )
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, elapsed_time_sec,
                moving_time_sec, distance_meters, total_elevation_gain,
                average_watts, weighted_average_watts, average_heartrate,
                max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.test_uid,
                "ride_in_1",
                "Zwift SST Short",
                "VirtualRide",
                f"{d2}T18:00:00Z",
                3600,
                3600,
                32000.0,
                220.0,
                215.0,
                220.0,
                152.0,
                172.0,
                72.0,
                774.0,
                raw_indoor,
            ),
        )
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, elapsed_time_sec,
                moving_time_sec, distance_meters, total_elevation_gain,
                average_watts, weighted_average_watts, average_heartrate,
                max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.test_uid,
                "ride_prev_1",
                "Prior Block Endurance",
                "Ride",
                f"{d_prev}T09:00:00Z",
                3600,
                3600,
                30000.0,
                300.0,
                180.0,
                185.0,
                140.0,
                160.0,
                50.0,
                648.0,
                raw_outdoor,
            ),
        )
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, elapsed_time_sec,
                moving_time_sec, distance_meters, total_elevation_gain,
                average_watts, weighted_average_watts, average_heartrate,
                max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.other_uid,
                "ride_other_secret",
                "Other Athlete Secret Ride",
                "Ride",
                f"{d1}T10:00:00Z",
                3600,
                3600,
                25000.0,
                100.0,
                200.0,
                200.0,
                145.0,
                165.0,
                50.0,
                720.0,
                raw_outdoor,
            ),
        )

        c.execute(
            """
            INSERT INTO whoop_metrics (user_id, date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_duration_hours)
            VALUES (?, ?, 84, 72.5, 49, 7.8)
            """,
            (self.test_uid, d1),
        )
        c.execute(
            """
            INSERT INTO whoop_metrics (user_id, date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_duration_hours)
            VALUES (?, ?, 48, 51.0, 54, 6.2)
            """,
            (self.test_uid, d2),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        conn = get_db_connection()
        c = conn.cursor()
        for uid in (self.test_uid, self.other_uid):
            c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()

    def test_html_contains_4th_history_tab(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base_dir, "app", "static", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="tabMainViewHistory"', html)
        self.assertIn('id="viewHistoryContainer"', html)
        self.assertIn('id="historyHeatmapContainer"', html)
        self.assertIn('id="historyPmcChart"', html)
        self.assertIn('id="historyRecoveryBuckets"', html)
        self.assertIn('id="historyPowerCurveChart"', html)
        self.assertIn('id="historyRecapContent"', html)
        self.assertIn('id="modalRideInspector"', html)

    def test_analytics_computation_and_isolation(self):
        res_30d = get_ride_history_analytics(user_id=self.test_uid, range_key="30d", env_filter="all")
        self.assertTrue(res_30d["success"])
        self.assertFalse(res_30d["is_guest"])
        self.assertEqual(res_30d["kpis"]["ride_count"], 2)
        self.assertAlmostEqual(res_30d["kpis"]["distance_km"], 77.0, places=1)
        self.assertEqual(len(res_30d["heatmap_rides"]), 1)
        self.assertEqual(res_30d["heatmap_rides"][0]["id"], "ride_out_1")
        self.assertTrue(len(res_30d["pmc_series"]) >= 30)
        self.assertEqual(res_30d["recovery_matrix"]["buckets"]["green"]["ride_count"], 1)
        self.assertEqual(res_30d["recovery_matrix"]["buckets"]["yellow"]["ride_count"], 1)
        self.assertTrue(res_30d["year_in_sport"]["has_data"])
        # Ensure other user's ride is never included
        ride_ids = [r["id"] for r in res_30d["rides"]]
        self.assertNotIn("ride_other_secret", ride_ids)
        # Ensure 3-tier strain is populated in both rides and volume_buckets
        self.assertTrue(any(r["strain_low"] > 0 for r in res_30d["rides"]))
        self.assertTrue(any(b["strain_low"] > 0 for b in res_30d["volume_buckets"]))

    def test_env_filter_and_single_ride_detail(self):
        res_out = get_ride_history_analytics(user_id=self.test_uid, range_key="30d", env_filter="outdoor")
        self.assertEqual(res_out["kpis"]["ride_count"], 1)
        self.assertEqual(res_out["rides"][0]["id"], "ride_out_1")

        detail = get_single_ride_detail("ride_out_1", user_id=self.test_uid)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["ride"]["whoop_recovery"], 84)
        self.assertIsNone(get_single_ride_detail("ride_other_secret", user_id=self.test_uid))

    def test_guest_and_http_endpoints(self):
        # Guest endpoint must return empty/is_guest=True
        resp_guest = self.client.get("/api/history/analytics?range=90d")
        self.assertEqual(resp_guest.status_code, 200)
        self.assertTrue(resp_guest.json()["is_guest"])

        # Authenticated via x-user-id header
        resp_auth = self.client.get(
            "/api/history/analytics?range=30d&env=all",
            headers={"x-user-id": self.test_uid},
        )
        self.assertEqual(resp_auth.status_code, 200)
        data = resp_auth.json()
        self.assertEqual(data["kpis"]["ride_count"], 2)

        resp_detail = self.client.get(
            "/api/history/ride/ride_out_1",
            headers={"x-user-id": self.test_uid},
        )
        self.assertEqual(resp_detail.status_code, 200)
        self.assertEqual(resp_detail.json()["ride"]["name"], "Morning Marin Loop")


if __name__ == "__main__":
    unittest.main()

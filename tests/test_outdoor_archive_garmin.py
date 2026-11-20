import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from app.database import (
    DEFAULT_USER_ID,
    GUEST_USER_ID,
    get_db_connection,
    init_db,
    reset_current_user_context,
    set_current_user_context,
)
from app.main import app
from app.services.garmin_service import fetch_activity_gpx_data, generate_gpx_from_points, push_course_to_garmin
from app.services.outdoor_coach import build_outdoor_ride_recommendation
from app.services.workout_archive_service import get_archived_outdoor_routes

SAMPLE_POLY = "ginwFry|dMVHvZmBfMyAz@pAVLpBiERuAq@sE{DoG{AoFOaA"


class TestOutdoorArchiveAndGarmin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.user_a = "usr_test_outdoor_a"
        self.user_b = "usr_test_outdoor_b"
        conn = get_db_connection()
        c = conn.cursor()
        for uid in (self.user_a, self.user_b):
            c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
        # Insert 63m ride and 90m ride for user_a
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, average_watts, weighted_average_watts, suffer_score, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.user_a,
                "900001",
                "Short 63m Loop",
                "Ride",
                "2026-11-15T09:00:00",
                63 * 60,
                30000.0,  # ~18.6 mi
                350.0,
                220.0,
                225.0,
                55.0,
                json.dumps({"map": {"summary_polyline": SAMPLE_POLY}}),
            ),
        )
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, average_watts, weighted_average_watts, suffer_score, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.user_a,
                "900002",
                "90m Gravel Fondo",
                "GravelRide",
                "2026-10-10T08:00:00",
                90 * 60,
                48280.0,  # ~30.0 mi
                600.0,
                195.0,
                205.0,
                75.0,
                json.dumps({"map": {"summary_polyline": SAMPLE_POLY}}),
            ),
        )
        # Insert user_b private ride
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, average_watts, weighted_average_watts, suffer_score, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.user_b,
                "900003",
                "User B Secret Route",
                "Ride",
                "2026-11-12T08:00:00",
                120 * 60,
                64373.0,
                900.0,
                210.0,
                215.0,
                90.0,
                json.dumps({"map": {"summary_polyline": SAMPLE_POLY}}),
            ),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        conn = get_db_connection()
        c = conn.cursor()
        for uid in (self.user_a, self.user_b):
            c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()

    def test_outdoor_archive_time_distance_filters_and_isolation(self):
        # User A sees only their own rides
        all_a = get_archived_outdoor_routes(user_id=self.user_a, ftp=250)
        ids_a = {r["id"] for r in all_a}
        self.assertEqual(ids_a, {"900001", "900002"})

        # Filter by 75-90m time window
        filtered_time = get_archived_outdoor_routes(
            user_id=self.user_a, ftp=250, min_duration_min=75, max_duration_min=90
        )
        self.assertEqual([r["id"] for r in filtered_time], ["900002"])

        # Filter by 25-40 mi distance window
        filtered_dist = get_archived_outdoor_routes(
            user_id=self.user_a, ftp=250, min_distance_mi=25.0, max_distance_mi=40.0
        )
        self.assertEqual([r["id"] for r in filtered_dist], ["900002"])

        # Guest sees nothing
        guest_routes = get_archived_outdoor_routes(user_id=GUEST_USER_ID, ftp=250)
        self.assertEqual(guest_routes, [])

    def test_outdoor_recommendation_respects_75_90_minute_range(self):
        tok = set_current_user_context(self.user_a)
        try:
            with patch("app.services.outdoor_coach.get_setting", return_value={"access_token": "tok"}):
                bundle = build_outdoor_ride_recommendation(
                    recovery_score=80,
                    hrv_rmssd=55.0,
                    sleep_score=88,
                    recent_volume_hours=4.5,
                    recent_high_intensity=False,
                    target_duration_min=60,
                    ftp=250,
                    user_note="I want to do a 75-90 minute outdoor ride",
                )
            primary = bundle["primary"]
            self.assertEqual(primary["id"], "900002")
            self.assertGreaterEqual(primary["moving_time_min"], 75)
        finally:
            reset_current_user_context(tok)

    def test_gpx_generation_and_garmin_course_push(self):
        gpx_res = fetch_activity_gpx_data("900002", user_id=self.user_a)
        self.assertTrue(gpx_res["success"])
        self.assertIn("<trkpt", gpx_res["gpx_xml"])
        self.assertIn("90m Gravel Fondo", gpx_res["gpx_xml"])

        mock_client = MagicMock()
        mock_client.client.post.side_effect = [
            {
                "courseName": "90m Gravel Fondo",
                "coordinateSystem": "WGS84",
                "distanceMeter": 48280.0,
                "elevationGainMeter": 600.0,
                "elevationLossMeter": 590.0,
                "geoPoints": [{"latitude": 40.0, "longitude": -74.0}],
                "boundingBox": {},
            },
            {"courseId": 12345678},
        ]

        with patch("app.services.garmin_service._get_garmin_client", return_value=mock_client):
            push_res = push_course_to_garmin(
                course_name="90m Gravel Fondo",
                gpx_xml=gpx_res["gpx_xml"],
                sport_type="GravelRide",
                user_id=self.user_a,
            )
        self.assertTrue(push_res["success"])
        self.assertEqual(push_res["course_id"], 12345678)
        self.assertIn("connect.garmin.com/modern/course/12345678", push_res["course_url"])
        self.assertEqual(mock_client.client.post.call_count, 2)

    def test_outdoor_recommendation_inherits_active_90m_workout(self):
        tok = set_current_user_context(self.user_a)
        try:
            with patch("app.services.outdoor_coach.get_setting", return_value={"access_token": "tok"}):
                bundle = build_outdoor_ride_recommendation(
                    recovery_score=80,
                    hrv_rmssd=55.0,
                    sleep_score=88,
                    recent_volume_hours=4.5,
                    recent_high_intensity=False,
                    target_duration_min=90,
                    ftp=250,
                    user_note="",
                    explicit_duration=True,
                )
            self.assertEqual(bundle["primary"]["id"], "900002")
            self.assertEqual(bundle["primary"]["moving_time_min"], 90)
        finally:
            reset_current_user_context(tok)

    def test_map_null_and_virtual_ride_handling(self):
        conn = get_db_connection()
        c = conn.cursor()
        # Insert a ride with map: null and a VirtualRide
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.user_a, "900004", "Outdoor No Map", "Ride", "2026-11-16T08:00:00", 3600, 25000.0, 200.0, json.dumps({"map": None, "start_latlng": [40.0, -74.0]})),
        )
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.user_a, "900005", "Zwift - Watopia", "VirtualRide", "2026-11-17T08:00:00", 3600, 30000.0, 300.0, json.dumps({"map": None, "trainer": True})),
        )
        conn.commit()
        conn.close()

        routes = get_archived_outdoor_routes(user_id=self.user_a, ftp=250)
        ids = {r["id"] for r in routes}
        self.assertIn("900004", ids)
        self.assertNotIn("900005", ids)


if __name__ == "__main__":
    unittest.main()

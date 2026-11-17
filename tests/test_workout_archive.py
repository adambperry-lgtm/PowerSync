import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import (
    init_db,
    reset_current_user_context,
    set_current_user_context,
    set_setting,
)
from app.main import app
from app.services.coach_tools import execute_coach_tool
from app.services.workout_archive_service import (
    adjust_workout_structure,
    calculate_workout_metrics,
    delete_archived_workout,
    get_archived_workouts,
    get_workout_library,
    save_custom_workout,
)


class TestWorkoutArchiveAndAgent(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_a = "usr_archive_test_a"
        self.user_b = "usr_archive_test_b"
        self.tok = set_current_user_context(self.user_a)
        set_setting("athlete_ftp", 260, user_id=self.user_a)
        set_setting("athlete_ftp", 220, user_id=self.user_b)

    def tearDown(self):
        # Clean up test workouts
        for uid in (self.user_a, self.user_b):
            for w in get_archived_workouts(user_id=uid):
                delete_archived_workout(w["id"], user_id=uid)
        reset_current_user_context(self.tok)

    def test_coggan_metrics_and_adjustment(self):
        intervals = [
            {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 75},
            {"type": "SteadyState", "duration_sec": 1800, "power_pct": 100},
            {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 45},
        ]
        m = calculate_workout_metrics(intervals, ftp=260)
        self.assertEqual(m["total_duration_sec"], 2400)
        self.assertEqual(m["duration_minutes"], 40)
        self.assertGreater(m["normalized_power_watts"], 220)
        self.assertGreater(m["estimated_tss"], 45)

        adjusted = adjust_workout_structure(
            {"title": "Test", "intervals": intervals},
            target_duration_min=60,
            intensity_adjust_pct=5,
            ftp=260,
        )
        self.assertEqual(adjusted["duration_minutes"], 60)
        self.assertGreater(adjusted["estimated_tss"], m["estimated_tss"])
        self.assertIn("Warmup", adjusted["zwo_content"])

    def test_library_and_multiuser_archive_isolation(self):
        library = get_workout_library(ftp=260, duration_min=60)
        self.assertGreaterEqual(len(library), 19)
        self.assertTrue(any(w["archetype_id"] == "sst_criss_cross" for w in library))

        saved_a = save_custom_workout(
            {
                "title": "User A Custom Threshold",
                "focus_area": "Threshold",
                "intervals": [
                    {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 75},
                    {"type": "SteadyState", "duration_sec": 1200, "power_pct": 98},
                    {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 45},
                ],
            },
            user_id=self.user_a,
            ftp=260,
        )
        self.assertTrue(saved_a["id"].startswith("custom_"))
        self.assertEqual(saved_a["duration_minutes"], 30)

        arch_a = get_archived_workouts(user_id=self.user_a, ftp=260)
        arch_b = get_archived_workouts(user_id=self.user_b, ftp=220)
        self.assertTrue(any(w["id"] == saved_a["id"] for w in arch_a))
        self.assertFalse(any(w["id"] == saved_a["id"] for w in arch_b))

    def test_coach_agent_archive_customize_and_zwift_tools(self):
        # 1. Search library & archive
        search_res = execute_coach_tool(
            "search_workout_archive_and_library",
            {"query": "criss", "source": "library", "duration_min": 60},
            user_id=self.user_a,
        )
        self.assertGreaterEqual(search_res["library_count"], 1)
        self.assertEqual(search_res["library_workouts"][0]["archetype_id"], "sst_criss_cross")

        # 2. Customize & save
        cust_res = execute_coach_tool(
            "customize_and_save_workout",
            {
                "archetype_id": "sst_criss_cross",
                "new_title": "Adam Custom Criss-Cross 75m",
                "duration_min": 75,
                "intensity_adjust_pct": -5,
                "notes": "Dialed back 5% for moderate recovery.",
            },
            user_id=self.user_a,
        )
        self.assertTrue(cust_res["success"])
        self.assertEqual(cust_res["workout"]["duration_minutes"], 75)
        self.assertEqual(cust_res["workout"]["title"], "Adam Custom Criss-Cross 75m")
        custom_id = cust_res["workout"]["id"]

        # 3. Send to Zwift via Intervals.icu (mocked)
        set_setting("intervals_athlete_id", "i12345", user_id=self.user_a)
        set_setting("intervals_icu_api_key", "secret_key_123", user_id=self.user_a)
        with patch("app.services.zwift_service.push_to_intervals_icu") as mock_push:
            mock_push.return_value = {
                "success": True,
                "message": "Scheduled on Intervals.icu!",
                "event_ids": [999],
            }
            zwift_res = execute_coach_tool(
                "send_workout_to_zwift",
                {
                    "workout_id": custom_id,
                    "target_date": "2026-11-15",
                },
                user_id=self.user_a,
            )
            self.assertTrue(zwift_res["success"])
            self.assertEqual(zwift_res["title"], "Adam Custom Criss-Cross 75m")
            mock_push.assert_called_once()

    def test_api_endpoints_and_ui_presence(self):
        client = TestClient(app)
        # Verify HTML/CSS/JS contain Workout Archive tab & editor
        base_dir = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base_dir, "app", "static", "index.html"), encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(base_dir, "app", "static", "js", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn('id="tabMainViewArchive"', html)
        self.assertIn('id="viewArchiveContainer"', html)
        self.assertIn("function loadWorkoutArchive", js)
        self.assertIn("function pushArchiveWorkoutToZwift", js)

        # Verify /api/workouts/archive returns library workouts
        resp = client.get("/api/workouts/archive?duration_min=45")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(len(data["library_workouts"]), 19)

        # Verify /api/workouts/archive/preview recalculates duration & TSS
        prev_resp = client.post(
            "/api/workouts/archive/preview",
            json={
                "title": "Preview Ride",
                "intervals": [
                    {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 75},
                    {"type": "SteadyState", "duration_sec": 1500, "power_pct": 90},
                    {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 45},
                ],
            },
        )
        self.assertEqual(prev_resp.status_code, 200)
        prev_data = prev_resp.json()
        self.assertTrue(prev_data["success"])
        self.assertEqual(prev_data["workout"]["duration_minutes"], 35)
        self.assertGreater(prev_data["workout"]["estimated_tss"], 20)

    def test_date_scoped_scheduled_workouts_and_strava_history(self):
        from app.database import get_db_connection, save_scheduled_workout

        intervals = [
            {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 75},
            {"type": "SteadyState", "duration_sec": 1500, "power_pct": 88},
            {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 45},
        ]
        id_sun = save_scheduled_workout(
            {"id": "workout_primary", "title": "Sunday Sweet Spot", "intervals": intervals},
            "2026-11-15",
            user_id=self.user_a,
        )
        id_tue = save_scheduled_workout(
            {"id": "workout_primary", "title": "Tuesday VO2", "intervals": intervals},
            "2026-11-17",
            user_id=self.user_a,
        )
        self.assertNotEqual(id_sun, id_tue)
        self.assertEqual(id_sun, "workout_primary_20261115")
        self.assertEqual(id_tue, "workout_primary_20261117")

        # Insert a completed Strava/Zwift ride for user_a and ensure it appears in archive
        conn = get_db_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO strava_activities
            (user_id, id, name, sport_type, start_date, elapsed_time_sec, moving_time_sec, average_watts, weighted_average_watts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.user_a, "99887766", "Sunday Zwift Watopia Tempo", "VirtualRide", "2026-11-15T10:00:00Z", 3600, 3540, 210.0, 224.0),
        )
        conn.commit()
        conn.close()

        try:
            arch_a = get_archived_workouts(user_id=self.user_a, ftp=260)
            titles = [w["title"] for w in arch_a]
            self.assertIn("Sunday Sweet Spot", titles)
            self.assertIn("Tuesday VO2", titles)
            self.assertIn("Sunday Zwift Watopia Tempo", titles)

            strava_item = next(w for w in arch_a if w["id"] == "strava_99887766")
            self.assertEqual(strava_item["origin"], "strava")
            self.assertEqual(strava_item["status"], "completed_ride")
            self.assertGreater(len(strava_item["intervals"]), 0)

            cloned = save_custom_workout(strava_item, user_id=self.user_a, ftp=260)
            self.assertTrue(cloned["id"].startswith("custom_"))
        finally:
            conn = get_db_connection()
            conn.execute("DELETE FROM strava_activities WHERE user_id = ? AND id = ?", (self.user_a, "99887766"))
            conn.commit()
            conn.close()


if __name__ == "__main__":
    unittest.main()

import unittest
import datetime
import json
from app.database import init_db, set_setting, set_current_user_context, get_db_connection
from app.services.review_coach import (
    build_daily_review_and_outlook_local,
    get_today_and_recent_activities,
    get_activity_date_str
)

class TestMultiWorkoutDay(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "test_multi_workout_athlete"
        set_current_user_context(self.user_id)
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (self.user_id,))
        c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (self.user_id,))
        c.execute("DELETE FROM settings WHERE user_id = ?", (self.user_id,))
        conn.commit()
        conn.close()

    def test_multi_workout_collective_aggregation(self):
        """
        Verify that a 50m primary workout and 15m cooldown spin on the same day
        are assessed collectively without the cooldown dragging down target fidelity.
        """
        from app.database import get_athlete_date
        today_iso = get_athlete_date().isoformat()
        
        # Primary session: 50m Sweet Spot @ 230W (FTP 250W -> 92%)
        primary_session = {
            "id": 1001,
            "name": "Sweet Spot Over-Unders",
            "start_date": f"{today_iso}T08:00:00Z",
            "moving_time_sec": 3000, # 50 mins
            "distance_meters": 24000.0,
            "total_elevation_gain": 250,
            "average_watts": 225.0,
            "weighted_average_watts": 230.0,
            "average_heartrate": 154.0,
            "suffer_score": 52,
            "kilojoules": 690.0,
            "raw_json": json.dumps({"start_date_local": f"{today_iso}T08:00:00"})
        }

        # Secondary session: 15m Cooldown Spin @ 110W (FTP 250W -> 44%)
        cooldown_session = {
            "id": 1002,
            "name": "Post-Ride Easy Spin",
            "start_date": f"{today_iso}T09:00:00Z",
            "moving_time_sec": 900, # 15 mins
            "distance_meters": 5000.0,
            "total_elevation_gain": 10,
            "average_watts": 110.0,
            "weighted_average_watts": 110.0,
            "average_heartrate": 118.0,
            "suffer_score": 6,
            "kilojoules": 100.0,
            "raw_json": json.dumps({"start_date_local": f"{today_iso}T09:00:00"})
        }

        # Strava returns newest first (cooldown at index 0, primary at index 1)
        today_acts = [cooldown_session, primary_session]

        whoop_data = {
            "recovery_score": 75,
            "hrv_rmssd": 55.0,
            "day_strain": 14.5,
            "sleep_performance": 90
        }

        review = build_daily_review_and_outlook_local(
            whoop_data=whoop_data,
            trailing_strava={"acute_weighted_tss": 120, "total_tss": 340},
            today_acts=today_acts,
            latest_act=cooldown_session,
            program={"phase": "Build Phase"},
            ftp=250,
            max_hr=185,
            day_acts=today_acts
        )

        sess = review["today_assessment"]

        # 1. Verification of Collective Aggregation
        self.assertEqual(sess["moving_time_min"], 65) # 50m + 15m
        self.assertEqual(sess["distance_km"], 29.0) # 24km + 5km
        self.assertEqual(sess["elevation_m"], 260) # 250m + 10m
        self.assertEqual(sess["sessions_count"], 2)
        self.assertEqual(len(sess["sessions"]), 2)

        # 2. Coggan 4th-power Combined NP preserves workout intensity (should be ~216W, NOT 110W or 170W)
        self.assertGreater(sess["weighted_watts"], 210)
        self.assertLess(sess["weighted_watts"], 230)

        # 3. Combined TSS is the sum of both sessions (~50 TSS + ~6 TSS)
        self.assertGreater(sess["calculated_tss"], 50)

        # 4. Identification of Primary vs Cooldown sessions
        primary_info = [s for s in sess["sessions"] if s["is_primary"]][0]
        cooldown_info = [s for s in sess["sessions"] if not s["is_primary"]][0]
        self.assertEqual(primary_info["name"], "Sweet Spot Over-Unders")
        self.assertEqual(cooldown_info["name"], "Post-Ride Easy Spin")

        # 5. Target Compliance: 75% Whoop recovery targets Sweet Spot (90% FTP = 225W).
        # Primary session was 230W (92% FTP). diff <= 8% -> Execution Bullseye!
        self.assertEqual(sess["verdict"], "Execution Bullseye")
        self.assertIn("🎯", sess["verdict_badge"])
        self.assertGreaterEqual(sess["compliance_score"], 90)

        # 6. Debrief text explicitly covers multi-session execution and active recovery flush
        self.assertIn("multi-session", sess["assessment_text"])
        self.assertIn("Sweet Spot Over-Unders", sess["assessment_text"])
        self.assertIn("lactate", sess["assessment_text"])

    def test_get_today_and_recent_activities_groups_same_day(self):
        """Verify DB queries group multiple activities occurring on the same date."""
        from app.database import get_athlete_date
        today_iso = get_athlete_date().isoformat()
        set_setting("strava_tokens", json.dumps({"access_token": "mock"}))

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO strava_activities (
                id, user_id, name, sport_type, start_date, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts,
                weighted_average_watts, average_heartrate, max_heartrate,
                suffer_score, kilojoules, raw_json
            ) VALUES
            ('2001', ?, 'Main Threshold Intervals', 'Ride', ?, 2700, 20000, 200, 240, 245, 160, 178, 65, 650, ?),
            ('2002', ?, 'Spin Out Legs Cooldown', 'Ride', ?, 600, 3000, 5, 100, 100, 115, 125, 4, 60, ?)
        """, (
            self.user_id,
            f"{today_iso}T07:30:00Z",
            json.dumps({"start_date_local": f"{today_iso}T07:30:00"}),
            self.user_id,
            f"{today_iso}T08:20:00Z",
            json.dumps({"start_date_local": f"{today_iso}T08:20:00"})
        ))
        conn.commit()
        conn.close()

        res = get_today_and_recent_activities()
        # Even if latest_activity is the cooldown (2002), day_activities contains BOTH
        self.assertEqual(len(res["day_activities"]), 2)
        activity_ids = [str(a["id"]) for a in res["day_activities"]]
        self.assertIn("2001", activity_ids)
        self.assertIn("2002", activity_ids)

if __name__ == "__main__":
    unittest.main()

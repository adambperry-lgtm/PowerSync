import unittest
import datetime
from app.database import init_db, set_setting, get_setting, set_current_user_context, get_db_connection
from app.services.ftp_test_service import (
    evaluate_ftp_test_readiness,
    build_ftp_test_workout,
    record_ftp_test_result,
)
from app.services.ai_coach import build_adaptive_workout_local


class TestFtpTestReadiness(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_a = "user_ftp_test_a"
        self.user_b = "user_ftp_test_b"
        set_current_user_context(self.user_a)
        self._cleanup()
        set_setting("athlete_ftp", 250, user_id=self.user_a)
        set_setting("athlete_ftp", 300, user_id=self.user_b)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_db_connection()
        c = conn.cursor()
        test_users = (self.user_a, self.user_b)
        c.execute("DELETE FROM strava_activities WHERE user_id IN (?, ?)", test_users)
        c.execute("DELETE FROM whoop_metrics WHERE user_id IN (?, ?)", test_users)
        c.execute("DELETE FROM workouts WHERE user_id IN (?, ?)", test_users)
        c.execute("DELETE FROM settings WHERE user_id IN (?, ?)", test_users)
        conn.commit()
        conn.close()

    def test_prime_window_with_breakthrough_and_green_recovery(self):
        """Green recovery + fresh legs + eFTP breakthrough + stale test -> PRIME_NOW."""
        today = datetime.date.today()
        # Wednesday is 60m+ outdoor_priority day -> should recommend 20m_coggan
        # Use explicit activities showing a 25-min 280W effort (eFTP ~266W vs 250W current)
        activities = [
            {
                "id": "1001",
                "name": "Threshold Breakthrough Ride",
                "sport_type": "VirtualRide",
                "start_date": (today - datetime.timedelta(days=4)).isoformat() + "T08:00:00Z",
                "moving_time_sec": 1800,
                "elapsed_time_sec": 1800,
                "weighted_average_watts": 280,
                "average_watts": 272,
                "suffer_score": 55,
            }
        ]
        # Add enough rides over 28d for consistency
        for i in range(6, 26, 3):
            activities.append({
                "id": f"100{i}",
                "name": "Endurance Base",
                "sport_type": "Ride",
                "start_date": (today - datetime.timedelta(days=i)).isoformat() + "T08:00:00Z",
                "moving_time_sec": 3600,
                "elapsed_time_sec": 3600,
                "weighted_average_watts": 180,
                "average_watts": 175,
                "suffer_score": 45,
            })

        whoop_data = {
            "date": today.isoformat(),
            "recovery_score": 84,
            "hrv_rmssd": 72.0,
            "sleep_performance": 92,
            "day_strain": 0.0,
        }
        program_data = {
            "phase": "Mastery & Benchmark Test",
            "progress_pct": 92,
            "current_week": 8,
            "total_weeks": 8,
            "has_specific_event": False,
            "days_remaining": 4,
        }

        res = evaluate_ftp_test_readiness(
            user_id=self.user_a,
            activities=activities,
            whoop_data=whoop_data,
            program_data=program_data,
        )
        self.assertTrue(res["has_breakthrough"])
        self.assertGreaterEqual(res["estimated_ftp"], 265)
        self.assertGreaterEqual(res["readiness_score"], 75)
        if not res["candidate_windows"][0]["is_rest"]:
            self.assertEqual(res["status"], "PRIME_NOW")
        self.assertIn(res["recommended_protocol"], ("20m_coggan", "ramp_test"))

    def test_defer_on_red_recovery(self):
        """Red Whoop recovery (<34%) should not return PRIME_NOW."""
        today = datetime.date.today()
        whoop_data = {
            "date": today.isoformat(),
            "recovery_score": 25,
            "hrv_rmssd": 30.0,
            "sleep_performance": 60,
            "day_strain": 4.0,
        }
        res = evaluate_ftp_test_readiness(
            user_id=self.user_a,
            activities=[],
            whoop_data=whoop_data,
            program_data={"phase": "Build Phase", "progress_pct": 50, "current_week": 4, "total_weeks": 8},
        )
        self.assertNotEqual(res["status"], "PRIME_NOW")
        self.assertEqual(res["pillars"]["physiological_readiness"]["score"], 0)

    def test_defer_when_tested_recently(self):
        """If tested < 14 days ago without breakthrough, status should be DEFER_RECENT."""
        today = datetime.date.today()
        set_setting("ftp_last_tested_date", (today - datetime.timedelta(days=5)).isoformat(), user_id=self.user_a)
        res = evaluate_ftp_test_readiness(
            user_id=self.user_a,
            activities=[],
            whoop_data={"date": today.isoformat(), "recovery_score": 88, "day_strain": 0.0},
            program_data={"phase": "Build Phase", "progress_pct": 50, "current_week": 4, "total_weeks": 8},
        )
        self.assertEqual(res["status"], "DEFER_RECENT")
        self.assertEqual(res["days_since_last_test"], 5)

    def test_defer_during_event_taper(self):
        """Within 7 days of a target event, FTP testing should be deferred."""
        today = datetime.date.today()
        res = evaluate_ftp_test_readiness(
            user_id=self.user_a,
            activities=[],
            whoop_data={"date": today.isoformat(), "recovery_score": 88, "day_strain": 0.0},
            program_data={
                "phase": "Taper & Freshness",
                "progress_pct": 95,
                "current_week": 8,
                "total_weeks": 8,
                "has_specific_event": True,
                "days_remaining": 4,
                "event_title": "Gran Fondo",
            },
        )
        self.assertEqual(res["status"], "DEFER_EVENT")

    def test_record_ftp_test_result_isolated_per_user(self):
        """Recording an FTP test updates athlete_ftp and ftp_last_tested_date for that user only."""
        res = record_ftp_test_result(new_ftp=272, protocol="20m_coggan", test_date="2026-11-18", user_id=self.user_a)
        self.assertTrue(res["success"])
        self.assertEqual(res["old_ftp"], 250)
        self.assertEqual(res["new_ftp"], 272)
        self.assertEqual(int(get_setting("athlete_ftp", 0, user_id=self.user_a)), 272)
        self.assertEqual(get_setting("ftp_last_tested_date", None, user_id=self.user_a), "2026-11-18")
        # User B remains untouched
        self.assertEqual(int(get_setting("athlete_ftp", 0, user_id=self.user_b)), 300)
        self.assertIsNone(get_setting("ftp_last_tested_date", None, user_id=self.user_b))

    def test_build_ftp_test_workouts_and_ai_coach_note(self):
        """Verify both 20m Coggan and Ramp Test protocols and ai_coach user_note integration."""
        w_coggan = build_ftp_test_workout("20m_coggan", ftp=260)
        self.assertEqual(w_coggan["option_type"], "ftp_test")
        self.assertEqual(w_coggan["duration_minutes"], 55)
        self.assertIn("zwo_content", w_coggan)
        self.assertGreater(w_coggan["total_xss"], 0)

        w_ramp = build_ftp_test_workout("ramp_test", ftp=260)
        self.assertEqual(w_ramp["protocol_type"], "ramp_test")
        self.assertEqual(w_ramp["duration_minutes"], 38)

        set_current_user_context(self.user_a)
        coach_w = build_adaptive_workout_local(
            recovery_score=80,
            hrv_rmssd=65.0,
            sleep_score=88,
            recent_volume_hours=5.0,
            recent_high_intensity=False,
            target_duration_min=55,
            ftp=260,
            user_note="ftp test",
        )
        self.assertEqual(coach_w["option_type"], "ftp_test")
        self.assertIn("FTP Test", coach_w["title"])


if __name__ == "__main__":
    unittest.main()

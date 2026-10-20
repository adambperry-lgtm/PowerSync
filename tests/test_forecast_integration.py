import unittest
import datetime
from app.database import init_db, set_setting, get_setting, set_current_user_context
from app.services.forecast_service import (
    save_coach_forecast_plan,
    get_forecast_for_date,
    is_forecast_valid_for_recovery
)
from app.services.review_coach import build_preference_aligned_outlook_days
from app.services.ai_coach import build_adaptive_workout_local

class TestForecastIntegration(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_a = "user_forecast_test_a"
        self.user_b = "user_forecast_test_b"
        set_current_user_context(self.user_a)

    def test_forecast_persisted_and_retrieved(self):
        """Verify that build_preference_aligned_outlook_days persists forecast with intervals."""
        today = datetime.date(2026, 10, 20)  # Tuesday
        outlook = build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=10.0,
            workout_strain=10.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={"phase": "Build Phase"}
        )
        self.assertEqual(len(outlook), 3)
        
        # Verify Day +1 (Wednesday, Oct 21)
        wed_iso = (today + datetime.timedelta(days=1)).isoformat()
        saved = get_forecast_for_date(wed_iso, user_id=self.user_a)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["date"], wed_iso)
        self.assertEqual(saved["duration_min"], 60)  # Wednesday 60m preference
        self.assertTrue(len(saved["intervals"]) > 0)
        self.assertEqual(saved["title"], outlook[0]["title"])

    def test_forecast_confirmed_when_assumptions_valid(self):
        """When actual morning recovery matches forecast assumptions, workout selector returns the exact forecast."""
        today = datetime.date(2026, 10, 20)
        outlook = build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=10.0,
            workout_strain=10.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={"phase": "Build Phase"}
        )
        wed_iso = (today + datetime.timedelta(days=1)).isoformat()
        saved_forecast = get_forecast_for_date(wed_iso, user_id=self.user_a)
        self.assertIsNotNone(saved_forecast)

        # On Wednesday morning, athlete wakes up with 78% recovery (Green, matches projected ~87%)
        wed_date = today + datetime.timedelta(days=1)
        workout = build_adaptive_workout_local(
            recovery_score=78,
            hrv_rmssd=65.0,
            sleep_score=85,
            recent_volume_hours=5.0,
            recent_high_intensity=False,
            ftp=250,
            target_date=wed_date
        )

        self.assertEqual(workout["title"], saved_forecast["title"])
        self.assertEqual(workout["duration_minutes"], saved_forecast["duration_min"])
        self.assertIn("Forecast Confirmed", workout["badge"])
        self.assertIn("Forecast Confirmed", workout["ai_rationale"])
        self.assertEqual(len(workout["intervals"]), len(saved_forecast["intervals"]))

    def test_forecast_adapts_when_recovery_diverges(self):
        """When actual recovery drops into Red (25%), workout selector adapts away from forecast."""
        today = datetime.date(2026, 10, 20)
        build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=10.0,
            workout_strain=10.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={"phase": "Build Phase"}
        )
        wed_date = today + datetime.timedelta(days=1)

        # Athlete wakes up in the RED at 25% (diverges from projected Green)
        workout = build_adaptive_workout_local(
            recovery_score=25,
            hrv_rmssd=28.0,
            sleep_score=45,
            recent_volume_hours=5.0,
            recent_high_intensity=False,
            ftp=250,
            target_date=wed_date
        )

        self.assertIn("Adapted from Forecast", workout["badge"])
        self.assertIn("Forecast Adapted", workout["ai_rationale"])
        self.assertEqual(workout["focus_area"], "Active Recovery")
        # Must be capped in Zone 1 active recovery
        for interval in workout["intervals"]:
            if "power_pct" in interval:
                self.assertLessEqual(interval["power_pct"], 55)

    def test_user_note_override_takes_precedence(self):
        """Explicit athlete note on the day overrides the confirmed forecast."""
        today = datetime.date(2026, 10, 20)
        build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=10.0,
            workout_strain=10.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={"phase": "Build Phase"}
        )
        wed_date = today + datetime.timedelta(days=1)

        # Athlete explicitly requests VO2 microbursts despite forecast
        workout = build_adaptive_workout_local(
            recovery_score=78,
            hrv_rmssd=65.0,
            sleep_score=85,
            recent_volume_hours=5.0,
            recent_high_intensity=False,
            ftp=250,
            user_note="Want high-cadence 30/30 microbursts",
            target_date=wed_date
        )

        self.assertIn("Microbursts", workout["title"])
        self.assertIn("Adapted to Your Note", workout["badge"])

    def test_generate_workout_endpoint_confirms_forecast(self):
        """Workout /generate endpoint automatically retrieves and confirms forecast for target_date."""
        from app.routers.workouts import generate_workout, WorkoutGenerateRequest
        today = datetime.date(2026, 10, 20)
        build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=10.0,
            workout_strain=10.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={"phase": "Build Phase"}
        )
        wed_iso = (today + datetime.timedelta(days=1)).isoformat()
        saved_forecast = get_forecast_for_date(wed_iso, user_id=self.user_a)
        self.assertIsNotNone(saved_forecast)

        res = generate_workout(WorkoutGenerateRequest(target_date=wed_iso))
        primary = res.get("active_workout", {})
        self.assertEqual(primary.get("title"), saved_forecast["title"])
        self.assertEqual(primary.get("duration_minutes"), saved_forecast["duration_min"])
        self.assertIn("Forecast Confirmed", primary.get("badge", ""))

    def test_forecast_diversity_across_wednesday_and_friday(self):
        """Forecast produces distinct, diverse archetypes for Wednesday and Friday."""
        today = datetime.date(2026, 10, 20)  # Tuesday
        outlook = build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=10.0,
            workout_strain=10.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={"phase": "Build Phase"}
        )
        wed_title = outlook[0]["title"]
        fri_title = outlook[2]["title"]
        self.assertNotEqual(wed_title, fri_title, f"Wednesday ({wed_title}) and Friday ({fri_title}) should not be identical")

    def test_completed_workout_today_not_overwritten_by_scheduled_target(self):
        """When an athlete completes a workout today, Today's Training marks target achieved and is not overwritten by scheduled target."""
        from app.routers.workouts import generate_workout, WorkoutGenerateRequest
        from app.database import save_scheduled_workout, get_db_connection

        today_iso = datetime.date.today().isoformat()
        # 1. Workout was previously scheduled
        save_scheduled_workout({
            "title": "45-Min Sweet Spot Over-Unders",
            "duration_minutes": 45,
            "estimated_tss": 48,
            "intervals": []
        }, today_iso, user_id=self.user_a)

        # 2. Athlete completed the ride on Strava today
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO strava_activities (user_id, id, name, sport_type, start_date, moving_time_sec, suffer_score, weighted_average_watts)
            VALUES (?, 'test_act_done_today', 'Zwift - Intervals icu: PowerSync: 45-Min Sweet Spot Over-Unders', 'Ride', ?, 2750, 48, 222)
        """, (self.user_a, f"{today_iso}T10:10:00Z"))
        conn.commit()
        conn.close()

        # 3. Requesting today's workout
        res = generate_workout(WorkoutGenerateRequest())
        active = res.get("active_workout", {})
        self.assertIn("Daily Target Achieved", active.get("title", ""))
        self.assertEqual(active.get("option_type"), "recovery")
        self.assertIn("Strain Met", active.get("badge", ""))

    def test_multi_user_forecast_isolation(self):
        """User A's forecast plan is strictly isolated from User B's."""
        set_current_user_context(self.user_a)
        save_coach_forecast_plan(self.user_a, [{
            "date_iso": "2026-10-21",
            "title": "User A 60m Over-Unders",
            "duration_min": 60,
            "projected_recovery": 80,
            "intervals": []
        }])

        set_current_user_context(self.user_b)
        plan_b = get_forecast_for_date("2026-10-21", user_id=self.user_b)
        self.assertIsNone(plan_b)

        plan_a = get_forecast_for_date("2026-10-21", user_id=self.user_a)
        self.assertIsNotNone(plan_a)
        self.assertEqual(plan_a["title"], "User A 60m Over-Unders")

if __name__ == "__main__":
    unittest.main()

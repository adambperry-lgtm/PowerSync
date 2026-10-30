import unittest
import datetime
from app.database import (
    get_db_connection,
    init_db,
    set_setting,
    get_athlete_date,
    set_current_user_context,
    reset_current_user_context
)
from app.services.forecast_service import (
    parse_chat_schedule_directives,
    save_athlete_planned_session,
    get_athlete_planned_sessions,
    clear_athlete_planned_session
)
from app.services.review_coach import (
    build_preference_aligned_outlook_days
)
from app.services.coach_chat_service import handle_coach_chat
from app.services.ai_coach import build_adaptive_workout_local

class TestMultiDayChatPlans(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_multiday_test"
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (id, email, name, picture)
            VALUES (?, 'multiday_test@powersync.local', 'MultiDay Athlete', '')
        """, (self.user_id,))
        conn.commit()
        conn.close()

        self.ctx_token = set_current_user_context(self.user_id)
        set_setting("athlete_ftp", 250, user_id=self.user_id)
        set_setting("athlete_timezone", "America/New_York", user_id=self.user_id)
        clear_athlete_planned_session(user_id=self.user_id)

    def tearDown(self):
        clear_athlete_planned_session(user_id=self.user_id)
        reset_current_user_context(self.ctx_token)

    def test_parse_multi_day_schedule_directives_with_complaint_clause(self):
        """Verifies multi-day extraction with complaint stripping."""
        # Assume today is a Friday
        today = datetime.date(2026, 10, 30) # Friday
        user_msg = "i said i was doing 50 miles tomorrow and resting sunday, but it still has rest tomorrow and a long ride on sunday"

        directives = parse_chat_schedule_directives(user_msg, today=today)
        self.assertEqual(len(directives), 2)

        sat_plan = next((d for d in directives if d["target_date"] == "2026-10-31"), None)
        sun_plan = next((d for d in directives if d["target_date"] == "2026-11-01"), None)

        self.assertIsNotNone(sat_plan, "Saturday (tomorrow) plan must be extracted")
        self.assertIsNotNone(sun_plan, "Sunday plan must be extracted")

        self.assertFalse(sat_plan["is_rest"])
        self.assertEqual(sat_plan["distance_miles"], 50.0)
        self.assertGreater(sat_plan["duration_min"], 100)
        self.assertEqual(sat_plan["focus_area"], "Endurance")

        self.assertTrue(sun_plan["is_rest"])
        self.assertEqual(sun_plan["duration_min"], 0)
        self.assertEqual(sun_plan["focus_area"], "Rest & Recovery")

    def test_forecast_outlook_reflects_both_weekend_days(self):
        """Verifies that Saturday gets 50-mile ride and Sunday gets rest in 3-day forecast."""
        today = datetime.date(2026, 10, 30) # Friday
        sat_iso = "2026-10-31"
        sun_iso = "2026-11-01"

        # Save both days
        save_athlete_planned_session(sat_iso, {
            "title": "50-Mile Saturday Ride",
            "duration_min": 171,
            "duration_minutes": 171,
            "distance_miles": 50.0,
            "estimated_tss": 105,
            "focus_area": "Endurance",
            "focus_duration": "Endurance / Century (>1h Focus)",
            "is_rest": False,
            "description": "Planned 50-mile Saturday endurance ride"
        }, user_id=self.user_id)

        save_athlete_planned_session(sun_iso, {
            "title": "Rest & Recovery",
            "duration_min": 0,
            "duration_minutes": 0,
            "distance_miles": 0.0,
            "estimated_tss": 0,
            "focus_area": "Rest & Recovery",
            "focus_duration": "Rest & Recovery",
            "is_rest": True,
            "description": "Scheduled rest day for Sunday"
        }, user_id=self.user_id)

        outlook = build_preference_aligned_outlook_days(
            today=today,
            today_recovery=75,
            today_strain=5.0,
            workout_strain=5.0,
            is_today=False,
            is_yesterday=False,
            has_trained_today=False,
            session_summary={},
            ftp=250,
            program={}
        )

        self.assertEqual(len(outlook), 3)

        sat_card = outlook[0] # Tomorrow
        sun_card = outlook[1] # Day +2

        self.assertEqual(sat_card["target_date"], sat_iso)
        self.assertIn("50-Mile", sat_card["title"])
        self.assertEqual(sat_card["duration_min"], 171)
        self.assertFalse(sat_card["is_default_rest"])
        self.assertTrue(sat_card["is_coach_scheduled"])

        self.assertEqual(sun_card["target_date"], sun_iso)
        self.assertEqual(sun_card["duration_min"], 0)
        self.assertTrue(sun_card["is_default_rest"])
        self.assertTrue(sun_card["is_coach_scheduled"])

    def test_friday_workout_protected_from_taper_hijacking(self):
        """Verifies today's (Friday) workout is preserved and not overwritten with a T-1 taper primer."""
        today = datetime.date(2026, 10, 30) # Friday

        # Stage Saturday 50 miles
        save_athlete_planned_session("2026-10-31", {
            "title": "50-Mile Saturday Ride",
            "duration_min": 171,
            "distance_miles": 50.0,
            "is_rest": False
        }, user_id=self.user_id)

        workout = build_adaptive_workout_local(
            recovery_score=78,
            hrv_rmssd=45.0,
            sleep_score=85,
            recent_volume_hours=6.5,
            recent_high_intensity=False,
            target_duration_min=60,
            ftp=250,
            user_note="",
            today_strain=0.0,
            today_activities=[],
            target_date=today
        )

        self.assertNotIn("Pre-Event Neuromuscular Primer", workout["title"])
        self.assertGreaterEqual(workout["duration_minutes"], 50)
        self.assertNotEqual(workout["option_type"], "rest")

if __name__ == "__main__":
    unittest.main()

import unittest
import datetime
from app.database import (
    get_db_connection,
    init_db,
    set_setting,
    get_setting,
    get_athlete_date,
    set_current_user_context,
    reset_current_user_context
)
from app.services.forecast_service import (
    save_athlete_planned_session,
    get_athlete_planned_sessions,
    clear_athlete_planned_session
)
from app.services.review_coach import (
    build_preference_aligned_outlook_days,
    generate_ai_review_and_outlook
)
from app.services.coach_chat_service import handle_coach_chat

class TestChatPlansAdjustForecast(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_chat_plan_test"
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (id, email, name, picture)
            VALUES (?, 'plan_test@powersync.local', 'Planning Athlete', '')
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

    def test_save_and_retrieve_planned_session(self):
        """Verifies saving planned session keyed by ISO date in forecast service."""
        today = get_athlete_date(self.user_id)
        target_date = (today + datetime.timedelta(days=1)).isoformat()

        plan_data = {
            "title": "45-Min Threshold Over-Unders",
            "duration_minutes": 45,
            "estimated_tss": 55,
            "estimated_xss": 58,
            "focus_area": "Threshold",
            "description": "45m over-unders planned in chat"
        }
        save_athlete_planned_session(target_date, plan_data, user_id=self.user_id)

        saved = get_athlete_planned_sessions(user_id=self.user_id)
        self.assertIn(target_date, saved)
        self.assertEqual(saved[target_date]["title"], "45-Min Threshold Over-Unders")
        self.assertEqual(saved[target_date]["duration_min"], 45)
        self.assertEqual(saved[target_date]["estimated_tss"], 55)

    def test_forecast_outlook_adjusts_for_chat_planned_session(self):
        """
        Verifies that when a planned session is staged in Coach Chat,
        build_preference_aligned_outlook_days adjusts the 3-day forecast card.
        """
        today = get_athlete_date(self.user_id)
        tomorrow = today + datetime.timedelta(days=1)
        tomorrow_iso = tomorrow.isoformat()

        # Stage a planned session for tomorrow
        plan_data = {
            "title": "45-Min Threshold Over-Unders",
            "duration_minutes": 45,
            "estimated_tss": 60,
            "estimated_xss": 62,
            "focus_area": "Threshold",
            "focus_duration": "Threshold (20:00 Focus)",
            "description": "Sharp 45m threshold over-under ladders",
            "intervals": [
                {"type": "Warmup", "duration_sec": 360, "power_low_pct": 45, "power_high_pct": 75, "cadence": 88, "name": "Ramp Up"},
                {"type": "SteadyState", "duration_sec": 1980, "power_pct": 98, "cadence": 92, "name": "Over-Under Block"},
                {"type": "Cooldown", "duration_sec": 360, "power_low_pct": 65, "power_high_pct": 40, "cadence": 82, "name": "Ramp Down"}
            ]
        }
        save_athlete_planned_session(tomorrow_iso, plan_data, user_id=self.user_id)

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
            program={"phase": "Build Phase"}
        )

        self.assertEqual(len(outlook), 3)
        day1 = outlook[0]  # Tomorrow
        self.assertEqual(day1["target_date"], tomorrow_iso)
        self.assertEqual(day1["title"], "45-Min Threshold Over-Unders")
        self.assertEqual(day1["duration_min"], 45)
        self.assertEqual(day1["estimated_tss"], 60)
        self.assertTrue(day1.get("is_coach_scheduled"))
        self.assertIn("Planned in Coach Chat", day1.get("description", ""))

    def test_forecast_outlook_adjusts_for_rest_day_plan(self):
        """Verifies that planning a rest day in chat sets duration to 0 and focus to Rest & Recovery."""
        today = get_athlete_date(self.user_id)
        day2 = today + datetime.timedelta(days=2)
        day2_iso = day2.isoformat()

        plan_data = {
            "title": "Full Rest Day",
            "is_rest": True,
            "description": "Taking the day off to prioritize deep recovery"
        }
        save_athlete_planned_session(day2_iso, plan_data, user_id=self.user_id)

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
            program={"phase": "Build Phase"}
        )

        day2_card = outlook[1]  # Day +2
        self.assertEqual(day2_card["target_date"], day2_iso)
        self.assertEqual(day2_card["duration_min"], 0)
        self.assertEqual(day2_card["estimated_tss"], 0)
        self.assertEqual(day2_card["focus"], "Rest & Recovery")
        self.assertTrue(day2_card.get("is_coach_scheduled"))

    def test_coach_chat_automatically_stages_planned_workout(self):
        """
        Verifies that when athlete asks coach in chat to schedule upcoming session,
        handle_coach_chat automatically stages it into coach_upcoming_plans.
        """
        msg = "Schedule 45m threshold over-unders tomorrow"
        res = handle_coach_chat(msg, history=[])
        self.assertTrue(res.get("success"))

        saved_plans = get_athlete_planned_sessions(user_id=self.user_id)
        today = get_athlete_date(self.user_id)
        tomorrow_iso = (today + datetime.timedelta(days=1)).isoformat()

        self.assertIn(tomorrow_iso, saved_plans)
        staged = saved_plans[tomorrow_iso]
        self.assertIn("Over-Under", staged["title"])
        self.assertEqual(staged["duration_min"], 45)

if __name__ == "__main__":
    unittest.main()

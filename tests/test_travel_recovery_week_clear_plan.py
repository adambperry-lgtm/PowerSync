import unittest
from unittest.mock import patch
import datetime
from app.services.coach_chat_service import (
    build_sports_science_action,
    generate_sports_science_fallback_response
)
from app.routers.chat import apply_chat_action_endpoint, ApplyChatActionPayload
from app.database import get_setting, set_setting, set_current_user_context
from app.services.program_service import get_current_program
from app.services.review_coach import build_preference_aligned_outlook_days

class TestTravelRecoveryWeekClearPlan(unittest.TestCase):
    def setUp(self):
        self.user_id = "test_user_travel"
        set_current_user_context(self.user_id)
        set_setting("travel_recovery_week_active", False, user_id=self.user_id)

    def tearDown(self):
        set_setting("travel_recovery_week_active", False, user_id=self.user_id)

    def test_intent_detection_with_typos(self):
        msg = "this week is a rest and recoveyr travel week with some light cross-trainig and that i wanrted to clear my plan and would start something new next week"
        snapshot = {"athlete": {"ftp_watts": 260}}
        action = build_sports_science_action(msg, snapshot)
        self.assertIsNotNone(action)
        self.assertEqual(action.get("action_type"), "clear_upcoming_plan")
        self.assertTrue(action.get("is_recovery_week"))
        self.assertIn("Travel / Recovery", action.get("title", ""))

    def test_fallback_response_empathy(self):
        msg = "this week was a rest and recoveyr travel week with some light cross-trainig and clear my plan"
        snapshot = {
            "athlete": {"ftp_watts": 260},
            "whoop_readiness_today": {
                "recovery_score_pct": 72,
                "recovery_zone": "green",
                "hrv_rmssd_ms": 55.0,
                "day_strain_today": 4.5
            },
            "today_prescribed_workout": {
                "title": "Threshold Steps",
                "duration_minutes": 45,
                "estimated_tss": 55
            },
            "training_load_strava": {"recent_rides": []}
        }
        fallback = generate_sports_science_fallback_response(msg, snapshot)
        self.assertIn("Travel & Rest/Recovery Week", fallback)
        self.assertIn("cross-training", fallback)
        self.assertIn("completely cleared", fallback)

    def test_apply_chat_action_endpoint_activates_recovery_week(self):
        payload = ApplyChatActionPayload(
            action_type="clear_upcoming_plan",
            action_data={
                "action_type": "clear_upcoming_plan",
                "is_recovery_week": True,
                "title": "Clear Plan & Activate Travel / Recovery Week"
            }
        )
        res = apply_chat_action_endpoint(payload)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("action_type"), "clear_upcoming_plan")
        self.assertTrue(res.get("is_recovery_week"))

        # Verify DB setting
        is_active = get_setting("travel_recovery_week_active", False, user_id=self.user_id)
        self.assertTrue(is_active)

        # Verify today's active workout is Rest & Mobility
        active_w = res.get("active_workout")
        self.assertIsNotNone(active_w)
        self.assertEqual(active_w.get("duration_minutes"), 0)
        self.assertIn("Travel Week", active_w.get("title", ""))
        self.assertEqual(active_w.get("badge"), "🧘 Travel & Recovery Week")

        # Verify options include 30-min cross-training
        opts = res.get("options", [])
        opt_titles = [o.get("title") for o in opts]
        self.assertTrue(any("Cross-Training" in t for t in opt_titles))

        # Verify program reflects Travel & Recovery Week
        prog = res.get("program") or get_current_program(user_id=self.user_id)
        self.assertEqual(prog.get("phase"), "Recovery & Travel Week")
        self.assertIn("Cross-Training", prog.get("phase_focus", ""))

        # Verify forecast reflects recovery days
        forecast = res.get("forecast", [])
        self.assertGreaterEqual(len(forecast), 1)
        f_titles = [f.get("title") for f in forecast]
        self.assertTrue(any("Cross-Training" in t or "Recovery" in t for t in f_titles))

    def test_cancel_the_plan_short_phrase_intent(self):
        snapshot = {"athlete": {"ftp_watts": 260}}
        for phrase in [
            "cancel the plan",
            "cancel my plan",
            "cancel plan",
            "clear the plan",
            "i cancelled the plan in the chat again and it is still there on the app",
            "cancel it",
            "cancel"
        ]:
            action = build_sports_science_action(phrase, snapshot)
            self.assertIsNotNone(action, f"Failed for phrase: {phrase}")
            self.assertEqual(action.get("action_type"), "clear_upcoming_plan")
            self.assertTrue(action.get("is_recovery_week"))

    def test_handle_coach_chat_auto_applies_clear_plan(self):
        from app.services.coach_chat_service import handle_coach_chat
        res = handle_coach_chat("cancel my plan", [])
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("cleared_plan"))
        self.assertTrue(get_setting("travel_recovery_week_active", False, user_id=self.user_id))

        # Check active workout returned is rest/recovery
        w = res.get("active_workout")
        self.assertIsNotNone(w)
        self.assertEqual(w.get("duration_minutes"), 0)
        self.assertEqual(w.get("badge"), "🧘 Travel & Recovery Week")

        # Check program is Recovery & Travel Week
        prog = res.get("program")
        self.assertIsNotNone(prog)
        self.assertEqual(prog.get("phase"), "Recovery & Travel Week")

    def test_clear_plans_endpoint_calls_execute_clear_plan(self):
        from app.routers.plans import clear_active_plan
        res = clear_active_plan()
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("plan_cleared"))
        self.assertTrue(get_setting("travel_recovery_week_active", False, user_id=self.user_id))
        self.assertEqual(res.get("active_workout", {}).get("duration_minutes"), 0)

if __name__ == "__main__":
    unittest.main()

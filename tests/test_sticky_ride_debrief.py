import unittest
import datetime
import json
from unittest.mock import patch
from app.database import (
    init_db,
    set_setting,
    set_current_user_context,
    get_db_connection,
    get_athlete_date,
)
from app.services.review_coach import generate_ai_review_and_outlook


class TestStickyRideDebrief(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_a = "test_sticky_debrief_a"
        self.user_b = "test_sticky_debrief_b"
        self._cleanup(self.user_a)
        self._cleanup(self.user_b)
        set_current_user_context(self.user_a)

    def tearDown(self):
        self._cleanup(self.user_a)
        self._cleanup(self.user_b)

    def _cleanup(self, uid):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()

    def _insert_activity(self, uid, act_id, name, start_iso, moving_sec=3600, watts=220):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts,
                weighted_average_watts, average_heartrate, max_heartrate,
                suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid, act_id, name, "Ride", start_iso, moving_sec,
                30000.0, 250.0, watts - 10, watts, 145.0, 172.0,
                65, 750.0, json.dumps({"id": act_id, "start_date_local": start_iso})
            ),
        )
        conn.commit()
        conn.close()

    def test_debrief_is_sticky_on_reload_and_invalidates_on_new_activity_or_force_refresh(self):
        set_setting("strava_tokens", {"access_token": "tok"}, user_id=self.user_a)
        set_setting("gemini_api_key", "fake-gemini-key", user_id=self.user_a)

        today_iso = get_athlete_date(self.user_a).isoformat()
        self._insert_activity(self.user_a, 1001, "Morning Tempo", f"{today_iso}T08:00:00")

        with patch("app.services.review_coach.call_gemini_coach_review") as mock_gemini:
            mock_gemini.return_value = {
                "insights": "Solid morning tempo ride with controlled aerobic drift and strong pacing.",
                "tomorrow_guidance": "Keep tomorrow easy Zone 2."
            }

            # 1. First load: analyzes ride via Gemini and caches result
            res1 = generate_ai_review_and_outlook()
            self.assertEqual(mock_gemini.call_count, 1)
            self.assertTrue(res1["today_assessment"]["is_today"])
            self.assertEqual(res1["today_assessment"]["title"], "Morning Tempo")
            self.assertIn("Solid morning tempo ride", res1["today_assessment"]["assessment_text"])

            # 2. Reload tab (second call, same day, same activity): sticky cache hit, no Gemini call
            res2 = generate_ai_review_and_outlook()
            self.assertEqual(mock_gemini.call_count, 1)
            self.assertEqual(res2["today_assessment"]["title"], "Morning Tempo")
            self.assertEqual(
                res2["today_assessment"]["assessment_text"],
                res1["today_assessment"]["assessment_text"],
            )

            # 3. Sync another activity today: invalidates cache and re-analyzes collectively
            self._insert_activity(self.user_a, 1002, "Evening Cooldown", f"{today_iso}T17:30:00", moving_sec=1200, watts=140)
            mock_gemini.return_value = {
                "insights": "Two-session day combining Morning Tempo and Evening Cooldown.",
                "tomorrow_guidance": "Prioritize sleep tonight."
            }
            res3 = generate_ai_review_and_outlook()
            self.assertEqual(mock_gemini.call_count, 2)
            self.assertEqual(len(res3["today_assessment"]["sessions"]), 2)
            self.assertIn("Two-session day", res3["today_assessment"]["assessment_text"])

            # 4. Reload tab again after second ride: sticky cache hit again
            res4 = generate_ai_review_and_outlook()
            self.assertEqual(mock_gemini.call_count, 2)
            self.assertEqual(len(res4["today_assessment"]["sessions"]), 2)

            # 5. Explicit regenerate (force_refresh=True): re-analyzes even with same activities
            mock_gemini.return_value = {
                "insights": "Regenerated debrief with fresh coach perspective.",
                "tomorrow_guidance": "Active recovery spin."
            }
            res5 = generate_ai_review_and_outlook(force_refresh=True)
            self.assertEqual(mock_gemini.call_count, 3)
            self.assertIn("Regenerated debrief", res5["today_assessment"]["assessment_text"])

    def test_debrief_cache_is_isolated_per_user_and_date(self):
        set_setting("strava_tokens", {"access_token": "tok_a"}, user_id=self.user_a)
        set_setting("strava_tokens", {"access_token": "tok_b"}, user_id=self.user_b)
        today = get_athlete_date(self.user_a)
        today_iso = today.isoformat()

        self._insert_activity(self.user_a, 2001, "User A Ride", f"{today_iso}T09:00:00")
        self._insert_activity(self.user_b, 3001, "User B Ride", f"{today_iso}T09:00:00")

        set_current_user_context(self.user_a)
        res_a = generate_ai_review_and_outlook()
        self.assertEqual(res_a["today_assessment"]["title"], "User A Ride")

        set_current_user_context(self.user_b)
        res_b = generate_ai_review_and_outlook()
        self.assertEqual(res_b["today_assessment"]["title"], "User B Ride")

        # Next day should miss cache for user A
        tomorrow = today + datetime.timedelta(days=1)
        set_current_user_context(self.user_a)
        with patch("app.services.review_coach.get_athlete_date", return_value=tomorrow):
            res_next_day = generate_ai_review_and_outlook()
            self.assertFalse(res_next_day["today_assessment"]["is_today"])


if __name__ == "__main__":
    unittest.main()

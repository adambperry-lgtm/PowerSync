import unittest
import datetime
import json
from unittest.mock import patch
from app.database import init_db, set_setting, set_current_user_context, get_db_connection, get_athlete_date
from app.services.review_coach import (
    build_daily_review_and_outlook_local,
    call_gemini_coach_review,
    generate_ai_review_and_outlook
)

class TestDebriefTimelineAccuracy(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "test_timeline_athlete"
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

    def test_past_workout_not_labeled_as_yesterday(self):
        """
        Verify that a workout completed 6 days ago (e.g., trail run / family hike)
        is accurately marked with its relative date and date_display, and never
        referred to as 'yesterday' in the assessment text or prompt context.
        """
        today = get_athlete_date()
        six_days_ago = today - datetime.timedelta(days=6)
        six_days_iso = six_days_ago.isoformat()

        trail_run = {
            "id": 8801,
            "name": "Mountain Trail Run",
            "start_date": f"{six_days_iso}T07:30:00Z",
            "moving_time_sec": 3600,
            "distance_meters": 12000.0,
            "total_elevation_gain": 400,
            "average_watts": 230.0,
            "weighted_average_watts": 230.0,
            "average_heartrate": 160.0,
            "suffer_score": 65,
            "kilojoules": 800.0,
            "raw_json": json.dumps({"start_date_local": f"{six_days_iso}T07:30:00"})
        }

        family_hike = {
            "id": 8802,
            "name": "Final Utah Family Hike",
            "start_date": f"{six_days_iso}T14:00:00Z",
            "moving_time_sec": 4200,
            "distance_meters": 6000.0,
            "total_elevation_gain": 200,
            "average_watts": 100.0,
            "weighted_average_watts": 105.0,
            "average_heartrate": 105.0,
            "suffer_score": 20,
            "kilojoules": 400.0,
            "raw_json": json.dumps({"start_date_local": f"{six_days_iso}T14:00:00"})
        }

        whoop_data = {
            "recovery_score": 71,
            "hrv_rmssd": 52.0,
            "day_strain": 3.2,
            "sleep_performance": 88,
            "sleep_needed_hours": 7.8
        }
        trailing_strava = {"acute_weighted_tss": 120, "total_tss": 120}
        program = {"goal_title": "Base Building", "phase": "Base", "target_ftp": 265}

        review = build_daily_review_and_outlook_local(
            whoop_data=whoop_data,
            trailing_strava=trailing_strava,
            today_acts=[],
            latest_act=family_hike,
            program=program,
            ftp=250,
            day_acts=[trail_run, family_hike]
        )

        sess = review["today_assessment"]
        self.assertFalse(sess["is_today"])
        self.assertFalse(sess["is_yesterday"])
        self.assertEqual(sess["relative_day_label"], "6 Days Ago")
        self.assertIn(six_days_ago.strftime("%A"), sess["date_display"])
        self.assertEqual(sess["date"], six_days_iso)

        # Assessment text must not contain 'yesterday'
        self.assertNotIn("yesterday", sess["assessment_text"].lower())
        self.assertIn("6 days ago", sess["assessment_text"].lower())

    def test_gemini_prompt_temporal_context_for_older_session(self):
        """
        Verify that call_gemini_coach_review instructs Gemini that the session occurred on the
        past date and forbids calling it 'yesterday'.
        """
        today = get_athlete_date()
        five_days_ago = today - datetime.timedelta(days=5)
        five_days_iso = five_days_ago.isoformat()
        date_display = five_days_ago.strftime("%A, %b ") + str(five_days_ago.day)

        review_data = {
            "today_assessment": {
                "title": "Weekend Long Ride",
                "is_today": False,
                "is_yesterday": False,
                "date": five_days_iso,
                "date_display": date_display,
                "relative_day_label": "5 Days Ago",
                "workout_recovery": 55,
                "workout_strain": 14.5,
                "today_recovery": 80,
                "today_strain": 1.5,
                "moving_time_formatted": "2h 15m",
                "weighted_watts": 200,
                "pct_ftp": 80,
                "calculated_tss": 110,
                "total_xss": 115,
                "low_strain_xss": 90,
                "high_strain_xss": 25,
                "peak_strain_xss": 0,
                "battery_depleted_pct": 10,
                "focus_duration": "Endurance",
                "target_zone": "Zone 2 Aerobic Base",
                "target_watts": 170,
                "target_pct_ftp": 68,
                "verdict": "Intensity Overreach",
                "compliance_score": 75,
                "sessions": []
            },
            "macrocycle_context": {"current_ftp": 250},
            "outlook_days": [{"title": "Recovery Spin", "estimated_xss": 25, "focus": "Zone 1"}]
        }

        # Mock requests.post to capture the prompt payload sent to Gemini
        captured_payloads = []
        def mock_post(url, json=None, headers=None, timeout=None):
            captured_payloads.append(json)
            class MockResponse:
                status_code = 200
                def json(self):
                    return {
                        "candidates": [{
                            "content": {
                                "parts": [{
                                    "text": '{"insights": "Yesterday was an overreach.", "tomorrow_guidance": "Rest well."}'
                                }]
                            }
                        }]
                    }
            return MockResponse()

        with patch("requests.post", side_effect=mock_post):
            result = call_gemini_coach_review("mock_key", review_data, {"recovery_score": 80})

        self.assertIsNotNone(result)
        self.assertTrue(len(captured_payloads) > 0)
        sent_prompt = captured_payloads[0]["contents"][0]["parts"][0]["text"]

        # Ensure prompt contains strict timeline instructions
        self.assertIn("CRITICAL TIMELINE NOTICE", sent_prompt)
        self.assertIn("5 Days Ago", sent_prompt)
        self.assertIn("NOT yesterday and NOT today", sent_prompt)
        self.assertIn("MUST NOT refer to this session as 'yesterday'", sent_prompt)

    def test_gemini_response_timeline_sanitization(self):
        """
        Verify that if Gemini hallucinates 'Yesterday was' for an older session,
        defense-in-depth sanitizes it to reference the actual session date.
        """
        today = get_athlete_date()
        six_days_ago = today - datetime.timedelta(days=6)
        six_days_iso = six_days_ago.isoformat()

        activity = {
            "id": 9901,
            "name": "Trail Run",
            "start_date": f"{six_days_iso}T08:00:00Z",
            "moving_time_sec": 3600,
            "distance_meters": 10000.0,
            "total_elevation_gain": 300,
            "average_watts": 230.0,
            "weighted_average_watts": 230.0,
            "average_heartrate": 155.0,
            "suffer_score": 60,
            "kilojoules": 750.0,
            "raw_json": json.dumps({"start_date_local": f"{six_days_iso}T08:00:00"})
        }

        # Insert activity into DB
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts,
                weighted_average_watts, average_heartrate, max_heartrate,
                suffer_score, kilojoules, raw_json
            ) VALUES (?, '9901', 'Trail Run', 'Run', ?, 3600, 10000, 300, 230, 230, 155, 175, 60, 750, ?)
        """, (self.user_id, f"{six_days_iso}T08:00:00", json.dumps(activity)))
        conn.commit()
        conn.close()

        set_setting("strava_tokens", json.dumps({"access_token": "mock"}), user_id=self.user_id)
        set_setting("gemini_api_key", "test_gemini_key", user_id=self.user_id)

        mock_gemini_text = (
            '{"insights": "Yesterday was a significant intensity overreach. The primary trail run exceeded '
            'prescribed targets while contributing to your 71% recovery today.", '
            '"tomorrow_guidance": "Focus on low-intensity flush."}'
        )

        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": mock_gemini_text}]}}]
            }
            review = generate_ai_review_and_outlook()

        sess = review["today_assessment"]
        self.assertFalse(sess["is_today"])
        self.assertFalse(sess["is_yesterday"])

        # The hallucinated 'Yesterday was' MUST be replaced
        self.assertNotIn("Yesterday was", sess["assessment_text"])
        self.assertIn("6 days ago", sess["assessment_text"].lower())

if __name__ == "__main__":
    unittest.main()

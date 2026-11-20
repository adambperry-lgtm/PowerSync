import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app.database import (
    get_athlete_date,
    get_db_connection,
    init_db,
    set_current_user_context,
    set_setting,
)
from app.services.review_coach import (
    DEBRIEF_CACHE_VERSION,
    build_daily_review_and_outlook_local,
    call_gemini_coach_review,
    generate_ai_review_and_outlook,
)


class TestDebriefNormalizedPowerLabels(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "test_debrief_np_labels"
        self._cleanup(self.user_id)
        set_current_user_context(self.user_id)

    def tearDown(self):
        self._cleanup(self.user_id)

    def _cleanup(self, uid):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM whoop_metrics WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()

    def test_local_debrief_uses_np_instead_of_avg_power(self):
        today_iso = get_athlete_date(self.user_id).isoformat()
        act = {
            "id": 9001,
            "name": "Zone 2 Endurance",
            "sport_type": "Ride",
            "start_date": f"{today_iso}T09:00:00",
            "moving_time_sec": 3600,
            "distance_meters": 32000.0,
            "total_elevation_gain": 250.0,
            "average_watts": 162.0,
            "weighted_average_watts": 175.0,
            "average_heartrate": 136.0,
            "suffer_score": 52,
        }
        review = build_daily_review_and_outlook_local(
            whoop_data={"recovery_score": 55, "strain": 9.5},
            trailing_strava={"weekly_tss": 180},
            today_acts=[act],
            latest_act=act,
            program={"goal_title": "FTP Build", "phase": "Base", "weekly_tss_target": 360},
            ftp=250,
            day_acts=[act],
        )
        sess = review["today_assessment"]
        self.assertEqual(sess["weighted_watts"], 175)
        self.assertIn("175W NP", sess["assessment_text"])
        self.assertNotIn("175W avg", sess["assessment_text"])

    def test_gemini_prompt_explicitly_labels_np_and_forbids_avg_power(self):
        captured_prompts = []

        def fake_post(url, json=None, timeout=20):
            captured_prompts.append(json["contents"][0]["parts"][0]["text"])
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"insights": "Strong 195W NP execution.", "tomorrow_guidance": "Easy Zone 2."}'
                                }
                            ]
                        }
                    }
                ]
            }
            return resp

        review_data = {
            "macrocycle_context": {"current_ftp": 260},
            "today_assessment": {
                "title": "Tempo Cruise",
                "is_today": True,
                "is_yesterday": False,
                "date": "2026-11-20",
                "date_display": "Today",
                "relative_day_label": "Today",
                "moving_time_formatted": "1h 0m",
                "weighted_watts": 195,
                "pct_ftp": 75,
                "calculated_tss": 56,
                "total_xss": 55.0,
                "low_strain_xss": 50.0,
                "high_strain_xss": 5.0,
                "peak_strain_xss": 0.0,
                "battery_depleted_pct": 12.0,
                "focus_duration": "Endurance",
                "target_zone": "Zone 2 Aerobic Base",
                "target_watts": 190,
                "target_pct_ftp": 73,
                "prescribed_workout_title": "Aerobic Base",
                "verdict": "Target Mastered",
                "compliance_score": 96,
                "workout_recovery": 78,
                "workout_strain": 10.2,
                "today_recovery": 78,
                "today_strain": 10.2,
                "sessions": [
                    {
                        "name": "Tempo Cruise",
                        "is_primary": True,
                        "moving_time_formatted": "1h 0m",
                        "weighted_watts": 195,
                        "pct_ftp": 75,
                        "avg_hr": 140,
                        "tss": 56,
                    }
                ],
            },
            "outlook_days": [
                {
                    "title": "Recovery Spin",
                    "estimated_xss": 30,
                    "focus_duration": "Endurance",
                    "focus": "Zone 1-2",
                }
            ],
        }

        with patch("requests.post", side_effect=fake_post):
            res = call_gemini_coach_review("fake-key", review_data, {"recovery_score": 78, "strain": 10.2})

        self.assertIsNotNone(res)
        self.assertEqual(len(captured_prompts), 1)
        prompt = captured_prompts[0]
        self.assertIn("195W NP (75% FTP)", prompt)
        self.assertIn("190W NP, 73% FTP", prompt)
        self.assertIn("NEVER as 'average power'", prompt)

    def test_stale_debrief_cache_without_version_refreshes(self):
        set_setting("strava_tokens", {"access_token": "tok"}, user_id=self.user_id)
        today_iso = get_athlete_date(self.user_id).isoformat()

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
                self.user_id,
                9101,
                "Morning Spin",
                "Ride",
                f"{today_iso}T08:00:00",
                3600,
                30000.0,
                200.0,
                165.0,
                180.0,
                135.0,
                160.0,
                50,
                600.0,
                json.dumps({"id": 9101, "start_date_local": f"{today_iso}T08:00:00"}),
            ),
        )
        conn.commit()
        conn.close()

        # Seed a legacy v1 cache entry without DEBRIEF_CACHE_VERSION containing old 'avg' wording
        set_setting(
            "cached_daily_debrief",
            {
                "signature": f"{today_iso}|9101|9101",
                "date": today_iso,
                "review": {
                    "today_assessment": {
                        "title": "Morning Spin",
                        "assessment_text": "Old cached text (60m, 180W avg, 72% FTP).",
                    }
                },
            },
            user_id=self.user_id,
        )

        refreshed = generate_ai_review_and_outlook()
        self.assertIn("180W NP", refreshed["today_assessment"]["assessment_text"])
        self.assertNotIn("180W avg", refreshed["today_assessment"]["assessment_text"])
        self.assertEqual(DEBRIEF_CACHE_VERSION, 2)

    def test_frontend_debrief_labels_use_np(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo_root, "app", "static", "js", "app.js"), "r", encoding="utf-8") as f:
            js_src = f.read()
        with open(os.path.join(repo_root, "app", "static", "index.html"), "r", encoding="utf-8") as f:
            html_src = f.read()

        self.assertIn('if (lbl2) lbl2.textContent = "Norm. Power";', js_src)
        self.assertNotIn('if (lbl2) lbl2.textContent = "Avg Power";', js_src)
        self.assertIn("W NP", js_src)
        self.assertIn("NP vs Target", html_src)


if __name__ == "__main__":
    unittest.main()

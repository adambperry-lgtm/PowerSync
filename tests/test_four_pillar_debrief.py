import datetime
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app.database import (
    get_athlete_date,
    get_db_connection,
    init_db,
    reset_current_user_context,
    set_current_user_context,
    set_setting,
)
from app.services.debrief_analytics import compute_stream_analytics
from app.services.forecast_service import (
    clear_athlete_planned_session,
    save_athlete_planned_session,
)
from app.services.review_coach import (
    build_daily_review_and_outlook_local,
    call_gemini_coach_review,
    generate_ai_review_and_outlook,
)


class TestFourPillarDebrief(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_a = "test_four_pillar_a"
        self.user_b = "test_four_pillar_b"
        self._cleanup(self.user_a)
        self._cleanup(self.user_b)
        self.token = set_current_user_context(self.user_a)
        set_setting("athlete_ftp", 250, user_id=self.user_a)
        set_setting("athlete_timezone", "America/New_York", user_id=self.user_a)
        set_setting("athlete_ftp", 250, user_id=self.user_b)
        set_setting("athlete_timezone", "America/New_York", user_id=self.user_b)

    def tearDown(self):
        reset_current_user_context(self.token)
        self._cleanup(self.user_a)
        self._cleanup(self.user_b)

    def _cleanup(self, uid: str):
        clear_athlete_planned_session(user_id=uid)
        conn = get_db_connection()
        c = conn.cursor()
        for table in (
            "strava_activities",
            "strava_activity_streams",
            "whoop_metrics",
            "workouts",
            "settings",
            "target_plans",
        ):
            c.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()

    def test_erg_workout_on_low_readiness_breaks_circularity(self):
        """
        Even when the athlete edits/pushes a hard Threshold workout to Zwift and hits
        99% ERG NP fidelity (VI ~1.01), the debrief must independently flag that the
        effort exceeded Red/low Yellow readiness rather than rubber-stamping it.
        """
        today = get_athlete_date(self.user_a)
        today_iso = today.isoformat()

        # Athlete explicitly pushed a 60m Threshold workout to Zwift today
        save_athlete_planned_session(
            today_iso,
            {
                "title": "60-Min Threshold Intervals",
                "focus_area": "Threshold",
                "duration_minutes": 60,
                "estimated_tss": 85,
                "intervals": [
                    {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 75},
                    {"type": "SteadyState", "duration_sec": 3000, "power_pct": 95},
                    {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 60, "power_high_pct": 45},
                ],
            },
            user_id=self.user_a,
        )

        # Seed 5 days of higher HRV baseline (~65ms) so today's 45ms is deeply depressed
        conn = get_db_connection()
        c = conn.cursor()
        for d_off in range(1, 7):
            d_str = (today - datetime.timedelta(days=d_off)).isoformat()
            c.execute(
                """
                INSERT INTO whoop_metrics (user_id, date, recovery_score, hrv_rmssd, day_strain)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.user_a, d_str, 75, 66.0, 10.5),
            )
        conn.commit()
        conn.close()

        # Zwift ERG ride matches planned NP (~233W NP, VI = 1.01) on 28% Red recovery!
        act = {
            "id": "erg_test_101",
            "name": "Zwift - 60-Min Threshold Intervals",
            "sport_type": "VirtualRide",
            "start_date": f"{today_iso}T07:30:00",
            "moving_time_sec": 3600,
            "average_watts": 231.0,
            "weighted_average_watts": 233.0,
            "average_heartrate": 166.0,
            "max_heartrate": 180.0,
            "suffer_score": 92,
            "distance_meters": 38000.0,
        }

        review = build_daily_review_and_outlook_local(
            whoop_data={"recovery_score": 28, "hrv_rmssd": 45.0, "day_strain": 16.4, "sleep_performance": 62},
            trailing_strava={"total_tss": 260, "acute_weighted_tss": 260},
            today_acts=[act],
            latest_act=act,
            program={
                "goal_title": "FTP Booster",
                "phase": "Build Phase",
                "current_week": 4,
                "total_weeks": 8,
                "target_ftp": 265,
                "weekly_tss_target": 360,
                "weekly_tss_actual": 260,
            },
            ftp=250,
            max_hr=185,
            day_acts=[act],
        )

        assessment = review["today_assessment"]
        pillars = assessment["debrief_pillars"]

        # Plan compliance is high (ERG mode worked), YET readiness fit & takeaway flag overreach
        self.assertGreaterEqual(assessment["compliance_score"], 90)
        self.assertTrue(pillars["is_erg_like"])
        self.assertEqual(pillars["execution_nuances"]["status"], "ERG-Locked Structure")
        self.assertEqual(pillars["readiness_fit"]["status"], "Overreached Readiness")
        self.assertEqual(pillars["readiness_fit"]["color"], "rose")
        self.assertEqual(pillars["takeaway_color"], "rose")
        self.assertIn("Overreached Readiness", pillars["takeaway_badge"])
        self.assertLess(pillars["readiness_fit"]["hrv_delta_pct"], -20.0)

    def test_physiological_ef_baseline_and_stream_decoupling_and_interval_fade(self):
        """
        Verifies:
          1. Personal EF baseline is scoped strictly by user_id.
          2. Real stream analytics compute Pw:Hr aerobic decoupling, cadence fade,
             and discrete work-interval fade.
        """
        today = get_athlete_date(self.user_a)
        today_iso = today.isoformat()

        # Seed 4 historical rides for user_a with EF ~1.30 (182W / 140 bpm)
        # and 4 rides for user_b with EF ~2.00 (to ensure zero cross-user leakage)
        conn = get_db_connection()
        c = conn.cursor()
        for i in range(1, 5):
            d_str = (today - datetime.timedelta(days=i * 3)).isoformat()
            c.execute(
                """
                INSERT INTO strava_activities (
                    user_id, id, name, sport_type, start_date, moving_time_sec,
                    average_watts, weighted_average_watts, average_heartrate, max_heartrate
                ) VALUES (?, ?, ?, 'Ride', ?, 3600, 178, 182, 140, 162)
                """,
                (self.user_a, f"hist_a_{i}", f"Base Ride {i}", f"{d_str}T08:00:00"),
            )
            c.execute(
                """
                INSERT INTO strava_activities (
                    user_id, id, name, sport_type, start_date, moving_time_sec,
                    average_watts, weighted_average_watts, average_heartrate, max_heartrate
                ) VALUES (?, ?, ?, 'Ride', ?, 3600, 260, 270, 135, 155)
                """,
                (self.user_b, f"hist_b_{i}", f"Other User Ride {i}", f"{d_str}T08:00:00"),
            )
        conn.commit()
        conn.close()

        # Build a 40-minute (2400s) synthetic stream with steady ~185W but HR drifting 132 -> 152 bpm
        # and cadence fading 92 -> 84 rpm -> clear cardiac decoupling (> 10%) & muscular cadence fade
        n = 2400
        watts = [185.0] * n
        hr = [132.0 + (20.0 * (i / n)) for i in range(n)]
        cadence = [92.0 - (8.0 * (i / n)) for i in range(n)]
        time_arr = list(range(n))

        act = {
            "id": "stream_test_202",
            "name": "Endurance Ride",
            "sport_type": "Ride",
            "start_date": f"{today_iso}T09:00:00",
            "moving_time_sec": n,
            "average_watts": 185.0,
            "weighted_average_watts": 185.0,
            "average_heartrate": 142.0,
            "max_heartrate": 154.0,
            "suffer_score": 45,
            "streams": {"time": time_arr, "watts": watts, "heartrate": hr, "cadence": cadence},
        }

        review = build_daily_review_and_outlook_local(
            whoop_data={"recovery_score": 76, "hrv_rmssd": 55.0, "day_strain": 10.2},
            trailing_strava={"total_tss": 190, "acute_weighted_tss": 190},
            today_acts=[act],
            latest_act=act,
            program={
                "goal_title": "Century Endurance",
                "phase": "Base Phase",
                "current_week": 2,
                "total_weeks": 8,
                "target_ftp": 265,
                "weekly_tss_target": 320,
                "weekly_tss_actual": 190,
            },
            ftp=250,
            max_hr=185,
            day_acts=[act],
        )

        pillars = review["today_assessment"]["debrief_pillars"]
        phys = pillars["physiological_response"]
        exec_p = pillars["execution_nuances"]
        goal_p = pillars["goal_progress"]

        # EF baseline must come from user_a (~1.30), never contaminated by user_b (~2.00)
        self.assertAlmostEqual(phys["ef_baseline"], 1.30, places=2)
        self.assertTrue(pillars["has_stream_telemetry"])
        self.assertIsNotNone(phys["decoupling_pct"])
        self.assertGreater(phys["decoupling_pct"], 5.0)
        self.assertIsNotNone(exec_p["cadence_fade_rpm"])
        self.assertLess(exec_p["cadence_fade_rpm"], -2.0)

        # Goal progress populated cleanly
        self.assertEqual(goal_p["goal_title"], "Century Endurance")
        self.assertEqual(goal_p["ftp_gap_w"], 15)
        self.assertEqual(goal_p["weekly_tss_target"], 320)
        self.assertGreater(goal_p["this_ride_weekly_share_pct"], 0)

        # Also test discrete work-interval fade detection directly
        interval_watts = (
            [130.0] * 300
            + [250.0] * 180 + [120.0] * 120
            + [240.0] * 180 + [120.0] * 120
            + [220.0] * 180 + [120.0] * 120
        )
        interval_hr = (
            [120.0] * 300
            + [160.0] * 180 + [130.0] * 120
            + [166.0] * 180 + [132.0] * 120
            + [172.0] * 180 + [135.0] * 120
        )
        interval_cad = (
            [88.0] * 300
            + [94.0] * 180 + [85.0] * 120
            + [90.0] * 180 + [85.0] * 120
            + [84.0] * 180 + [82.0] * 120
        )
        s_metrics = compute_stream_analytics(
            {"watts": interval_watts, "heartrate": interval_hr, "cadence": interval_cad},
            ftp=250,
        )
        self.assertIsNotNone(s_metrics["interval_fade"])
        self.assertEqual(s_metrics["interval_fade"]["interval_count"], 3)
        self.assertLess(s_metrics["interval_fade"]["interval_power_fade_pct"], -10.0)
        self.assertGreater(s_metrics["interval_fade"]["interval_hr_drift_bpm"], 8.0)
        self.assertLess(s_metrics["interval_fade"]["interval_cadence_fade_rpm"], -5.0)

    def test_gemini_prompt_includes_four_pillars_and_applies_pillar_notes(self):
        captured = []

        def fake_post(url, json=None, timeout=20):
            captured.append(json["contents"][0]["parts"][0]["text"])
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"insights": "Your 195W NP ride showed solid aerobic efficiency (+4% EF vs baseline) '
                                        'while staying aligned with your 78% recovery and Build Phase weekly pace.", '
                                        '"tomorrow_guidance": "Follow with a 45m Zone 2 flush tomorrow.", '
                                        '"pillar_notes": {'
                                        '"physiological": "EF climbed 4% above baseline with tight cardiac coupling.", '
                                        '"readiness": "Well-matched to 78% Green recovery and steady HRV.", '
                                        '"execution": "ERG held power flat; steady 90 rpm cadence confirms low muscular fade.", '
                                        '"goal": "Moves you to 62% of weekly Build Phase TSS toward 265W FTP."}}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
            return resp

        today_iso = get_athlete_date(self.user_a).isoformat()
        set_setting("strava_tokens", {"access_token": "tok"}, user_id=self.user_a)
        set_setting("gemini_api_key", "fake-gemini-key", user_id=self.user_a)

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts,
                weighted_average_watts, average_heartrate, max_heartrate,
                suffer_score, kilojoules, raw_json
            ) VALUES (?, '9901', 'Zwift - Tempo Cruise', 'VirtualRide', ?, 3600, 32000, 150, 193, 195, 140, 162, 58, 690, ?)
            """,
            (self.user_a, f"{today_iso}T08:00:00", json.dumps({"id": 9901, "start_date_local": f"{today_iso}T08:00:00"})),
        )
        conn.commit()
        conn.close()

        with patch("requests.post", side_effect=fake_post):
            res = generate_ai_review_and_outlook(force_refresh=True)

        self.assertEqual(len(captured), 1)
        prompt = captured[0]
        self.assertIn("4-PILLAR TELEMETRY", prompt)
        self.assertIn("CRITICAL ANTI-CIRCULARITY RULE", prompt)
        self.assertIn("Long-Term Goal Progress", prompt)

        pillars = res["today_assessment"]["debrief_pillars"]
        self.assertIn("EF climbed 4%", pillars["physiological_response"]["ai_note"])
        self.assertIn("Well-matched", pillars["readiness_fit"]["ai_note"])
        self.assertIn("ERG held power flat", pillars["execution_nuances"]["ai_note"])
        self.assertIn("Build Phase TSS", pillars["goal_progress"]["ai_note"])

    def test_frontend_four_pillar_ui_hooks_exist(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo_root, "app", "static", "index.html"), "r", encoding="utf-8") as f:
            html_src = f.read()
        with open(os.path.join(repo_root, "app", "static", "js", "app.js"), "r", encoding="utf-8") as f:
            js_src = f.read()

        for elem_id in (
            "debriefPillarsGrid",
            "pillarPhysStatus",
            "pillarReadinessStatus",
            "pillarExecutionStatus",
            "pillarGoalStatus",
            "pillarGoalBarFill",
        ):
            self.assertIn(elem_id, html_src)
            self.assertIn(elem_id, js_src)

    def test_structured_erg_intervals_with_vi_above_105_detected_as_erg_locked(self):
        """
        A structured Zwift ERG interval workout (e.g. 3 work blocks + recoveries) naturally
        produces whole-ride VI > 1.05 (such as 1.08). Stream steadiness within blocks must
        detect ERG-mode lock so it is never mislabeled as a non-ERG stochastic ride or power fade.
        """
        today = get_athlete_date(self.user_a)
        today_iso = today.isoformat()

        # Build a 45-min (2700s) structured ERG stream:
        # 5m warmup @ 140W, then 3x (6m work @ 240W/235W/229W + 3m recovery @ 125W), 5m cooldown @ 120W
        def _erg_seg(watts_target: float, secs: int) -> list[float]:
            # Realistic smart-trainer +/- 3W micro-oscillation
            return [watts_target + ((i % 5) - 2) * 1.5 for i in range(secs)]

        watts = (
            _erg_seg(140.0, 300)
            + _erg_seg(240.0, 360) + _erg_seg(125.0, 180)
            + _erg_seg(235.0, 360) + _erg_seg(125.0, 180)
            + _erg_seg(229.0, 360) + _erg_seg(125.0, 180)
            + _erg_seg(120.0, 600)
        )
        n = len(watts)
        hr = [125.0 + (22.0 * (i / n)) for i in range(n)]
        cadence = [90.0 - (4.0 * (i / n)) for i in range(n)]

        act = {
            "id": "erg_structured_108",
            "name": "Zwift - Structured Base Intervals",
            "sport_type": "VirtualRide",
            "start_date": f"{today_iso}T08:00:00",
            "moving_time_sec": n,
            "average_watts": 186.0,
            "weighted_average_watts": 201.0,  # VI = 201 / 186 = 1.08
            "average_heartrate": 141.0,
            "max_heartrate": 162.0,
            "suffer_score": 65,
            "streams": {"time": list(range(n)), "watts": watts, "heartrate": hr, "cadence": cadence},
        }

        review = build_daily_review_and_outlook_local(
            whoop_data={"recovery_score": 91, "hrv_rmssd": 72.0, "day_strain": 13.6},
            trailing_strava={"total_tss": 242, "acute_weighted_tss": 242},
            today_acts=[act],
            latest_act=act,
            program={
                "goal_title": "Base Fitness",
                "phase": "Base Phase",
                "current_week": 2,
                "total_weeks": 8,
                "target_ftp": 265,
                "weekly_tss_target": 400,
                "weekly_tss_actual": 242,
            },
            ftp=250,
            max_hr=185,
            day_acts=[act],
        )

        pillars = review["today_assessment"]["debrief_pillars"]
        exec_p = pillars["execution_nuances"]
        self.assertTrue(pillars["is_erg_like"])
        self.assertTrue(exec_p["is_erg_like"])
        self.assertEqual(exec_p["vi"], 1.08)
        self.assertEqual(exec_p["status"], "ERG-Locked Structure")
        self.assertIn("VI 1.08 (ERG Structured)", exec_p["chips"])
        self.assertNotIn("faded", exec_p["summary"].lower())

        # Conversely, a non-ERG Zwift free-ride with continuous surges within 20s windows
        # must NOT be flagged as ERG-locked.
        free_ride_watts = [185.0 + ((i * 17) % 90) - 45.0 for i in range(1800)]
        free_metrics = compute_stream_analytics({"watts": free_ride_watts}, ftp=250)
        self.assertFalse(free_metrics["erg_stream_detected"])


if __name__ == "__main__":
    unittest.main()

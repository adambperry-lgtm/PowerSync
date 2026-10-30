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
from app.services.review_coach import (
    resolve_day_prescribed_target,
    build_daily_review_and_outlook_local,
    generate_ai_review_and_outlook
)
from app.services.forecast_service import (
    save_athlete_planned_session,
    clear_athlete_planned_session
)

class TestPrescribedTargetFidelity(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_target_fidelity_test"
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (id, email, name, picture)
            VALUES (?, 'fidelity@powersync.local', 'Fidelity Athlete', '')
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

    def test_lower_effort_scheduled_session_overrides_high_recovery_target(self):
        """
        Verifies that when a lower effort ride (e.g. Zone 2 Aerobic Base) is prescribed
        in the schedule, the coach analysis evaluates against Zone 2 (70% FTP) instead of
        assuming Sweet Spot (90% FTP) on high Whoop recovery (e.g. 95%).
        """
        today = get_athlete_date(self.user_id)
        yesterday_iso = (today - datetime.timedelta(days=1)).isoformat()

        # Athlete had an updated schedule specifying a lower-effort Zone 2 session yesterday
        save_athlete_planned_session(yesterday_iso, {
            "title": "45-Min Zone 2 Aerobic Base Flush",
            "focus_area": "Zone 2 Base",
            "duration_minutes": 45,
            "estimated_tss": 35,
            "is_rest": False
        }, user_id=self.user_id)

        target = resolve_day_prescribed_target(
            date_str=yesterday_iso,
            workout_recovery=95,  # High green recovery!
            ftp=250,
            user_id=self.user_id,
            is_today=False
        )

        self.assertEqual(target["target_zone"], "Zone 2 Aerobic Base")
        self.assertEqual(target["target_pct_ftp"], 70)
        self.assertIn("Zone 2", target["target_title"])

    def test_execution_bullseye_for_lower_effort_ride_matching_updated_schedule(self):
        """
        Verifies that an athlete riding at 74% FTP (186W) receives an Execution Bullseye
        verdict (>= 90% compliance) when a Zone 2 session was on the schedule, rather than
        being criticized for 'Conservative Pacing'.
        """
        today = get_athlete_date(self.user_id)
        yesterday_iso = (today - datetime.timedelta(days=1)).isoformat()

        save_athlete_planned_session(yesterday_iso, {
            "title": "45-Min Zone 2 Aerobic Base Flush",
            "focus_area": "Zone 2 Aerobic Base",
            "duration_minutes": 45,
            "estimated_tss": 35,
            "is_rest": False
        }, user_id=self.user_id)

        # Yesterday's completed activity: 47m at 186W (74% of 250W FTP)
        act = {
            "name": "Zwift - 45-Min Aerobic Base",
            "start_date": f"{yesterday_iso}T21:00:00",
            "moving_time_sec": 47 * 60,
            "average_watts": 186,
            "weighted_average_watts": 186,
            "average_heartrate": 132,
            "suffer_score": 38,
            "distance_meters": 22000
        }

        review = build_daily_review_and_outlook_local(
            whoop_data={"recovery_score": 95, "day_strain": 5.0, "hrv_rmssd": 50.0},
            trailing_strava={"total_tss": 150, "acute_weighted_tss": 150},
            today_acts=[],
            latest_act=act,
            program={},
            ftp=250,
            day_acts=[act]
        )

        assessment = review["today_assessment"]
        self.assertEqual(assessment["target_zone"], "Zone 2 Aerobic Base")
        self.assertEqual(assessment["target_pct_ftp"], 70)
        self.assertEqual(assessment["target_watts"], 175)
        self.assertEqual(assessment["verdict"], "Execution Bullseye")
        self.assertEqual(assessment["verdict_badge"], "🎯 Target Mastered")
        self.assertGreaterEqual(assessment["compliance_score"], 90)

    def test_debrief_returns_strava_recent_activities(self):
        """Verifies that generate_ai_review_and_outlook bundles live Strava telemetry for auto-rendering."""
        debrief = generate_ai_review_and_outlook()
        self.assertIn("strava", debrief)
        self.assertIn("recent_activities", debrief["strava"])

if __name__ == "__main__":
    unittest.main()

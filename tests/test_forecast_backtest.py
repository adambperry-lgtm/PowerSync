import datetime
import unittest
from fastapi.testclient import TestClient

from app.database import (
    init_db,
    get_db_connection,
    set_current_user_context,
    get_athlete_date,
)
from app.main import app
from app.services.review_coach import (
    predict_3day_recovery_heuristic,
    predict_3day_recovery_hybrid,
    build_preference_aligned_outlook_days,
)
from app.services.forecast_backtest_service import run_recovery_forecast_backtest


class TestForecastBacktest(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_a = "user_backtest_a"
        self.user_b = "user_backtest_b"
        set_current_user_context(self.user_a)
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_db_connection()
        c = conn.cursor()
        users = (self.user_a, self.user_b)
        c.execute("DELETE FROM whoop_metrics WHERE user_id IN (?, ?)", users)
        c.execute("DELETE FROM strava_activities WHERE user_id IN (?, ?)", users)
        c.execute("DELETE FROM settings WHERE user_id IN (?, ?)", users)
        c.execute("DELETE FROM workouts WHERE user_id IN (?, ?)", users)
        conn.commit()
        conn.close()

    def _insert_whoop(
        self,
        user_id: str,
        d_iso: str,
        recovery: int,
        strain: float = 10.0,
        hrv: float = 55.0,
        rhr: int = 52,
        sleep_perf: int = 85,
        sleep_hrs: float = 7.8,
    ):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO whoop_metrics
            (user_id, date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_performance, sleep_duration_hours, day_strain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, d_iso, recovery, hrv, rhr, sleep_perf, sleep_hrs, strain),
        )
        conn.commit()
        conn.close()

    def _insert_strava(
        self,
        user_id: str,
        act_id: str,
        d_iso: str,
        suffer_score: float = 50.0,
        moving_time_sec: int = 3600,
    ):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO strava_activities
            (user_id, id, name, sport_type, start_date, moving_time_sec, suffer_score, weighted_average_watts, kilojoules)
            VALUES (?, ?, ?, 'Ride', ?, ?, ?, 210, 750)
            """,
            (user_id, act_id, f"Ride {d_iso}", f"{d_iso}T15:00:00Z", moving_time_sec, suffer_score),
        )
        conn.commit()
        conn.close()

    def test_heuristic_all_three_branches_exact_math(self):
        """Verify all 3 branches of predict_3day_recovery_heuristic and their clamp bounds."""
        # Branch 1: Heavy Load Today (strain >= 13.5)
        b1 = predict_3day_recovery_heuristic(
            today_recovery=80,
            today_strain=16.2,
            workout_strain=16.2,
            is_today=True,
            is_yesterday=False,
            has_trained_today=True,
            suffer_score=75,
        )
        self.assertEqual(b1["branch"], "trained_today_heavy")
        # day1 = max(38, min(62, 80-10)) = 62, day2 = min(84, 62+24) = 84, day3 = min(88, 84+6) = 88
        self.assertEqual(b1["recoveries"], [62, 84, 88])

        # Branch 1 floor check (low recovery)
        b1_low = predict_3day_recovery_heuristic(
            today_recovery=30,
            today_strain=15.0,
            workout_strain=15.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=True,
        )
        self.assertEqual(b1_low["branch"], "trained_today_heavy")
        self.assertEqual(b1_low["recoveries"], [38, 62, 68])

        # Branch 2: Heavy Yesterday + Light/Passive Today
        b2 = predict_3day_recovery_heuristic(
            today_recovery=48,
            today_strain=7.5,
            workout_strain=15.8,
            is_today=False,
            is_yesterday=True,
            has_trained_today=False,
            suffer_score=65,
        )
        self.assertEqual(b2["branch"], "trained_yesterday_heavy")
        # day1 = min(74, 48+22) = 70, day2 = min(86, 70+14) = 84, day3 = 76
        self.assertEqual(b2["recoveries"], [70, 84, 76])

        # Branch 3: Standard / Balanced
        b3 = predict_3day_recovery_heuristic(
            today_recovery=70,
            today_strain=9.0,
            workout_strain=9.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=True,
            suffer_score=25,
        )
        self.assertEqual(b3["branch"], "standard")
        # day1 = min(88, 70+12) = 82, day2 = max(45, 82-14) = 68, day3 = 74
        self.assertEqual(b3["recoveries"], [82, 68, 74])

    def test_hybrid_live_parity_with_outlook_builder(self):
        """Ensure build_preference_aligned_outlook_days matches promoted predict_3day_recovery_hybrid."""
        # Tuesday Oct 20 -> Wed (training), Thu (training), Fri (training) with no rest overrides
        today = datetime.date(2026, 10, 20)
        expected = predict_3day_recovery_hybrid(
            origin_dt=today,
            today_recovery=78,
            today_strain=16.0,
            workout_strain=16.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=True,
            suffer_score=80,
            personal_rec_mean=78.0,
            mean_strain=10.5,
        )["recoveries"]

        outlook = build_preference_aligned_outlook_days(
            today=today,
            today_recovery=78,
            today_strain=16.0,
            workout_strain=16.0,
            is_today=True,
            is_yesterday=False,
            has_trained_today=True,
            session_summary={"suffer_score": 80},
            ftp=250,
            program={"phase": "Build Phase"},
        )
        actual = [d["projected_recovery"] for d in outlook]
        self.assertEqual(actual, expected)

        # Verify 36% Yellow floor on Heavy Load Today prevents false-Red zone flips
        heavy_low = predict_3day_recovery_hybrid(
            origin_dt=today,
            today_recovery=38,
            today_strain=17.5,
            workout_strain=17.5,
            is_today=True,
            is_yesterday=False,
            has_trained_today=True,
            personal_rec_mean=58.0,
            mean_strain=10.0,
        )
        self.assertEqual(heavy_low["recoveries"][0], 36)

        # Verify full-rest cap rises to 82% on Heavy Yesterday + Light Today (<5 strain)
        rest_rebound = predict_3day_recovery_hybrid(
            origin_dt=today,
            today_recovery=60,
            today_strain=0.8,
            workout_strain=15.5,
            is_today=False,
            is_yesterday=True,
            has_trained_today=False,
            personal_rec_mean=58.0,
            mean_strain=10.0,
        )
        self.assertEqual(rest_rebound["recoveries"][0], 82)

    def test_backtest_walks_history_across_all_branches_and_baselines(self):
        """Verify walk-forward backtest computes metrics across all 3 branches, confusion matrix, and correlations."""
        today = get_athlete_date(self.user_a)
        start = today - datetime.timedelta(days=15)

        # Build 15 consecutive days that trigger all 3 branches and include a Red day (<34%)
        # Pattern: heavy ride day -> light recovery day -> standard light ride day (repeating)
        pattern = [
            # (recovery, strain, has_ride, suffer, hrv, sleep)
            (72, 16.5, True, 85, 62.0, 88),   # Day 0: Heavy today
            (54, 6.2, False, 0, 48.0, 76),    # Day 1: Heavy yesterday + light today
            (76, 9.5, True, 30, 68.0, 90),    # Day 2: Standard
            (80, 15.8, True, 75, 70.0, 92),   # Day 3: Heavy today
            (28, 5.8, False, 0, 32.0, 58),    # Day 4: Actual Red! Heavy yesterday + light today
            (66, 8.4, False, 0, 58.0, 82),    # Day 5: Standard
            (74, 14.9, True, 68, 64.0, 86),   # Day 6: Heavy today
            (58, 6.8, False, 0, 50.0, 79),    # Day 7: Heavy yesterday + light today
            (78, 10.2, True, 35, 67.0, 88),   # Day 8: Standard
            (82, 17.0, True, 92, 72.0, 91),   # Day 9: Heavy today
            (45, 5.5, False, 0, 40.0, 70),    # Day 10: Heavy yesterday + light today
            (71, 9.0, False, 0, 60.0, 84),    # Day 11: Standard
            (75, 14.2, True, 64, 65.0, 87),   # Day 12: Heavy today
            (60, 6.0, False, 0, 52.0, 80),    # Day 13: Heavy yesterday + light today
            (79, 8.8, False, 0, 69.0, 89),    # Day 14: Standard
        ]

        for idx, (rec, strain, has_ride, suffer, hrv, sleep_p) in enumerate(pattern):
            d_iso = (start + datetime.timedelta(days=idx)).isoformat()
            self._insert_whoop(self.user_a, d_iso, rec, strain=strain, hrv=hrv, sleep_perf=sleep_p)
            if has_ride:
                self._insert_strava(self.user_a, f"bt_act_{idx}", d_iso, suffer_score=suffer)

        report = run_recovery_forecast_backtest(user_id=self.user_a, days=30)

        self.assertTrue(report["success"])
        self.assertEqual(report["data_coverage"]["whoop_days_in_window"], 15)
        self.assertEqual(report["data_coverage"]["day_1_pairs"], 14)
        self.assertTrue(report["data_coverage"]["sufficient_data"])

        # All 3 branches must be populated
        for b_key in ("trained_today_heavy", "trained_yesterday_heavy", "standard"):
            self.assertGreater(report["by_branch"][b_key]["trigger_count"], 0)
            self.assertGreater(report["by_branch"][b_key]["day_1"]["count"], 0)
            self.assertIsNotNone(report["by_branch"][b_key]["day_1"]["mae"])

        # Horizons day_1 (14), day_2 (13), day_3 (12)
        self.assertEqual(report["by_horizon"]["day_1"]["count"], 14)
        self.assertEqual(report["by_horizon"]["day_2"]["count"], 13)
        self.assertEqual(report["by_horizon"]["day_3"]["count"], 12)
        self.assertEqual(report["by_horizon"]["overall"]["count"], 39)

        # Baselines list contains all 5 models (Candidate + Heuristic + 3 baselines) with valid Day +1 MAE
        baseline_keys = [b["key"] for b in report["baselines"]]
        self.assertEqual(
            baseline_keys,
            ["candidate", "heuristic", "rolling_mean", "mean_reversion", "persistence"],
        )
        for b in report["baselines"]:
            self.assertIsNotNone(b["day_1_mae"])
            self.assertIsNotNone(b["day_1_bias"])

        # Candidate model payload and per-branch candidate metrics populated
        cand = report["candidate_model"]
        self.assertIsNotNone(cand["by_horizon"]["day_1"]["mae"])
        self.assertIsNotNone(cand["by_horizon"]["overall"]["mae"])
        self.assertIsNotNone(cand["vs_heuristic"]["day_1_mae_delta"])
        self.assertEqual(cand["learned_profile"]["model_type"], "hybrid_3branch_personal_baseline")
        self.assertIsNotNone(cand["learned_profile"]["personal_baseline_recovery"])
        for b_key in ("trained_today_heavy", "trained_yesterday_heavy", "standard"):
            self.assertIsNotNone(report["by_branch"][b_key]["candidate_day_1"]["mae"])

        # Structural check: actual Red day (28%) occurred once and heuristic never predicts Red (<34)
        cm_d1 = report["confusion_matrix"]["day_1"]
        self.assertEqual(cm_d1["actual_red_total"], 1)
        self.assertEqual(cm_d1["caught_red_count"], 0)

        # Correlations should be computed for today_recovery & day_strain
        corr_map = {c["key"]: c for c in report["feature_correlations"]}
        self.assertIsNotNone(corr_map["day_strain"]["r_next_day_recovery"])
        # Because heavy strain days always precede lower next-day recovery in this pattern, correlation is negative
        self.assertLess(corr_map["day_strain"]["r_next_day_recovery"], 0.0)

        # Insights populated
        self.assertTrue(len(report["insights"]) >= 1)

    def test_candidate_model_zero_future_leakage(self):
        """Mutating future WHOOP recovery after day t must not change day t's walk-forward candidate prediction."""
        today = get_athlete_date(self.user_a)
        start = today - datetime.timedelta(days=12)

        base_recs = [70, 52, 74, 68, 48, 72, 65, 55, 76, 60, 50, 72]
        strains = [15.5, 5.0, 10.0, 16.0, 4.5, 9.5, 14.8, 6.0, 11.0, 15.2, 5.5, 9.0]
        for idx, (rec, st) in enumerate(zip(base_recs, strains)):
            d_iso = (start + datetime.timedelta(days=idx)).isoformat()
            self._insert_whoop(self.user_a, d_iso, rec, strain=st, hrv=55.0 + (idx % 3) * 4.0)

        rep_before = run_recovery_forecast_backtest(user_id=self.user_a, days=30)
        # Capture Day +1 prediction made on origin day idx=5 (targeting idx=6)
        target_mid_iso = (start + datetime.timedelta(days=6)).isoformat()
        pred_before = next(t["candidate_recovery"] for t in rep_before["timeline"] if t["target_date"] == target_mid_iso)

        # Now drastically alter future recoveries on days idx=6..11 (strictly AFTER origin day idx=5)
        for idx in range(6, 12):
            d_iso = (start + datetime.timedelta(days=idx)).isoformat()
            self._insert_whoop(self.user_a, d_iso, 20 if idx % 2 == 0 else 95, strain=strains[idx], hrv=40.0)

        rep_after = run_recovery_forecast_backtest(user_id=self.user_a, days=30)
        pred_after = next(t["candidate_recovery"] for t in rep_after["timeline"] if t["target_date"] == target_mid_iso)

        self.assertEqual(pred_before, pred_after)

    def test_multi_user_isolation_and_empty_history(self):
        """User A's historical WHOOP metrics must never appear in User B's backtest."""
        today = get_athlete_date(self.user_a)
        for i in range(1, 8):
            d_iso = (today - datetime.timedelta(days=i)).isoformat()
            self._insert_whoop(self.user_a, d_iso, 75, strain=11.0)

        rep_a = run_recovery_forecast_backtest(user_id=self.user_a, days=30)
        rep_b = run_recovery_forecast_backtest(user_id=self.user_b, days=30)

        self.assertEqual(rep_a["data_coverage"]["day_1_pairs"], 6)
        self.assertEqual(rep_b["data_coverage"]["day_1_pairs"], 0)
        self.assertFalse(rep_b["data_coverage"]["sufficient_data"])
        self.assertEqual(rep_b["timeline"], [])

    def test_api_endpoint_guest_guard_and_authenticated_response(self):
        """GET /api/review/forecast-accuracy enforces guest privacy and returns report for signed-in user."""
        client = TestClient(app)

        # Guest request (no auth)
        guest_res = client.get("/api/review/forecast-accuracy?days=30")
        self.assertEqual(guest_res.status_code, 200)
        guest_data = guest_res.json()
        self.assertTrue(guest_data.get("requires_auth"))
        self.assertEqual(guest_data["data_coverage"]["day_1_pairs"], 0)

        # Authenticated request for user_a with seeded data
        today = get_athlete_date(self.user_a)
        for idx, rec in enumerate([70, 62, 74, 80, 68, 72]):
            d_iso = (today - datetime.timedelta(days=6 - idx)).isoformat()
            self._insert_whoop(self.user_a, d_iso, rec, strain=10.5)

        auth_res = client.get(
            "/api/review/forecast-accuracy?days=30",
            headers={"x-user-id": self.user_a},
        )
        self.assertEqual(auth_res.status_code, 200)
        auth_data = auth_res.json()
        self.assertTrue(auth_data["success"])
        self.assertFalse(auth_data.get("requires_auth", False))
        self.assertEqual(auth_data["data_coverage"]["day_1_pairs"], 5)
        self.assertIsNotNone(auth_data["summary"]["day_1_mae"])


if __name__ == "__main__":
    unittest.main()

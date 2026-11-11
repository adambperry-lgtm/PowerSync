import unittest
import json
import datetime
from app.main import app
from tests.test_multi_user_isolation import ASGIClient
from app.database import (
    get_db_connection,
    init_db,
    set_setting,
    set_current_user_context,
    reset_current_user_context
)
from app.services.power_profile_service import (
    calculate_activity_peak_powers,
    get_power_spiderweb_profile,
    calculate_spiderweb_target_changes,
    set_active_spiderweb_goal,
    get_active_spiderweb_goal,
    clear_active_spiderweb_goal
)
from app.services.coach_tools import execute_coach_tool

class TestPowerSpiderweb(unittest.TestCase):
    def setUp(self):
        init_db()
        self.user_id = "usr_spiderweb_test"
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (id, email, name, picture)
            VALUES (?, 'spiderweb@powersync.local', 'Spiderweb Athlete', '')
        """, (self.user_id,))

        # Clear existing activities for this test user
        c.execute("DELETE FROM strava_activities WHERE user_id = ?", (self.user_id,))

        # Insert representative activities across 2 months
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_date = (now - datetime.timedelta(days=5)).isoformat()
        prior_date = (now - datetime.timedelta(days=40)).isoformat()

        # Recent high-intensity workout
        recent_raw = {
            "max_watts": 850,
            "weighted_average_watts": 280,
            "average_watts": 240
        }
        c.execute("""
            INSERT INTO strava_activities (
                id, user_id, name, sport_type, distance_meters, moving_time_sec,
                elapsed_time_sec, total_elevation_gain, start_date,
                average_watts, weighted_average_watts, kilojoules, raw_json
            ) VALUES (?, ?, ?, 'Ride', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "act_spider_1", self.user_id, "Recent Punchy Ride", 35000, 3600,
            3600, 350, recent_date, 240, 280, 864, json.dumps(recent_raw)
        ))

        # Prior base workout
        prior_raw = {
            "max_watts": 620,
            "weighted_average_watts": 220,
            "average_watts": 200
        }
        c.execute("""
            INSERT INTO strava_activities (
                id, user_id, name, sport_type, distance_meters, moving_time_sec,
                elapsed_time_sec, total_elevation_gain, start_date,
                average_watts, weighted_average_watts, kilojoules, raw_json
            ) VALUES (?, ?, ?, 'Ride', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "act_spider_2", self.user_id, "Prior Endurance Ride", 40000, 4200,
            4200, 250, prior_date, 200, 220, 840, json.dumps(prior_raw)
        ))

        conn.commit()
        conn.close()

        self.ctx_token = set_current_user_context(self.user_id)
        set_setting("athlete_ftp", 260, user_id=self.user_id)
        set_setting("athlete_weight", 70.0, user_id=self.user_id)
        self.client = ASGIClient(app)

    def tearDown(self):
        reset_current_user_context(self.ctx_token)

    def test_calculate_activity_peak_powers(self):
        activity = {
            "moving_time_seconds": 3600,
            "average_watts": 250,
            "max_watts": 800,
            "weighted_average_watts": 270,
            "raw_json": json.dumps({"max_watts": 800})
        }
        peaks = calculate_activity_peak_powers(activity, ftp=250)
        self.assertIn("5s", peaks)
        self.assertIn("1m", peaks)
        self.assertIn("5m", peaks)
        self.assertIn("20m", peaks)
        self.assertIn("60m", peaks)
        self.assertGreaterEqual(peaks["5s"], peaks["1m"])
        self.assertGreaterEqual(peaks["1m"], peaks["5m"])
        self.assertGreaterEqual(peaks["5m"], peaks["20m"])
        self.assertGreaterEqual(peaks["20m"], peaks["60m"])

    def test_spiderweb_profile_data_structure(self):
        profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe="30d")
        self.assertEqual(profile["timeframe"], "30d")
        self.assertIn("axes", profile)
        self.assertEqual(len(profile["axes"]), 5)

        axis_keys = [a["key"] for a in profile["axes"]]
        self.assertEqual(axis_keys, ["5s", "1m", "5m", "20m", "60m"])

        for ax in profile["axes"]:
            self.assertIn("current_watts", ax)
            self.assertIn("current_w_kg", ax)
            self.assertIn("current_radar_pct", ax)
            self.assertGreaterEqual(ax["current_radar_pct"], 20.0)
            self.assertLessEqual(ax["current_radar_pct"], 100.0)

        # Verify phenotype classification
        self.assertIn("phenotype", profile)
        self.assertIn("title", profile["phenotype"])
        self.assertIn("primary_strength", profile["phenotype"])
        self.assertIn("growth_focus", profile["phenotype"])

        # Verify progression timeline
        self.assertIn("progression_timeline", profile)
        self.assertGreaterEqual(len(profile["progression_timeline"]), 1)

    def test_spiderweb_timeframe_options(self):
        for tf in ["30d", "60d", "90d", "all_time", "invalid_default"]:
            profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe=tf)
            self.assertIn("axes", profile)
            self.assertEqual(len(profile["axes"]), 5)

    def test_api_power_spiderweb_endpoint(self):
        response = self.client.get(f"/api/power/spiderweb?timeframe=30d", headers={"X-User-ID": self.user_id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["timeframe"], "30d")
        self.assertIn("axes", data)
        self.assertEqual(len(data["axes"]), 5)
        self.assertIn("phenotype", data)
        self.assertIn("progression_timeline", data)

    def test_api_dashboard_includes_power_spiderweb(self):
        response = self.client.get("/api/dashboard", headers={"X-User-ID": self.user_id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("power_spiderweb", data)
        self.assertIsNotNone(data["power_spiderweb"])
        self.assertIn("axes", data["power_spiderweb"])


    def test_calculate_spiderweb_target_changes(self):
        targets = calculate_spiderweb_target_changes(user_id=self.user_id, timeframe="30d")
        self.assertIn("duration_category_targets", targets)
        self.assertEqual(len(targets["duration_category_targets"]), 5)

        for d in targets["duration_category_targets"]:
            self.assertIn("tier1_progressive", d)
            self.assertIn("tier2_transformative", d)
            self.assertIn("tier3_benchmark", d)
            self.assertGreater(d["tier1_progressive"]["target_watts"], d["current_watts"])
            self.assertGreater(d["tier2_transformative"]["target_watts"], d["tier1_progressive"]["target_watts"])
            self.assertGreater(d["tier3_benchmark"]["target_watts"], d["tier2_transformative"]["target_watts"])
            self.assertGreater(d["tier3_benchmark"]["target_watts"], d["current_watts"])
            self.assertGreater(d["benchmark_watts"], d["current_watts"])
            self.assertGreater(d["tier3_benchmark"]["delta_watts"], 0)

        self.assertIn("rider_type_transformation_targets", targets)
        self.assertEqual(len(targets["rider_type_transformation_targets"]), 6)
        pheno_ids = [p["id"] for p in targets["rider_type_transformation_targets"]]
        self.assertIn("Puncheur", pheno_ids)
        self.assertIn("Rouleur", pheno_ids)
        self.assertIn("Climber", pheno_ids)
        self.assertIn("Sprinter", pheno_ids)
        self.assertIn("Pursuiter", pheno_ids)

    def test_set_and_clear_spiderweb_goal(self):
        # 1. Set duration goal
        goal_payload = {
            "goal_type": "duration",
            "target_key": "20m",
            "target_watts": 310
        }
        saved_goal = set_active_spiderweb_goal(goal_payload, user_id=self.user_id)
        self.assertEqual(saved_goal["target_key"], "20m")
        self.assertEqual(saved_goal["target_envelope"]["20m"], 310)

        # Verify profile incorporates goal
        profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe="30d")
        self.assertTrue(profile["has_active_goal"])
        self.assertIsNotNone(profile["active_goal"])
        ax_20m = next(a for a in profile["axes"] if a["key"] == "20m")
        self.assertEqual(ax_20m["target_watts"], 310)
        self.assertFalse(ax_20m["goal_met"])
        self.assertGreater(ax_20m["goal_remaining_watts"], 0)

        # 2. Set phenotype goal (Puncheur)
        pheno_payload = {
            "goal_type": "phenotype",
            "target_key": "Puncheur"
        }
        saved_pheno = set_active_spiderweb_goal(pheno_payload, user_id=self.user_id)
        self.assertEqual(saved_pheno["target_key"], "Puncheur")
        self.assertIn("1m", saved_pheno["target_envelope"])
        self.assertIn("5m", saved_pheno["target_envelope"])

        # 3. Clear goal
        clear_active_spiderweb_goal(user_id=self.user_id)
        profile_cleared = get_power_spiderweb_profile(user_id=self.user_id, timeframe="30d")
        self.assertFalse(profile_cleared["has_active_goal"])
        self.assertIsNone(profile_cleared["active_goal"])

    def test_api_power_spiderweb_target_endpoints(self):
        # GET target analysis
        res_analysis = self.client.get("/api/power/spiderweb/target-analysis", headers={"X-User-ID": self.user_id})
        self.assertEqual(res_analysis.status_code, 200)
        data_a = res_analysis.json()
        self.assertIn("duration_category_targets", data_a)
        self.assertIn("rider_type_transformation_targets", data_a)

        # POST goal
        post_res = self.client.post("/api/power/spiderweb/goal", json={
            "goal_type": "phenotype",
            "target_key": "Rouleur"
        }, headers={"X-User-ID": self.user_id})
        self.assertEqual(post_res.status_code, 200)
        post_data = post_res.json()
        self.assertTrue(post_data["success"])
        self.assertEqual(post_data["goal"]["target_key"], "Rouleur")

        # GET goal
        get_res = self.client.get("/api/power/spiderweb/goal", headers={"X-User-ID": self.user_id})
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertTrue(get_data["has_active_goal"])
        self.assertEqual(get_data["goal"]["target_key"], "Rouleur")

        # DELETE goal
        del_res = self.client.request("DELETE", "/api/power/spiderweb/goal", headers={"X-User-ID": self.user_id})
        self.assertEqual(del_res.status_code, 200)
        del_data = del_res.json()
        self.assertTrue(del_data["success"])

    def test_coach_tools_spiderweb_goal(self):
        # Test setting goal via coach tool
        res = execute_coach_tool("set_spiderweb_goal", {
            "goal_type": "phenotype",
            "target_key": "Puncheur"
        }, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertIn("Puncheur", res["tool_summary"])

        # Test inspecting goal via coach tool
        res_inspect = execute_coach_tool("get_active_spiderweb_goal", {}, user_id=self.user_id)
        self.assertTrue(res_inspect["has_active_goal"])
        self.assertIn("Puncheur", res_inspect["goal"]["target_title"])

        clear_active_spiderweb_goal(user_id=self.user_id)

    def test_user_phenotype_classification_and_progressive_overload_goal(self):
        """
        Verify that an athlete with high VO2 max and balanced capabilities
        is accurately classified (Pursuiter or All-Rounder) and not trapped
        as a Puncheur, and setting a phenotype goal generates progressive overload
        targets rather than 0W gaps.
        """
        from app.services.power_profile_service import classify_athlete_phenotype

        ftp = 260.0
        weight_kg = 70.0
        # Envelope where VO2 max (5m) is strong (e.g. 340W / 1.31 ratio),
        # 1m is solid (445W / 1.71 ratio), 20m is 265W (1.02 ratio), 60m is 250W (0.96 ratio), 5s is 800W (3.08 ratio)
        cur_envelope = {
            "5s": 800.0,
            "1m": 445.0,
            "5m": 340.0,
            "20m": 265.0,
            "60m": 250.0
        }

        classification = classify_athlete_phenotype(cur_envelope, ftp, weight_kg)
        # Should be Pursuiter (due to outstanding 5m weapon) or All-Rounder, NOT Puncheur
        self.assertIn(classification["title"], ["Pursuiter", "All-Rounder"])
        self.assertNotEqual(classification["title"], "Puncheur")

        # Test setting Pursuiter goal when already at or above baseline ratio
        goal_payload = {
            "goal_type": "phenotype",
            "target_key": "Pursuiter"
        }
        saved_goal = set_active_spiderweb_goal(goal_payload, user_id=self.user_id)
        # Signature axis for Pursuiter is 5m (and 1m); target should require progressive overload (+5%)
        # and not collapse to 0W delta
        self.assertGreater(saved_goal["target_envelope"]["5m"], cur_envelope["5m"] * 0.95)

        # Profile active goal should compute the remaining watts needed
        profile_with_goal = get_power_spiderweb_profile(user_id=self.user_id, timeframe="30d")
        self.assertTrue(profile_with_goal["has_active_goal"])
        self.assertGreater(profile_with_goal["active_goal"]["remaining_total_watts"], 0)

        clear_active_spiderweb_goal(user_id=self.user_id)

    def test_non_cycling_power_exclusion_from_spiderweb_and_breakthroughs(self):
        """
        Verify that non-cycling cross-training activities (e.g. running, swimming, gym)
        are analyzed for fitness and fatigue, but their power telemetry is NEVER used for
        cycling peak power envelopes, radar profile axes, or PR breakthroughs.
        """
        from app.services.strain_model_service import calculate_activity_strain, is_cycling_sport

        # 1. Verify sport classification helper
        self.assertTrue(is_cycling_sport("Ride", "Morning Group Ride"))
        self.assertTrue(is_cycling_sport("VirtualRide", "Zwift - The Pretzel"))
        self.assertTrue(is_cycling_sport("GravelRide", "Gravel Exploration"))
        self.assertFalse(is_cycling_sport("Run", "Morning 10k Tempo Run"))
        self.assertFalse(is_cycling_sport("WeightTraining", "Leg Day Hypertrophy"))
        self.assertFalse(is_cycling_sport("Swim", "Master's Swim Intervals"))

        # 2. Activity with running power meter telemetry (e.g. Stryd/Garmin 380W)
        run_act = {
            "id": "act_run_stryd_1",
            "name": "Tempo 10k Run",
            "sport_type": "Run",
            "moving_time_sec": 3000,
            "average_watts": 380,
            "weighted_average_watts": 410,
            "max_watts": 580,
            "average_heartrate": 165,
            "suffer_score": 85,
            "raw_json": json.dumps({"max_watts": 580, "device_watts": True})
        }

        # Peak powers must be 0 for all durations
        peaks = calculate_activity_peak_powers(run_act, ftp=260)
        self.assertEqual(peaks["5s"], 0)
        self.assertEqual(peaks["1m"], 0)
        self.assertEqual(peaks["5m"], 0)
        self.assertEqual(peaks["20m"], 0)
        self.assertEqual(peaks["60m"], 0)

        # But cross-training MUST be analyzed for fitness and fatigue (XSS / cardiovascular load)
        run_strain = calculate_activity_strain(run_act, ftp=260)
        self.assertTrue(run_strain["is_cross_training"])
        self.assertGreater(run_strain["total_xss"], 50.0) # Suffer score 85 accounted for
        self.assertGreater(run_strain["low_xss"], 0.0)
        self.assertEqual(run_strain["min_w_bal_pct"], 100.0) # Cycling W' battery preserved

        # 3. Insert running activity into database for user
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc)
        yesterday_date = (now - datetime.timedelta(days=1)).isoformat()
        c.execute("""
            INSERT INTO strava_activities (
                id, user_id, name, sport_type, distance_meters, moving_time_sec,
                elapsed_time_sec, total_elevation_gain, start_date,
                average_watts, weighted_average_watts, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "act_run_db_1", self.user_id, "Massive 10k Run PR", "Run", 10000, 3000,
            3000, 100, yesterday_date, 380, 410, 85, 950, json.dumps({"max_watts": 580})
        ))
        conn.commit()
        conn.close()

        # Query profile and verify breakthroughs do not include the run
        profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe="30d")
        breakthroughs = profile.get("recent_breakthroughs", [])
        for b in breakthroughs:
            self.assertNotEqual(b["activity_name"], "Massive 10k Run PR")
            self.assertNotIn("Run", b["activity_name"])

        # Verify activity breakdown includes cross-training count
        counts = profile.get("activities_count", {})
        self.assertGreaterEqual(counts.get("total_cross_training", 0), 1)

    def test_cross_training_debrief_without_cycling_ftp_distortion(self):
        """
        Verify that sports science debrief on a cross-training day evaluates
        the session as cross-training and does not treat running/gym power
        as cycling FTP overreach.
        """
        from app.services.review_coach import generate_ai_review_and_outlook

        # Query debrief for user (where recent activity includes the 10k Run)
        debrief = generate_ai_review_and_outlook()
        self.assertIsNotNone(debrief)
        # Should not crash and session list should flag cross-training
        for s in debrief.get("sessions_list", []):
            if s.get("sport_type") == "Run":
                self.assertTrue(s.get("is_cross_training"))
                self.assertIsNone(s.get("weighted_watts"))
                self.assertIsNone(s.get("pct_ftp"))

    def test_rider_type_drives_long_term_program_and_periodization(self):
        """
        Verify that Rider Type selection and spiderweb goals drive the long-term
        target envelope, target FTP, and periodization macrocycle absent a specific event,
        and cleanly transition to race taper when an event is present.
        """
        from app.services.program_service import get_current_program, update_program_goal
        from app.services.power_profile_service import set_active_spiderweb_goal, clear_active_spiderweb_goal
        from app.database import save_target_plan, clear_active_target_plans

        # Ensure no active target plan exists initially
        clear_active_target_plans(self.user_id)
        clear_active_spiderweb_goal(self.user_id)

        # 1. Set Rider Type goal to Pursuiter
        set_active_spiderweb_goal({
            "goal_type": "phenotype",
            "target_key": "Pursuiter"
        }, user_id=self.user_id)

        prog = get_current_program(user_id=self.user_id)
        self.assertFalse(prog["has_specific_event"])
        self.assertIn("Pursuiter", prog["goal_title"])
        self.assertIn("target_envelope", prog)
        self.assertIn("5m", prog["target_envelope"])
        self.assertEqual(prog["phase_4_label"], "4. Mastery & Test")
        self.assertGreater(prog["target_ftp"], prog["current_ftp"])
        self.assertEqual(prog["target_ftp"], 272)

        # 2. Update program goal via settings dropdown to Climber
        update_program_goal("CLIMBER", user_id=self.user_id)
        prog_climber = get_current_program(user_id=self.user_id)
        self.assertFalse(prog_climber["has_specific_event"])
        self.assertIn("Climber", prog_climber["goal_title"])
        self.assertEqual(prog_climber["phase_4_label"], "4. Mastery & Test")
        self.assertIn("20m", prog_climber["target_envelope"])

        # 3. Simulate adding a specific event target plan
        future_date = (datetime.date.today() + datetime.timedelta(days=42)).isoformat()
        save_target_plan({
            "title": "State Championship Road Race",
            "target_date": future_date,
            "description": "A-priority peak road race",
            "distance_miles": 65.0,
            "elevation_gain_ft": 4500.0,
            "estimated_duration_min": 180,
            "estimated_tss": 210,
            "intensity_type": "Threshold",
            "is_active": 1
        }, user_id=self.user_id)

        prog_event = get_current_program(user_id=self.user_id)
        self.assertTrue(prog_event["has_specific_event"])
        self.assertEqual(prog_event["event_title"], "State Championship Road Race")
        self.assertEqual(prog_event["phase_4_label"], "4. Taper & Fresh")

        # Cleanup
        clear_active_target_plans(self.user_id)
        clear_active_spiderweb_goal(self.user_id)

    def test_new_goal_resets_macrocycle_block_timeline(self):
        """
        Verify that selecting a new Rider Type goal resets an old block countdown
        (e.g. 8 days remaining) to Week 1 (56 days remaining, Base Phase),
        and verify the /api/program/reset-block endpoint.
        """
        from app.database import set_setting, clear_active_target_plans
        from app.services.power_profile_service import set_active_spiderweb_goal, clear_active_spiderweb_goal
        from app.services.program_service import get_current_program

        clear_active_target_plans(self.user_id)
        clear_active_spiderweb_goal(self.user_id)

        # 1. Simulate an old block that is almost finished (8 days remaining)
        today = datetime.date.today()
        old_target = (today + datetime.timedelta(days=8)).isoformat()
        old_start = (today - datetime.timedelta(days=48)).isoformat()
        set_setting("program_target_date", old_target, user_id=self.user_id)
        set_setting("program_start_date", old_start, user_id=self.user_id)

        old_prog = get_current_program(user_id=self.user_id)
        self.assertEqual(old_prog["days_remaining"], 8)
        self.assertEqual(old_prog["current_week"], 7)

        # 2. Select new rider type goal with reset_block=False (athlete declines block reset)
        set_active_spiderweb_goal({
            "goal_type": "phenotype",
            "target_key": "Rouleur",
            "reset_block": False
        }, user_id=self.user_id)

        prog_declined = get_current_program(user_id=self.user_id)
        self.assertIn("Rouleur", prog_declined["goal_title"])
        # Timeline remains unchanged because reset was declined
        self.assertEqual(prog_declined["days_remaining"], 8)
        self.assertEqual(prog_declined["current_week"], 7)

        # 3. Select new rider type goal with reset_block=True (athlete confirms block reset)
        set_active_spiderweb_goal({
            "goal_type": "phenotype",
            "target_key": "Rouleur",
            "reset_block": True
        }, user_id=self.user_id)

        new_prog = get_current_program(user_id=self.user_id)
        self.assertEqual(new_prog["days_remaining"], 56)
        self.assertEqual(new_prog["total_weeks"], 8)
        self.assertEqual(new_prog["current_week"], 1)
        self.assertEqual(new_prog["phase"], "Base Phase")

        # 4. Test explicit reset endpoint
        # Artificially shift dates again
        set_setting("program_target_date", old_target, user_id=self.user_id)
        res = self.client.post("/api/program/reset-block", json={"block_weeks": 8}, headers={"X-User-ID": self.user_id})
        self.assertEqual(res.status_code, 200)
        res_data = res.json()
        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["program"]["days_remaining"], 56)
        self.assertEqual(res_data["program"]["current_week"], 1)

        # Cleanup
        clear_active_spiderweb_goal(self.user_id)

    def test_is_cycling_sport_indoor_intervals_and_telemetry(self):
        from app.services.strain_model_service import is_cycling_sport
        # Test 1: Ride with 3 blocks of ~14 minutes at 215+
        self.assertTrue(is_cycling_sport("Workout", "3 blocks of ~14 minutes at 215+", average_watts=218))
        self.assertTrue(is_cycling_sport("IndoorCycling", "3 blocks of ~14 minutes at 215+"))
        self.assertTrue(is_cycling_sport("VirtualRide", "Watopia Flat Route"))
        self.assertTrue(is_cycling_sport("Ride", "Morning Coffee Spin"))
        self.assertTrue(is_cycling_sport("Spinning", "Peloton 45 min Power Zone"))
        self.assertTrue(is_cycling_sport("workout", "Indoor Trainer Session", average_watts=215, kilojoules=720))

        # Test 2: Non-cycling activities must be excluded
        self.assertFalse(is_cycling_sport("Run", "Morning 5k Run"))
        self.assertFalse(is_cycling_sport("Workout", "Leg Day Gym Workout"))
        self.assertFalse(is_cycling_sport("Swim", "Pool Laps"))
        self.assertFalse(is_cycling_sport("Walk", "Evening Dog Walk"))

    def test_interval_blocks_peak_power_calculation(self):
        # 3 blocks of 14 minutes (840s) at 218W
        laps = [
            {"moving_time": 840, "average_watts": 218.0},
            {"moving_time": 180, "average_watts": 120.0},
            {"moving_time": 840, "average_watts": 222.0},
            {"moving_time": 180, "average_watts": 120.0},
            {"moving_time": 840, "average_watts": 215.0}
        ]
        activity = {
            "name": "3 blocks of ~14 minutes at 215+",
            "sport_type": "Workout",
            "moving_time_sec": 2900,
            "average_watts": 195.0,
            "weighted_average_watts": 212.0,
            "raw_json": json.dumps({"laps": laps, "device_watts": True, "max_watts": 450})
        }
        peaks = calculate_activity_peak_powers(activity, ftp=250)
        # 5m power should reflect the >215W sustained block
        self.assertGreaterEqual(peaks["5m"], 215)
        # 20m power should reflect the ~215W interval load
        self.assertGreaterEqual(peaks["20m"], 205)

    def test_timeline_buckets_consistent_ride_counts(self):
        # Test profile generation timeline buckets
        profile = get_power_spiderweb_profile(user_id=self.user_id, timeframe="all_time")
        timeline = profile.get("progression_timeline", [])
        self.assertGreater(len(timeline), 0)
        for b in timeline:
            self.assertIn("cycling_count", b)
            self.assertIn("cycling_hours", b)
            self.assertIn("cross_training_count", b)
            self.assertEqual(b["workout_count"], b["cycling_count"] + b["cross_training_count"])


if __name__ == "__main__":
    unittest.main()



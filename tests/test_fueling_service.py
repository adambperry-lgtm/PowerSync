import unittest
from app.services.fueling_service import generate_fueling_plan


class TestFuelingService(unittest.TestCase):
    def test_63_min_mild_ride_folds_tail_and_omits_salt_capsules(self):
        plan = generate_fueling_plan(
            duration_min=63,
            avg_power_watts=185,
            ftp=250,
            temp_f=52,
            humidity_pct=50,
            is_outdoor=True,
        )
        schedule = plan["hourly_timeline"]
        # 63m folds the 3-min tail into Hour 1 (0-63 min)
        self.assertEqual(len(schedule), 1)
        h1 = schedule[0]
        self.assertEqual(h1["label"], "Hour 1 (0–63 min)")
        self.assertEqual(h1["fuel_items"][0]["time"], "Min 0–63")
        self.assertEqual(sum(i["carbs"] for i in h1["fuel_items"]), h1["carbs_g"])

        checklist_items = [c["item"] for c in plan["packing_checklist"]]
        self.assertFalse(any("Salt Capsules" in item for item in checklist_items))

    def test_105_min_ride_uses_ride_clock_timestamps_in_hour_2(self):
        plan = generate_fueling_plan(
            duration_min=105,
            avg_power_watts=195,
            ftp=250,
            temp_f=65,
            humidity_pct=50,
            is_outdoor=True,
        )
        schedule = plan["hourly_timeline"]
        self.assertEqual(len(schedule), 2)
        h1, h2 = schedule[0], schedule[1]
        self.assertEqual(h1["label"], "Hour 1 (0–60 min)")
        self.assertEqual(h2["label"], "Hour 2 (60–105 min)")
        self.assertEqual(sum(i["carbs"] for i in h1["fuel_items"]), h1["carbs_g"])
        self.assertEqual(sum(i["carbs"] for i in h2["fuel_items"]), h2["carbs_g"])
        # Hour 2 timestamps must be >= 60 (actual ride clock, not Min 15 / Min 40)
        for item in h2["fuel_items"]:
            self.assertNotIn("Min 15", item["time"])
            self.assertNotIn("Min 40", item["time"])

    def test_salt_capsules_only_for_very_hot_and_humid_outdoor_rides(self):
        hot_humid = generate_fueling_plan(duration_min=90, temp_f=86, humidity_pct=70, is_outdoor=True)
        self.assertTrue(any("Salt Capsules" in c["item"] for c in hot_humid["packing_checklist"]))

        indoor_hot = generate_fueling_plan(duration_min=90, temp_f=86, humidity_pct=70, is_outdoor=False)
        self.assertFalse(any("Salt Capsules" in c["item"] for c in indoor_hot["packing_checklist"]))

        november_ride = generate_fueling_plan(duration_min=90, temp_f=48, humidity_pct=55, is_outdoor=True)
        self.assertFalse(any("Salt Capsules" in c["item"] for c in november_ride["packing_checklist"]))

    def test_60_min_35g_ride_packing_list_matches_bottle_only_protocol(self):
        plan = generate_fueling_plan(
            duration_min=60,
            avg_power_watts=170,
            ftp=250,
            intensity_type="Endurance",
            is_outdoor=False,
            recovery_score=92,
            trailing_strain_avg=10.0,
            yesterday_tss=37,
        )
        self.assertEqual(plan["target_rates"]["carbs_per_hour_g"], 35)
        self.assertEqual(plan["target_rates"]["total_carbs_g"], 35)
        self.assertEqual(plan["target_rates"]["fluid_ml_per_hour"], 747)

        checklist = plan["packing_checklist"]
        items = [c["item"] for c in checklist]
        # 1 bottle + 35g carb drink mix only; no extra gel or solid that would exceed 35g
        self.assertTrue(any("1x 750ml Cycling Water Bottle" == it for it in items))
        self.assertTrue(any("Carb Drink Mix (35g carbs)" == it for it in items))
        self.assertFalse(any("Gel" in it for it in items))
        self.assertFalse(any("Solid" in it for it in items))
        self.assertEqual(sum(c["carbs_g"] for c in checklist), 35)

    def test_short_ride_zero_carbs_omits_carb_mix_and_gels(self):
        plan = generate_fueling_plan(
            duration_min=30,
            avg_power_watts=160,
            ftp=250,
            is_outdoor=False,
            recovery_score=80,
        )
        self.assertEqual(plan["target_rates"]["total_carbs_g"], 0)
        checklist = plan["packing_checklist"]
        self.assertEqual(len(checklist), 1)
        self.assertEqual(checklist[0]["item"], "1x 750ml Cycling Water Bottle")
        self.assertIn("0g carbs", checklist[0]["detail"])
        self.assertEqual(sum(c["carbs_g"] for c in checklist), 0)

    def test_packing_checklist_always_matches_hourly_timeline_and_total_carbs(self):
        durations = [30, 45, 60, 63, 75, 90, 105, 120, 150, 180, 210, 240]
        intensities = ["Recovery", "Endurance", "Tempo", "Hard"]
        recoveries = [30, 85]

        for dur in durations:
            for intensity in intensities:
                for rec in recoveries:
                    plan = generate_fueling_plan(
                        duration_min=dur,
                        ftp=250,
                        intensity_type=intensity,
                        is_outdoor=True,
                        temp_f=70,
                        humidity_pct=50,
                        recovery_score=rec,
                    )
                    total_target = plan["target_rates"]["total_carbs_g"]
                    timeline_sum = sum(h["carbs_g"] for h in plan["hourly_timeline"])
                    items_sum = sum(
                        it["carbs"]
                        for h in plan["hourly_timeline"]
                        for it in h["fuel_items"]
                    )
                    checklist_sum = sum(c["carbs_g"] for c in plan["packing_checklist"])

                    self.assertEqual(
                        timeline_sum,
                        total_target,
                        f"Timeline sum mismatch for dur={dur}, intensity={intensity}, rec={rec}",
                    )
                    self.assertEqual(
                        items_sum,
                        total_target,
                        f"Fuel items sum mismatch for dur={dur}, intensity={intensity}, rec={rec}",
                    )
                    self.assertEqual(
                        checklist_sum,
                        total_target,
                        f"Packing checklist sum mismatch for dur={dur}, intensity={intensity}, rec={rec}",
                    )

                    # Verify gels only appear in checklist when scheduled in hourly_timeline
                    scheduled_gels = sum(
                        1
                        for h in plan["hourly_timeline"]
                        for it in h["fuel_items"]
                        if "Gel" in it["item"]
                    )
                    has_gel_in_checklist = any("Gel" in c["item"] for c in plan["packing_checklist"])
                    self.assertEqual(
                        has_gel_in_checklist,
                        scheduled_gels > 0,
                        f"Gel mismatch for dur={dur}, intensity={intensity}, rec={rec}",
                    )


if __name__ == "__main__":
    unittest.main()

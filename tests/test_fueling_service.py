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


if __name__ == "__main__":
    unittest.main()

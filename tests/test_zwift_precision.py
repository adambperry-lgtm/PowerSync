import math
import unittest
import xml.etree.ElementTree as ET
from app.services.zwift_service import _calculate_zwo_power, generate_zwo_xml, generate_intervals_icu_text

class TestZwiftPowerPrecision(unittest.TestCase):
    def test_calculate_zwo_power_exact_integer_match(self):
        """Verifies _calculate_zwo_power matches JS Math.round and eliminates 1W truncation drops in Zwift."""
        for ftp in [200, 250, 267, 270, 275, 285, 288, 315, 330]:
            for pct in range(40, 130):
                # Frontend app.js uses Math.round(ftp * (pct / 100)) which is floor(x + 0.5)
                app_target_watts = math.floor(ftp * (pct / 100.0) + 0.5)
                power_ratio = _calculate_zwo_power(pct, ftp)
                
                # Zwift's game engine uses integer truncation / floor on floating power values
                zwift_trunc_watts = int(ftp * power_ratio)
                zwift_round_watts = math.floor(ftp * power_ratio + 0.5)
                
                self.assertEqual(
                    zwift_trunc_watts,
                    app_target_watts,
                    f"Truncation mismatch at FTP {ftp}W, {pct}%: expected {app_target_watts}W, got {zwift_trunc_watts}W (ratio {power_ratio})"
                )
                self.assertEqual(
                    zwift_round_watts,
                    app_target_watts,
                    f"Rounding mismatch at FTP {ftp}W, {pct}%: expected {app_target_watts}W, got {zwift_round_watts}W (ratio {power_ratio})"
                )

    def test_generate_zwo_xml_target_power_attributes(self):
        """Verifies exported .zwo XML maintains exact target watts for Sweet Spot, Threshold, and Repeats."""
        ftp = 275
        workout = {
            "title": "Sweet Spot 45m Sustained",
            "duration_minutes": 45,
            "intervals": [
                {"type": "Warmup", "duration_sec": 360, "power_low_pct": 45, "power_high_pct": 75, "cadence": 88},
                {"type": "SteadyState", "duration_sec": 720, "power_pct": 89, "cadence": 90, "name": "Sweet Spot 1"},
                {"type": "SteadyState", "duration_sec": 180, "power_pct": 55, "cadence": 85, "name": "Recovery"},
                {"type": "Repeats", "repeat": 3, "on_duration_sec": 60, "off_duration_sec": 30, "on_power_pct": 105, "off_power_pct": 50},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 40, "cadence": 82}
            ]
        }
        
        xml_str = generate_zwo_xml(workout, ftp)
        root = ET.fromstring(xml_str)
        
        # 1. Warmup: 45% -> 75%
        warmup = root.find(".//Warmup")
        self.assertIsNotNone(warmup)
        p_low = float(warmup.get("PowerLow"))
        p_high = float(warmup.get("PowerHigh"))
        self.assertEqual(int(ftp * p_low), math.floor(ftp * 0.45 + 0.5))
        self.assertEqual(int(ftp * p_high), math.floor(ftp * 0.75 + 0.5))
        
        # 2. SteadyState: 89% (245W for 275 FTP)
        steady = root.find(".//SteadyState")
        self.assertIsNotNone(steady)
        p_steady = float(steady.get("Power"))
        expected_steady_watts = math.floor(ftp * 0.89 + 0.5)  # 245W
        self.assertEqual(int(ftp * p_steady), expected_steady_watts)
        
        # 3. IntervalsT: 105% (289W) / 50% (138W)
        intervals_t = root.find(".//IntervalsT")
        self.assertIsNotNone(intervals_t)
        on_p = float(intervals_t.get("OnPower"))
        off_p = float(intervals_t.get("OffPower"))
        self.assertEqual(int(ftp * on_p), math.floor(ftp * 1.05 + 0.5))
        self.assertEqual(int(ftp * off_p), math.floor(ftp * 0.50 + 0.5))

    def test_intervals_icu_text_preserves_zwift_target_watts(self):
        """Verifies Intervals.icu text uses precision-compensated % so Zwift sync never drops 1W (e.g. 200W -> 199W)."""
        ftp = 270
        workout = {
            "title": "200W Endurance Test",
            "duration_minutes": 30,
            "intervals": [
                {"type": "SteadyState", "duration_sec": 1800, "power_pct": 74, "name": "Steady 200W"}
            ]
        }
        text = generate_intervals_icu_text(workout, ftp=ftp)
        # 270 * 0.74 = 199.8 -> app displays 200W; precision-compensated pct is 74.17% -> 270 * 0.7417 = 200.259 -> 200W in Zwift
        self.assertIn("74.17%", text)

if __name__ == "__main__":
    unittest.main()

import pytest
import os
from app.services.strain_model_service import get_coggan_power_zones
from app.services.workout_catalog import (
    build_sweet_spot_sustained,
    build_sweet_spot_over_under,
    build_tempo_cadence_ladders,
    build_vo2_repeats_3min,
    build_endurance_steady
)
from app.routers.dashboard import get_dashboard_data

def test_coggan_7_zone_structure_and_percentages():
    """Validates that Coggan 7-Zone system contains all 7 zones and Sweet Spot sub-zone."""
    zones = get_coggan_power_zones(ftp=250, peak_power=1050)
    
    assert "z1" in zones
    assert "z2" in zones
    assert "z3" in zones
    assert "sweet_spot" in zones
    assert "z4" in zones
    assert "z5" in zones
    assert "z6" in zones
    assert "z7" in zones

    # Percentage definitions
    assert zones["z1"]["max_pct"] == 55
    assert zones["z2"]["min_pct"] == 56 and zones["z2"]["max_pct"] == 75
    assert zones["z3"]["min_pct"] == 76 and zones["z3"]["max_pct"] == 90
    assert zones["sweet_spot"]["min_pct"] == 88 and zones["sweet_spot"]["max_pct"] == 94
    assert zones["z4"]["min_pct"] == 91 and zones["z4"]["max_pct"] == 105
    assert zones["z5"]["min_pct"] == 106 and zones["z5"]["max_pct"] == 120
    assert zones["z6"]["min_pct"] == 121 and zones["z6"]["max_pct"] == 150
    assert zones["z7"]["min_pct"] == 151

def test_coggan_power_zones_wattage_at_250w():
    """Validates exact wattage calculations at 250W FTP (the user's FTP)."""
    zones = get_coggan_power_zones(ftp=250, peak_power=1050)

    # Z1 Active Recovery (< 55%): < 138W
    assert zones["z1"]["max_watts"] == 138

    # Z2 Endurance (56-75%): 140 - 188W
    assert zones["z2"]["min_watts"] == 140
    assert zones["z2"]["max_watts"] == 188

    # Z3 Tempo (76-90%): 190 - 225W (No longer missing!)
    assert zones["z3"]["min_watts"] == 190
    assert zones["z3"]["max_watts"] == 225

    # Sweet Spot Sub-Zone (88-94%): 220 - 235W
    assert zones["sweet_spot"]["min_watts"] == 220
    assert zones["sweet_spot"]["max_watts"] == 235

    # Z4 Lactate Threshold (91-105%): 228 - 262W (Fills the gap!)
    assert zones["z4"]["min_watts"] == 228
    assert zones["z4"]["max_watts"] == round(250 * 1.05)

    # Z5 VO2 Max (106-120%): 265 - 300W
    assert zones["z5"]["min_watts"] == 265
    assert zones["z5"]["max_watts"] == 300

    # Z6 Anaerobic Capacity (121-150%): 302 - 375W
    assert zones["z6"]["min_watts"] == round(250 * 1.21)
    assert zones["z6"]["max_watts"] == 375

    # Z7 Neuromuscular (> 150%): > 375W up to 1050W
    assert zones["z7"]["min_watts"] == 378
    assert zones["z7"]["max_watts"] == 1050

def test_dashboard_api_returns_power_zones():
    """Ensures get_dashboard_data returns the full Coggan power_zones dictionary in athlete object."""
    data = get_dashboard_data()
    assert isinstance(data, dict)
    athlete = data.get("athlete", {})
    assert "power_zones" in athlete
    pz = athlete["power_zones"]
    assert "z1" in pz
    assert "z2" in pz
    assert "z3" in pz
    assert "sweet_spot" in pz
    assert "z4" in pz
    assert "z5" in pz
    assert "z6" in pz
    assert "z7" in pz

def test_prescribed_rides_use_exact_ftp_percentages_not_ui_zones():
    """
    Verifies that workouts are generated with direct physiological FTP percentages,
    proving that prescribed rides were never compromised by the incomplete 3-tile UI display.
    """
    ftp = 250

    # Sweet Spot sustained: 88-92% FTP
    ss_workout = build_sweet_spot_sustained(duration_min=45, ftp=ftp)
    steady_steps = [s for s in ss_workout["intervals"] if s.get("type") == "SteadyState" and s.get("power_pct", 0) > 60]
    for step in steady_steps:
        assert 88 <= step["power_pct"] <= 92

    # Over-unders: 95% over / 88% under
    ou_workout = build_sweet_spot_over_under(duration_min=45, ftp=ftp)
    rep_steps = [s for s in ou_workout["intervals"] if s.get("type") == "Repeats"]
    assert len(rep_steps) > 0
    assert rep_steps[0]["on_power_pct"] == 95
    assert rep_steps[0]["off_power_pct"] == 88

    # Tempo: 78-84% FTP
    tempo_workout = build_tempo_cadence_ladders(duration_min=45, ftp=ftp)
    tempo_steps = [s for s in tempo_workout["intervals"] if s.get("type") == "SteadyState" and s.get("power_pct", 0) > 60]
    for step in tempo_steps:
        assert 78 <= step["power_pct"] <= 85

    # VO2 Max repeats: 112-115% FTP
    vo2_workout = build_vo2_repeats_3min(duration_min=45, ftp=ftp)
    vo2_steps = [s for s in vo2_workout["intervals"] if s.get("type") == "SteadyState" and s.get("power_pct", 0) > 100]
    for step in vo2_steps:
        assert 110 <= step["power_pct"] <= 120

    # Endurance: 65-68% FTP
    endurance_workout = build_endurance_steady(duration_min=60, ftp=ftp)
    endurance_steps = [s for s in endurance_workout["intervals"] if s.get("type") == "SteadyState"]
    for step in endurance_steps:
        assert 65 <= step["power_pct"] <= 70

def test_ui_contains_all_7_coggan_zones_and_sweet_spot():
    """Verifies that index.html contains all 7 Coggan zones and Sweet Spot callout."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    html_path = os.path.join(base_dir, "app", "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="rangeZ1"' in html
    assert 'id="rangeZ2"' in html
    assert 'id="rangeZ3"' in html
    assert 'id="rangeSweetSpot"' in html
    assert 'id="rangeZ4"' in html
    assert 'id="rangeZ5"' in html
    assert 'id="rangeZ6"' in html
    assert 'id="rangeZ7"' in html
    assert 'Z1 Active Recovery' in html
    assert 'Z2 Endurance' in html
    assert 'Z3 Tempo' in html
    assert 'Z4 Lactate Threshold' in html
    assert 'Z5 VO2 Max' in html
    assert 'Z6 Anaerobic Capacity' in html
    assert 'Z7 Neuromuscular' in html

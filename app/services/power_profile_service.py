import math
import datetime
import json
from typing import Dict, Any, List, Optional, Tuple
from app.database import (
    get_db_connection,
    get_setting,
    set_setting,
    delete_setting,
    get_current_user_id,
    get_athlete_date,
    resolve_strava_local_start
)
from app.services.strain_model_service import get_athlete_fitness_signature, is_cycling_sport

RADAR_DURATIONS = [
    {"key": "5s", "label": "5s Sprint", "sec": 5, "name": "Sprint (5s)", "icon": "⚡", "energy": "Neuromuscular"},
    {"key": "1m", "label": "1m Anaerobic", "sec": 60, "name": "Anaerobic (1m)", "icon": "💥", "energy": "Glycolytic"},
    {"key": "5m", "label": "5m VO2 Max", "sec": 300, "name": "VO2 Max (5m)", "icon": "🫁", "energy": "Aerobic Ceiling"},
    {"key": "20m", "label": "20m Threshold", "sec": 1200, "name": "Threshold (20m)", "icon": "⏱️", "energy": "Lactate Equilibrium"},
    {"key": "60m", "label": "60m Stamina", "sec": 3600, "name": "Stamina (60m)", "icon": "🚴", "energy": "Aerobic Endurance"},
]

# --- Rider Phenotype Definitions (Coggan Power Profiling Model) ---

RIDER_PHENOTYPE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "Puncheur",
        "title": "Puncheur",
        "badge": "🥊 Puncheur",
        "icon": "🥊",
        "description": "High-octane anaerobic battery (W') capable of violent steep hill attacks and sharp short climbs.",
        "primary_strength": "1m–3m Glycolytic Power & Attack Repeatability",
        "growth_focus": "Sub-Threshold Glycogen Sparing",
        "focus_energy_system": "1m–3m Glycolytic Capacity & Anaerobic Power (W')",
        "signature_axes": ["1m", "5m"],
        "recommended_workouts": [
            "30/30s High-Cadence VO2 Microbursts (120% FTP / 50% recovery)",
            "5x 2-Min Steep Anaerobic Hill Repeats (125-130% FTP)",
            "Tabata High-Torque Acceleration Blocks"
        ],
        "requirements": {
            "5s_ratio": 2.80,
            "1m_ratio": 1.72,
            "5m_ratio": 1.22,
            "20m_ratio": 0.98,
            "60m_ratio": 0.86
        }
    },
    {
        "id": "Rouleur",
        "title": "Rouleur / TT Specialist",
        "badge": "⏱️ Rouleur",
        "icon": "⏱️",
        "description": "Diesel engine with massive sustained aerobic power and fatigue resistance over prolonged durations.",
        "primary_strength": "20m–60m Sustained Lactate Threshold",
        "growth_focus": "High-Intensity Neuromuscular Snap",
        "focus_energy_system": "Lactate Clearance & Aerobic Threshold (FTP)",
        "signature_axes": ["20m", "60m"],
        "recommended_workouts": [
            "2x 20-Min Progressive Sweet Spot (88–94% FTP)",
            "3x 12-Min Threshold Over-Unders (95% / 105% FTP)",
            "75-Min Aerobic Tempo Density Ride"
        ],
        "requirements": {
            "5s_ratio": 2.40,
            "1m_ratio": 1.45,
            "5m_ratio": 1.16,
            "20m_ratio": 1.04,
            "60m_ratio": 0.94
        }
    },
    {
        "id": "Climber",
        "title": "Climber",
        "badge": "⛰️ Climber",
        "icon": "⛰️",
        "description": "Exceptional power-to-weight ratio over extended elevation gradients and sustained mountain passes.",
        "primary_strength": "High Sustained W/kg Output on Gradients",
        "growth_focus": "Flat Wind Sprint Snap",
        "focus_energy_system": "Sustained W/kg & High Aerobic Ceiling",
        "signature_axes": ["20m", "5m"],
        "recommended_workouts": [
            "4x 10-Min High-Cadence Alpine Threshold Repeats (96–102% FTP)",
            "5x 4-Min VO2 Max Climbing Ladders (110–115% FTP)",
            "2-Hour Endurance Mountain Simulation"
        ],
        "requirements": {
            "5s_ratio": 2.50,
            "1m_ratio": 1.50,
            "5m_ratio": 1.25,
            "20m_ratio": 1.04,
            "60m_ratio": 0.90,
            "min_20m_wkg": 3.85,
            "min_5m_wkg": 4.90
        }
    },
    {
        "id": "Sprinter",
        "title": "Sprinter",
        "badge": "⚡ Sprinter",
        "icon": "⚡",
        "description": "Explosive neuromuscular recruitment and fast-twitch power. Dominates final kicks and short accelerations.",
        "primary_strength": "5s Sprint & Max Neuromuscular Burst",
        "growth_focus": "Aerobic Threshold Extension (20m+)",
        "focus_energy_system": "Neuromuscular Recruitment & Peak Sprint P_max",
        "signature_axes": ["5s", "1m"],
        "recommended_workouts": [
            "6x 15s All-Out Standing Start Sprints with 4m Recovery",
            "3 Blocks of 30s High-Torque Acceleration Spin-Ups",
            "Heavy Resistance Squat & Plyometric Priming"
        ],
        "requirements": {
            "5s_ratio": 3.45,
            "1m_ratio": 1.72,
            "5m_ratio": 1.15,
            "20m_ratio": 0.95,
            "60m_ratio": 0.82
        }
    },
    {
        "id": "Pursuiter",
        "title": "Pursuiter / VO2 Specialist",
        "badge": "🫁 Pursuiter",
        "icon": "🫁",
        "description": "Huge maximal aerobic ceiling (MAP). Excels at bridge attempts, breakaway pacing, and 3-8 minute climbs.",
        "primary_strength": "5m Maximal Aerobic Power (MAP)",
        "growth_focus": "Neuromuscular Peak Sprint P_max",
        "focus_energy_system": "Maximal Aerobic Power (MAP) & Stroke Volume",
        "signature_axes": ["5m", "1m"],
        "recommended_workouts": [
            "5x 4-Min Maximal Aerobic Power (MAP @ 112–118% FTP)",
            "4x 5-Min VO2 Max Extenders with 1:1 Recovery",
            "40/20s High-Intensity Interval Sets"
        ],
        "requirements": {
            "5s_ratio": 2.65,
            "1m_ratio": 1.60,
            "5m_ratio": 1.28,
            "20m_ratio": 0.98,
            "60m_ratio": 0.88
        }
    },
    {
        "id": "All-Rounder",
        "title": "All-Rounder",
        "badge": "🎯 All-Rounder",
        "icon": "🎯",
        "description": "Well-balanced spiderweb with harmonious capabilities across sprint, anaerobic capacity, and sustained threshold.",
        "primary_strength": "Versatile Energy System Equilibrium",
        "growth_focus": "Specialized Peak Power Polarization",
        "focus_energy_system": "Harmonious Multi-System Progression (+5% Envelope Lift)",
        "signature_axes": ["5s", "1m", "5m", "20m", "60m"],
        "recommended_workouts": [
            "Weekly Polarized Mix: 1x VO2 Intervals, 1x Sweet Spot, 2x Z2 Base",
            "Over-Under Threshold Ladders",
            "Weekend Long Aerobic Simulation"
        ],
        "requirements": {
            "5s_ratio": 2.85,
            "1m_ratio": 1.58,
            "5m_ratio": 1.20,
            "20m_ratio": 1.00,
            "60m_ratio": 0.88
        }
    }
]


def classify_athlete_phenotype(cur_envelope: Dict[str, int], ftp: int, weight_kg: float) -> Dict[str, Any]:
    """
    Evaluates multi-axis power profile distribution to classify athlete phenotype
    (Sprinter, Puncheur, Pursuiter, Rouleur, Climber, All-Rounder) based on Coggan
    power profiling principles and relative energy system balance.
    """
    safe_ftp = max(1.0, float(ftp))
    safe_weight = max(40.0, float(weight_kg))
    wkg_20m = cur_envelope.get("20m", 0) / safe_weight
    wkg_5m = cur_envelope.get("5m", 0) / safe_weight

    pheno_map = {p["id"]: p for p in RIDER_PHENOTYPE_DEFINITIONS}

    # Neutral reference ratios across the 5 domains (population baseline)
    neutral_ratios = {"5s": 2.80, "1m": 1.58, "5m": 1.20, "20m": 1.00, "60m": 0.88}
    r_vals = [cur_envelope.get(k, 0) / (safe_ftp * neutral_ratios[k]) for k in neutral_ratios]
    mean_r = sum(r_vals) / len(r_vals)
    variance = sum((x - mean_r) ** 2 for x in r_vals) / len(r_vals)
    std_dev = math.sqrt(variance)

    scores: Dict[str, float] = {}
    readiness_map: Dict[str, float] = {}

    for pheno in RIDER_PHENOTYPE_DEFINITIONS:
        p_id = pheno["id"]
        reqs = pheno["requirements"]
        sig_axes = pheno.get("signature_axes", [])

        # Calculate axis fulfillments
        axis_scores = []
        axis_readiness = []
        weights = []

        for k in ["5s", "1m", "5m", "20m", "60m"]:
            req_w = safe_ftp * reqs.get(f"{k}_ratio", 1.0)
            curr_w = cur_envelope.get(k, 0)
            fulf = min(1.15, curr_w / max(1.0, req_w))
            w = 2.5 if k in sig_axes else 1.0
            axis_scores.append(fulf * w)
            axis_readiness.append(min(100.0, (curr_w / max(1.0, req_w)) * 100.0) * w)
            weights.append(w)

        base_score = sum(axis_scores) / sum(weights)
        readiness = sum(axis_readiness) / sum(weights)

        # Signature weapon bonus:
        if sig_axes:
            primary_sig = sig_axes[0]
            sig_req_w = safe_ftp * reqs.get(f"{primary_sig}_ratio", 1.0)
            sig_ratio = cur_envelope.get(primary_sig, 0) / max(1.0, sig_req_w)
            if sig_ratio >= 1.0:
                base_score += (sig_ratio - 1.0) * 0.45 + 0.03

        # Climber W/kg addition
        if p_id == "Climber":
            wkg_fulf = (min(1.15, wkg_20m / 3.85) + min(1.15, wkg_5m / 4.90)) / 2.0
            base_score = base_score * 0.4 + wkg_fulf * 0.6
            readiness = readiness * 0.4 + ((min(1.0, wkg_20m / 3.85) + min(1.0, wkg_5m / 4.90)) / 2.0 * 100.0) * 0.6
            if wkg_20m >= 3.85 and wkg_5m >= 4.90:
                base_score += ((wkg_20m / 3.85 - 1.0) + (wkg_5m / 4.90 - 1.0)) * 0.45 + 0.05

        # All-Rounder equilibrium bonus
        if p_id == "All-Rounder":
            if std_dev <= 0.075:
                base_score += (0.075 - std_dev) * 0.8 + 0.02

        scores[p_id] = round(base_score, 4)
        readiness_map[p_id] = round(min(100.0, readiness), 1)

    best_id = max(scores, key=scores.get)
    best_pheno = pheno_map[best_id]

    return {
        "title": best_pheno["title"],
        "badge": best_pheno["badge"],
        "icon": best_pheno["icon"],
        "description": best_pheno["description"],
        "primary_strength": best_pheno["primary_strength"],
        "growth_focus": best_pheno.get("growth_focus", "Harmonious Multi-System Progression"),
        "affinity_scores": scores,
        "readiness_map": readiness_map,
        "std_dev": round(std_dev, 3)
    }


def calculate_activity_peak_powers(
    act: Dict[str, Any],
    ftp: int = 250,
    w_prime_kj: float = 20.0,
    peak_power_watts: int = 1050
) -> Dict[str, int]:
    """
    Computes realistic peak power profile (5s, 30s, 1m, 5m, 20m, 60m) for an activity.
    Uses power meter telemetry (device_watts, max_watts), interval laps and segments,
    and applies physiological duration gating with Morton CP / W' intensity attenuation.
    Guarantees non-cycling activities (runs, swims, gym) never produce cycling power data.
    """
    sport = act.get("sport_type") or act.get("type", "")
    act_name = act.get("name", "")
    if not is_cycling_sport(sport, act_name):
        return {"5s": 0, "30s": 0, "1m": 0, "5m": 0, "20m": 0, "60m": 0}

    moving_sec = int(act.get("moving_time_sec") or 0)
    avg_w = float(act.get("average_watts") or 0.0)
    np_w = float(act.get("weighted_average_watts") or avg_w)

    raw_json = act.get("raw_json")
    max_w = 0.0
    device_watts = False
    laps_peaks: Dict[str, float] = {}

    if raw_json:
        try:
            raw_parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            if isinstance(raw_parsed, dict):
                max_w = float(raw_parsed.get("max_watts") or 0.0)
                device_watts = bool(raw_parsed.get("device_watts", False))
                # Check recorded laps and segment efforts for real interval peaks
                for lap in raw_parsed.get("laps") or []:
                    l_sec = int(lap.get("moving_time") or lap.get("elapsed_time") or 0)
                    l_w = float(lap.get("average_watts") or 0.0)
                    if 45 <= l_sec <= 90 and l_w > laps_peaks.get("1m", 0):
                        laps_peaks["1m"] = l_w
                    if 240 <= l_sec <= 360 and l_w > laps_peaks.get("5m", 0):
                        laps_peaks["5m"] = l_w
                    if 1000 <= l_sec <= 1400 and l_w > laps_peaks.get("20m", 0):
                        laps_peaks["20m"] = l_w
                for seg in raw_parsed.get("segment_efforts") or []:
                    s_sec = int(seg.get("moving_time") or seg.get("elapsed_time") or 0)
                    s_w = float(seg.get("average_watts") or 0.0)
                    if 45 <= s_sec <= 90 and s_w > laps_peaks.get("1m", 0):
                        laps_peaks["1m"] = s_w
                    if 240 <= s_sec <= 360 and s_w > laps_peaks.get("5m", 0):
                        laps_peaks["5m"] = s_w
                    if 1000 <= s_sec <= 1400 and s_w > laps_peaks.get("20m", 0):
                        laps_peaks["20m"] = s_w
        except Exception:
            pass

    if moving_sec < 5 or (np_w <= 0 and avg_w <= 0 and max_w <= 0):
        return {"5s": 0, "30s": 0, "1m": 0, "5m": 0, "20m": 0, "60m": 0}

    w_prime_j = w_prime_kj * 1000.0
    intensity = max(0.40, min(1.15, np_w / max(1.0, float(ftp))))

    # 1. 5s Sprint: True burst from power meter or intensity-calibrated sprint
    if max_w > 0:
        p_5s = round(min(max_w, max_w * 0.96))
        if not device_watts and max_w < np_w:
            p_5s = round(max(max_w, np_w * 1.35))
    else:
        p_5s = round(min(float(peak_power_watts), np_w * 1.45))

    # 2. 30s Burst: High anaerobic capacity
    if moving_sec < 30:
        p_30s = 0
    else:
        est_30s = np_w * 1.25 + (w_prime_j / 30.0) * 0.40 * intensity
        p_30s = round(min(p_5s * 0.85, max(np_w * 1.15, est_30s))) if p_5s > 0 else round(est_30s)

    # 3. 1m Anaerobic: Glycolytic peak (respects real intervals and intensity)
    if moving_sec < 60:
        p_1m = 0
    else:
        est_1m = np_w * 1.15 + (w_prime_j / 60.0) * 0.45 * intensity
        capped_1m = min(p_30s * 0.88, est_1m) if p_30s > 0 else est_1m
        p_1m = round(max(capped_1m, laps_peaks.get("1m", 0.0)))

    # 4. 5m VO2 Max: Maximal Aerobic Power (MAP)
    if moving_sec < 300:
        p_5m = 0
    else:
        est_5m = np_w * 1.05 + (w_prime_j / 300.0) * 0.60 * intensity
        capped_5m = min(p_1m * 0.88, est_5m) if p_1m > 0 else est_5m
        p_5m = round(max(capped_5m, laps_peaks.get("5m", 0.0)))

    # 5. 20m Threshold: If ride was at least 15 min (900 sec)
    if moving_sec < 900:
        p_20m = 0
    elif moving_sec >= 1200:
        est_20m = min(p_5m * 0.92, max(avg_w, np_w * 0.98)) if p_5m > 0 else max(avg_w, np_w * 0.98)
        p_20m = round(max(est_20m, laps_peaks.get("20m", 0.0)))
    else:
        est_20m = max(avg_w, np_w * 0.93)
        p_20m = round(max(est_20m, laps_peaks.get("20m", 0.0)))

    # 6. 60m Stamina: If ride was at least 50 min (3000 sec)
    if moving_sec < 3000:
        p_60m = 0
    elif moving_sec >= 3600:
        est_60m = min(p_20m * 0.95, max(avg_w, np_w * 0.94)) if p_20m > 0 else avg_w
        p_60m = round(est_60m)
    else:
        est_60m = min(p_20m * 0.92, avg_w * 0.96) if p_20m > 0 else avg_w * 0.92
        p_60m = round(est_60m)

    return {
        "5s": p_5s,
        "30s": p_30s,
        "1m": p_1m,
        "5m": p_5m,
        "20m": p_20m,
        "60m": p_60m
    }

def get_power_spiderweb_profile(
    user_id: Optional[str] = None,
    timeframe: str = "30d"
) -> Dict[str, Any]:
    """
    Computes the multi-axis Power Spiderweb (Radar) profile comparing the current
    evaluation period against the comparison period and historical baselines.
    """
    uid = user_id or get_current_user_id()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))
    w_prime_kj = float(get_setting("athlete_w_prime_kj", 20.0, user_id=uid))
    peak_power = int(get_setting("athlete_peak_power_watts", 1050, user_id=uid))
    weight_kg = float(get_setting("athlete_weight_kg", 70.0, user_id=uid))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, sport_type, start_date, moving_time_sec, distance_meters,
               average_watts, weighted_average_watts, average_heartrate, suffer_score, raw_json
        FROM strava_activities
        WHERE user_id = ?
        ORDER BY start_date DESC
    """, (uid,))
    rows = c.fetchall()
    if not rows and uid == "usr_guest":
        c.execute("""
            SELECT id, name, sport_type, start_date, moving_time_sec, distance_meters,
                   average_watts, weighted_average_watts, average_heartrate, suffer_score, raw_json
            FROM strava_activities
            WHERE user_id = 'usr_default'
            ORDER BY start_date DESC
        """)
        rows = c.fetchall()
    conn.close()

    activities = [dict(r) for r in rows] if rows else []

    # If no activities in DB, use mock activities
    if not activities:
        from app.services.mock_data import get_mock_strava_activities
        activities = get_mock_strava_activities()

    # Determine reference date (most recent activity date or today)
    today = get_athlete_date(uid)
    if activities:
        first_date_str = str(activities[0].get("start_date", ""))[:10]
        try:
            ref_date = max(today, datetime.date.fromisoformat(first_date_str))
        except Exception:
            ref_date = today
    else:
        ref_date = today

    # Determine date intervals based on timeframe
    timeframe = (timeframe or "30d").lower()
    if timeframe == "60d":
        cur_days = 60
        prev_days = 60
        cur_label = "Last 60 Days"
        prev_label = "Prior 60 Days"
    elif timeframe == "90d":
        cur_days = 90
        prev_days = 90
        cur_label = "Last 90 Days"
        prev_label = "Season Baseline"
    elif timeframe == "all_time":
        cur_days = 30
        prev_days = 365
        cur_label = "Current Month"
        prev_label = "All-Time PRs"
    else: # default 30d
        cur_days = 30
        prev_days = 30
        cur_label = "Last 30 Days"
        prev_label = "Prior 30 Days"

    cur_start = ref_date - datetime.timedelta(days=cur_days)
    prev_start = cur_start - datetime.timedelta(days=prev_days)

    cur_acts = []
    prev_acts = []
    all_acts = []

    for act in activities:
        local_s = resolve_strava_local_start(act, user_id=uid) or act.get("start_date") or ""
        s_date_str = local_s[:10]
        try:
            act_d = datetime.date.fromisoformat(s_date_str)
        except Exception:
            continue

        act_copy = dict(act)
        act_copy["act_date"] = act_d
        act_copy["act_date_str"] = s_date_str
        sport = act.get("sport_type") or act.get("type", "")
        is_cycling = is_cycling_sport(sport, act.get("name", ""))
        act_copy["is_cycling"] = is_cycling

        if is_cycling:
            act_copy["peaks"] = calculate_activity_peak_powers(act_copy, ftp, w_prime_kj, peak_power)
        else:
            act_copy["peaks"] = {"5s": 0, "30s": 0, "1m": 0, "5m": 0, "20m": 0, "60m": 0}

        all_acts.append(act_copy)
        if act_d >= cur_start:
            cur_acts.append(act_copy)
        elif act_d >= prev_start:
            prev_acts.append(act_copy)

    # Cycling-specific activity subsets for power curve analytics
    cur_cycling = [a for a in cur_acts if a.get("is_cycling", False)]
    prev_cycling = [a for a in prev_acts if a.get("is_cycling", False)]
    all_cycling = [a for a in all_acts if a.get("is_cycling", False)]

    # If previous period has 0 activities (e.g. athlete joined recently), fallback to historical split
    if not prev_cycling and len(all_cycling) > len(cur_cycling):
        prev_cycling = [a for a in all_cycling if a not in cur_cycling]
    elif not prev_cycling and all_cycling:
        prev_cycling = []

    # Calculate peak power envelope for each duration
    dur_keys = ["5s", "1m", "5m", "20m", "60m"]

    # Fallback baseline powers based on athlete's FTP and fitness signature
    modeled_baseline = {
        "5s": round(max(peak_power * 0.72, ftp * 2.7)),
        "1m": round(ftp * 1.55),
        "5m": round(ftp * 1.15),
        "20m": round(ftp * 0.98),
        "60m": round(ftp * 0.88)
    }

    cur_envelope = {}
    prev_envelope = {}
    all_time_envelope = {}

    for k in dur_keys:
        # Current period peak (strictly cycling activities)
        cur_vals = [a["peaks"].get(k, 0) for a in cur_cycling if a["peaks"].get(k, 0) > 0]
        cur_envelope[k] = max(cur_vals) if cur_vals else modeled_baseline[k]

        # Previous period peak (strictly cycling activities)
        if timeframe == "all_time":
            all_vals = [a["peaks"].get(k, 0) for a in all_cycling if a["peaks"].get(k, 0) > 0]
            prev_envelope[k] = max(all_vals) if all_vals else modeled_baseline[k]
        else:
            prev_vals = [a["peaks"].get(k, 0) for a in prev_cycling if a["peaks"].get(k, 0) > 0]
            prev_envelope[k] = max(prev_vals) if prev_vals else int(modeled_baseline[k] * 0.95)

        # All-time PR peak (strictly cycling activities)
        all_vals = [a["peaks"].get(k, 0) for a in all_cycling if a["peaks"].get(k, 0) > 0]
        all_time_envelope[k] = max(all_vals) if all_vals else modeled_baseline[k]

    # Benchmark caps for radar scale normalization (100% outer ring)
    # Calibrated against Coggan Category 1 / Elite W/kg physiological standards,
    # body mass, and dynamically scaled so benchmark ceiling is NEVER below current bests or all-time PRs.
    safe_weight = max(40.0, float(weight_kg))
    coggan_elite_benchmarks = {
        "5s": max(1200, round(safe_weight * 20.5), round(max(peak_power, ftp * 3.8) * 1.15)),
        "1m": max(580, round(safe_weight * 9.6), round(ftp * 2.2)),
        "5m": max(380, round(safe_weight * 6.1), round(ftp * 1.45)),
        "20m": max(320, round(safe_weight * 5.0), round(ftp * 1.22)),
        "60m": max(290, round(safe_weight * 4.6), round(ftp * 1.12)),
    }

    benchmarks = {
        k: max(
            coggan_elite_benchmarks[k],
            round(cur_envelope.get(k, 0) * 1.15),
            round(all_time_envelope.get(k, 0) * 1.10)
        )
        for k in dur_keys
    }

    # Retrieve athlete's active training goal if configured
    active_goal = get_active_spiderweb_goal(user_id=uid)
    goal_envelope = active_goal.get("target_envelope", {}) if active_goal else {}

    # Build axis points and deltas
    axes_data = []
    total_goal_initial_gap = 0
    total_goal_remaining_gap = 0

    for meta in RADAR_DURATIONS:
        k = meta["key"]
        cur_w = cur_envelope.get(k, 0)
        prev_w = prev_envelope.get(k, 0)
        bm = benchmarks.get(k, 300)

        delta_w = cur_w - prev_w
        delta_pct = round((delta_w / max(1, prev_w)) * 100.0, 1) if prev_w > 0 else 0.0

        cur_w_kg = round(cur_w / max(40.0, weight_kg), 2)
        prev_w_kg = round(prev_w / max(40.0, weight_kg), 2)

        # Scale 20% to 100% radius for visual radar chart
        cur_radar_pct = round(min(100.0, max(20.0, (cur_w / bm) * 100.0)), 1)
        prev_radar_pct = round(min(100.0, max(20.0, (prev_w / bm) * 100.0)), 1)

        # Goal target points
        target_w = None
        target_w_kg = None
        target_radar_pct = None
        goal_remaining_w = 0
        goal_met = False

        if active_goal and k in goal_envelope:
            target_w = int(goal_envelope[k])
            target_w_kg = round(target_w / max(40.0, weight_kg), 2)
            target_radar_pct = round(min(100.0, max(20.0, (target_w / bm) * 100.0)), 1)
            goal_remaining_w = max(0, target_w - cur_w)
            goal_met = (cur_w >= target_w)

            initial_axis_target_gap = max(0, target_w - prev_w)
            total_goal_initial_gap += initial_axis_target_gap
            total_goal_remaining_gap += goal_remaining_w

        axes_data.append({
            "key": k,
            "label": meta["label"],
            "name": meta["name"],
            "icon": meta["icon"],
            "energy_system": meta["energy"],
            "current_watts": cur_w,
            "current_w_kg": cur_w_kg,
            "previous_watts": prev_w,
            "previous_w_kg": prev_w_kg,
            "all_time_pr_watts": all_time_envelope.get(k, cur_w),
            "delta_watts": delta_w,
            "delta_pct": delta_pct,
            "benchmark_watts": bm,
            "current_radar_pct": cur_radar_pct,
            "previous_radar_pct": prev_radar_pct,
            "target_watts": target_w,
            "target_w_kg": target_w_kg,
            "target_radar_pct": target_radar_pct,
            "goal_remaining_watts": goal_remaining_w,
            "goal_met": goal_met,
            "improved": delta_w > 0,
            "unchanged": delta_w == 0,
            "declined": delta_w < 0
        })

    # Evaluate active goal progression percentage
    if active_goal:
        all_axes_met = all(ax.get("goal_met", True) for ax in axes_data if ax.get("target_watts") is not None)
        if all_axes_met:
            active_goal["progress_pct"] = 100.0
            active_goal["is_achieved"] = True
            active_goal["remaining_total_watts"] = 0
        else:
            active_goal["is_achieved"] = False
            active_goal["remaining_total_watts"] = total_goal_remaining_gap
            if total_goal_initial_gap > 0:
                prog = max(0.0, min(99.0, ((total_goal_initial_gap - total_goal_remaining_gap) / total_goal_initial_gap) * 100.0))
                active_goal["progress_pct"] = round(prog, 1)
            else:
                active_goal["progress_pct"] = 0.0

    # Classify Rider Phenotype (Unified Multi-Axis Scoring Model)
    phenotype_eval = classify_athlete_phenotype(cur_envelope, ftp, weight_kg)
    phenotype = phenotype_eval["title"]
    phenotype_badge = phenotype_eval["badge"]
    phenotype_desc = phenotype_eval["description"]
    primary_strength = phenotype_eval["primary_strength"]
    growth_focus = phenotype_eval["growth_focus"]

    # Historical Progression Timeline (Month-by-Month Buckets)
    timeline_buckets = []
    bucket_map = {}
    for act in all_acts:
        d = act["act_date"]
        b_key = d.strftime("%Y-%m")
        b_label = d.strftime("%b %Y")
        if b_key not in bucket_map:
            bucket_map[b_key] = {
                "key": b_key,
                "label": b_label,
                "workout_count": 0,
                "total_sec": 0,
                "total_tss": 0,
                "peak_5s": 0,
                "peak_1m": 0,
                "peak_5m": 0,
                "peak_20m": 0,
                "peak_60m": 0
            }
        b = bucket_map[b_key]
        b["workout_count"] += 1
        b["total_sec"] += int(act.get("moving_time_sec") or 0)
        b["total_tss"] += int(act.get("suffer_score") or 0)

        if act.get("is_cycling", False):
            b["cycling_count"] = b.get("cycling_count", 0) + 1
            for dur in dur_keys:
                p_val = act["peaks"].get(dur, 0)
                if p_val > b[f"peak_{dur}"]:
                    b[f"peak_{dur}"] = p_val
        else:
            b["cross_training_count"] = b.get("cross_training_count", 0) + 1

    # Sort chronological
    sorted_bucket_keys = sorted(bucket_map.keys())
    for b_k in sorted_bucket_keys:
        b = bucket_map[b_k]
        b["total_hours"] = round(b["total_sec"] / 3600.0, 1)
        timeline_buckets.append(b)

    # Highlight PR breakthroughs across history (strictly cycling activities)
    breakthroughs = []
    best_5s_so_far = 0
    best_5m_so_far = 0
    best_20m_so_far = 0

    # Chronological scan of cycling activities ONLY
    chronological_cycling = sorted([a for a in all_acts if a.get("is_cycling", False)], key=lambda a: a["act_date_str"])
    for act in chronological_cycling:
        p_5 = act["peaks"].get("5s", 0)
        p_5m = act["peaks"].get("5m", 0)
        p_20 = act["peaks"].get("20m", 0)
        d_str = act["act_date_str"]
        a_name = act.get("name", "Ride")

        if p_5 > best_5s_so_far and best_5s_so_far > 0 and (p_5 - best_5s_so_far) >= 15:
            delta = p_5 - best_5s_so_far
            breakthroughs.append({
                "date": d_str,
                "activity_name": a_name,
                "duration": "5s Sprint",
                "watts": p_5,
                "delta_watts": delta,
                "badge": f"+{delta}W Sprint PR"
            })
            best_5s_so_far = p_5
        elif p_5 > best_5s_so_far:
            best_5s_so_far = p_5

        if p_5m > best_5m_so_far and best_5m_so_far > 0 and (p_5m - best_5m_so_far) >= 6:
            delta = p_5m - best_5m_so_far
            breakthroughs.append({
                "date": d_str,
                "activity_name": a_name,
                "duration": "5m VO2 Max",
                "watts": p_5m,
                "delta_watts": delta,
                "badge": f"+{delta}W VO2 PR"
            })
            best_5m_so_far = p_5m
        elif p_5m > best_5m_so_far:
            best_5m_so_far = p_5m

        if p_20 > best_20m_so_far and best_20m_so_far > 0 and (p_20 - best_20m_so_far) >= 4:
            delta = p_20 - best_20m_so_far
            breakthroughs.append({
                "date": d_str,
                "activity_name": a_name,
                "duration": "20m Threshold",
                "watts": p_20,
                "delta_watts": delta,
                "badge": f"+{delta}W Threshold PR"
            })
            best_20m_so_far = p_20
        elif p_20 > best_20m_so_far:
            best_20m_so_far = p_20

    # Sort breakthroughs reverse chronological
    breakthroughs = sorted(breakthroughs, key=lambda b: b["date"], reverse=True)[:5]

    return {
        "timeframe": timeframe,
        "current_label": cur_label,
        "previous_label": prev_label,
        "athlete": {
            "ftp_watts": ftp,
            "w_prime_kj": w_prime_kj,
            "peak_power_watts": peak_power,
            "weight_kg": weight_kg
        },
        "phenotype": {
            "title": phenotype,
            "badge": phenotype_badge,
            "description": phenotype_desc,
            "primary_strength": primary_strength,
            "growth_focus": growth_focus,
            "affinity_scores": phenotype_eval.get("affinity_scores", {}),
            "readiness_map": phenotype_eval.get("readiness_map", {}),
            "std_dev": phenotype_eval.get("std_dev", 0.0)
        },
        "has_active_goal": bool(active_goal),
        "active_goal": active_goal,
        "axes": axes_data,
        "summary_deltas": {
            "sprint_5s": next((a for a in axes_data if a["key"] == "5s"), {}),
            "anaerobic_1m": next((a for a in axes_data if a["key"] == "1m"), {}),
            "vo2_5m": next((a for a in axes_data if a["key"] == "5m"), {}),
            "threshold_20m": next((a for a in axes_data if a["key"] == "20m"), {}),
            "stamina_60m": next((a for a in axes_data if a["key"] == "60m"), {}),
        },
        "progression_timeline": timeline_buckets,
        "recent_breakthroughs": breakthroughs,
        "activities_count": {
            "current_period": len(cur_cycling),
            "previous_period": len(prev_cycling),
            "total_cycling": len(all_cycling),
            "total_cross_training": len([a for a in all_acts if not a.get("is_cycling", False)]),
            "total_analyzed": len(all_acts)
        }
    }


# --- Spiderweb Training Goals & Target Improvement Planning ---

# (RIDER_PHENOTYPE_DEFINITIONS is defined above in the Coggan Power Profiling Model section)


def get_active_spiderweb_goal(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the active spiderweb training goal for the athlete."""
    uid = user_id or get_current_user_id()
    raw = get_setting("spiderweb_goal", None, user_id=uid)
    if not raw:
        return None
    try:
        if isinstance(raw, str):
            goal = json.loads(raw)
        elif isinstance(raw, dict):
            goal = dict(raw)
        else:
            return None
        return goal
    except Exception:
        return None


def set_active_spiderweb_goal(payload: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Saves a new or updated active spiderweb goal.
    Supports either Duration-based goals (e.g. 20m Threshold 260W)
    or Phenotype Transformation goals (e.g. Transform to Puncheur).
    """
    uid = user_id or get_current_user_id()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))
    weight_kg = float(get_setting("athlete_weight_kg", 70.0, user_id=uid))

    goal_type = payload.get("goal_type", "phenotype") # "phenotype" or "duration"
    target_key = payload.get("target_key", "Puncheur")
    preserve_program_settings = bool(payload.get("preserve_program_settings", False))
    explicit_target_ftp = payload.get("explicit_target_ftp")

    # Get current envelope to anchor non-target axes
    profile = get_power_spiderweb_profile(user_id=uid, timeframe="30d")
    cur_envelope = {ax["key"]: ax["current_watts"] for ax in profile.get("axes", [])}

    target_envelope = dict(cur_envelope)
    synced_program_goal = str(get_setting("program_goal", "FTP_BUILD", user_id=uid))
    synced_target_ftp = int(explicit_target_ftp or get_setting("program_target_ftp", ftp + 15, user_id=uid))
    anchor_ftp = max(ftp, synced_target_ftp) if preserve_program_settings else ftp

    # Archetype weekly load baselines (aligned with program_service.DEFAULT_GOALS)
    program_load_baselines = {
        "FTP_BUILD": {"gain": 15, "tss": 360, "xss": 360},
        "GRAN_FONDO": {"gain": 10, "tss": 420, "xss": 420},
        "VO2_CRIT": {"gain": 12, "tss": 340, "xss": 340},
        "HEALTH_LONGEVITY": {"gain": 5, "tss": 260, "xss": 260}
    }

    if goal_type == "phenotype":
        pheno_def = next((p for p in RIDER_PHENOTYPE_DEFINITIONS if p["id"].lower() == target_key.lower()), None)
        if not pheno_def:
            pheno_def = RIDER_PHENOTYPE_DEFINITIONS[0] # Default Puncheur

        cur_pheno_title = profile.get("phenotype", {}).get("title", "")
        is_deepening = (cur_pheno_title.lower() == pheno_def["title"].lower() or cur_pheno_title.lower() == pheno_def["id"].lower())

        target_key = pheno_def["id"]
        target_title = f"{'Deepen Focus on' if is_deepening else 'Transform into'} {pheno_def['title']}"
        target_badge = f"{pheno_def['icon']} {pheno_def['title']} Target"
        focus_system = pheno_def["focus_energy_system"]
        rec_workouts = pheno_def["recommended_workouts"]

        reqs = pheno_def["requirements"]
        sig_axes = pheno_def.get("signature_axes", [])

        # Build target envelope: progressive adaptation overload on signature axes
        for k in ["5s", "1m", "5m", "20m", "60m"]:
            base_req = round(anchor_ftp * reqs.get(f"{k}_ratio", 1.0))
            cur_w = cur_envelope.get(k, base_req)
            if k in sig_axes:
                if cur_w >= round(base_req * 0.97):
                    target_envelope[k] = max(base_req, round(cur_w * 1.05))
                else:
                    target_envelope[k] = base_req
            else:
                target_envelope[k] = max(cur_w, base_req)

        # Check climber specific W/kg minimums
        if "min_20m_wkg" in reqs:
            wkg_target_20m = round(weight_kg * reqs["min_20m_wkg"])
            if cur_envelope.get("20m", 0) >= round(wkg_target_20m * 0.97):
                target_envelope["20m"] = max(target_envelope.get("20m", 0), round(cur_envelope.get("20m", 0) * 1.05))
            else:
                target_envelope["20m"] = max(target_envelope.get("20m", 0), wkg_target_20m)
        if "min_5m_wkg" in reqs:
            wkg_target_5m = round(weight_kg * reqs["min_5m_wkg"])
            if cur_envelope.get("5m", 0) >= round(wkg_target_5m * 0.97):
                target_envelope["5m"] = max(target_envelope.get("5m", 0), round(cur_envelope.get("5m", 0) * 1.05))
            else:
                target_envelope["5m"] = max(target_envelope.get("5m", 0), wkg_target_5m)

        # Automatically align program_goal & program_target_ftp so Macrocycle & Spiderweb never conflict
        if not preserve_program_settings:
            program_goal_map = {
                "Puncheur": "VO2_CRIT",
                "Pursuiter": "VO2_CRIT",
                "Rouleur": "FTP_BUILD",
                "Climber": "FTP_BUILD",
                "Sprinter": "VO2_CRIT",
                "All-Rounder": "GRAN_FONDO"
            }
            synced_program_goal = program_goal_map.get(pheno_def["id"], "FTP_BUILD")
            baseline_cfg = program_load_baselines[synced_program_goal]
            derived_ftp = max(
                ftp + baseline_cfg["gain"],
                round(target_envelope["20m"] * 0.95),
                target_envelope["60m"]
            )
            synced_target_ftp = derived_ftp
            set_setting("program_goal", synced_program_goal, user_id=uid)
            set_setting("program_target_ftp", synced_target_ftp, user_id=uid)
            set_setting("program_weekly_tss_target", baseline_cfg["tss"], user_id=uid)
            set_setting("program_weekly_xss_target", baseline_cfg["xss"], user_id=uid)

    else: # duration goal
        # e.g. target_key = "20m", target_watts = 260
        target_watts = int(payload.get("target_watts") or round(cur_envelope.get(target_key, 250) * 1.06))
        dur_meta = next((d for d in RADAR_DURATIONS if d["key"] == target_key), RADAR_DURATIONS[3])

        target_envelope[target_key] = target_watts
        target_title = f"{dur_meta['name']} @ {target_watts}W"
        target_badge = f"{dur_meta['icon']} {target_watts}W ({dur_meta['label']})"
        focus_system = f"{dur_meta['energy']} ({dur_meta['label']})"

        workouts_map = {
            "5s": ["6x 15s Standing Start Sprints", "Cadence Acceleration Drills", "Heavy Squats"],
            "1m": ["30/30s VO2 Microbursts", "5x 2-Min Anaerobic Repeats", "Tabata Power Surges"],
            "5m": ["5x 4-Min MAP @ 115% FTP", "4x 5-Min VO2 Extenders", "High-Cadence MAP Ramps"],
            "20m": ["2x 20-Min Sweet Spot @ 92% FTP", "3x 12-Min Threshold Over-Unders", "45-Min TT Simulation"],
            "60m": ["3x 20-Min Threshold Progression", "90-Min Zone 2 Steady Aerobic Base", "Carbohydrate Depletion Resistance"]
        }
        rec_workouts = workouts_map.get(target_key, ["Structured Interval Progressions"])

        if target_key == "20m":
            if not preserve_program_settings:
                synced_program_goal = "FTP_BUILD"
                synced_target_ftp = max(ftp + 5, round(target_watts * 0.95))
            # Keep 60m envelope physiologically coherent with 20m target
            target_envelope["60m"] = max(target_envelope.get("60m", 210), round(target_watts * 0.91))
        elif target_key == "60m":
            if not preserve_program_settings:
                synced_program_goal = "GRAN_FONDO" if target_watts <= round(ftp * 1.04) else "FTP_BUILD"
                synced_target_ftp = max(ftp + 5, target_watts)
            target_envelope["20m"] = max(target_envelope.get("20m", 240), round(target_watts / 0.95))
        elif target_key in ("1m", "5m", "5s") and not preserve_program_settings:
            synced_program_goal = "VO2_CRIT"
            cur_axis_w = max(1, cur_envelope.get(target_key, target_watts))
            pct_gain = max(0.03, (target_watts - cur_axis_w) / float(cur_axis_w))
            synced_target_ftp = max(ftp + 5, ftp + round(ftp * min(0.12, pct_gain * 0.6)))

        if not preserve_program_settings:
            baseline_cfg = program_load_baselines.get(synced_program_goal, program_load_baselines["FTP_BUILD"])
            set_setting("program_goal", synced_program_goal, user_id=uid)
            set_setting("program_target_ftp", synced_target_ftp, user_id=uid)
            set_setting("program_weekly_tss_target", baseline_cfg["tss"], user_id=uid)
            set_setting("program_weekly_xss_target", baseline_cfg["xss"], user_id=uid)

    goal_obj = {
        "id": f"spiderweb_goal_{int(datetime.datetime.now().timestamp())}",
        "goal_type": goal_type,
        "target_key": target_key,
        "target_watts": payload.get("target_watts") if goal_type == "duration" else None,
        "target_title": target_title,
        "target_badge": target_badge,
        "target_envelope": target_envelope,
        "focus_energy_system": focus_system,
        "recommended_workouts": rec_workouts,
        "synced_program_goal": synced_program_goal,
        "synced_target_ftp": synced_target_ftp,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "active"
    }

    set_setting("spiderweb_goal", goal_obj, user_id=uid)
    return goal_obj


def sync_spiderweb_goal_from_program(
    program_goal: Optional[str] = None,
    program_target_ftp: Optional[int] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronizes the active Spiderweb Goal when the athlete updates
    'Long-Term Fitness Goal & Program (Xert Alternative)' in Settings,
    guaranteeing the two systems are 100% integrated and never conflict.
    """
    uid = user_id or get_current_user_id()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))
    weight_kg = float(get_setting("athlete_weight_kg", 70.0, user_id=uid))
    p_goal = program_goal or str(get_setting("program_goal", "FTP_BUILD", user_id=uid))
    p_target_ftp = int(program_target_ftp or get_setting("program_target_ftp", ftp + 15, user_id=uid))

    existing = get_active_spiderweb_goal(user_id=uid)
    profile = get_power_spiderweb_profile(user_id=uid, timeframe="30d")
    cur_envelope = {ax["key"]: ax["current_watts"] for ax in profile.get("axes", [])}

    # Map macrocycle program_goal -> compatible spiderweb goals
    compatible_map = {
        "FTP_BUILD": [("duration", "20m"), ("duration", "60m"), ("phenotype", "Climber"), ("phenotype", "Rouleur")],
        "GRAN_FONDO": [("duration", "60m"), ("phenotype", "All-Rounder"), ("phenotype", "Rouleur")],
        "VO2_CRIT": [("phenotype", "Puncheur"), ("phenotype", "Pursuiter"), ("phenotype", "Sprinter"), ("duration", "5m"), ("duration", "1m"), ("duration", "5s")],
        "HEALTH_LONGEVITY": [("phenotype", "All-Rounder"), ("duration", "60m")]
    }
    allowed_pairs = compatible_map.get(p_goal, compatible_map["FTP_BUILD"])

    # If existing spiderweb goal is already compatible with p_goal, update its target wattage to match p_target_ftp
    if existing and (existing.get("goal_type"), existing.get("target_key")) in allowed_pairs:
        g_type = existing.get("goal_type")
        t_key = existing.get("target_key")
        env = dict(existing.get("target_envelope") or cur_envelope)
        env["20m"] = max(cur_envelope.get("20m", 240), round(p_target_ftp / 0.95))
        env["60m"] = max(cur_envelope.get("60m", 210), round(p_target_ftp * 0.96))

        if g_type == "duration" and t_key == "20m":
            t_watts = round(p_target_ftp / 0.95)
            env["20m"] = t_watts
            existing["target_watts"] = t_watts
            existing["target_title"] = f"20-Min Threshold @ {t_watts}W ({p_target_ftp}W FTP)"
            existing["target_badge"] = f"🔥 {t_watts}W (20m Threshold)"
        elif g_type == "duration" and t_key == "60m":
            t_watts = p_target_ftp
            env["60m"] = t_watts
            existing["target_watts"] = t_watts
            existing["target_title"] = f"60-Min Fatigue Resistance @ {t_watts}W"
            existing["target_badge"] = f"🛡️ {t_watts}W (60m Endurance)"
        elif g_type == "phenotype":
            pheno_def = next((p for p in RIDER_PHENOTYPE_DEFINITIONS if p["id"].lower() == str(t_key).lower()), None)
            if pheno_def:
                reqs = pheno_def["requirements"]
                env["5s"] = max(cur_envelope.get("5s", 600), round(p_target_ftp * reqs["5s_ratio"]))
                env["1m"] = max(cur_envelope.get("1m", 400), round(p_target_ftp * reqs["1m_ratio"]))
                env["5m"] = max(cur_envelope.get("5m", 300), round(p_target_ftp * reqs["5m_ratio"]))
                env["20m"] = max(cur_envelope.get("20m", 240), round(p_target_ftp * reqs["20m_ratio"]))
                env["60m"] = max(cur_envelope.get("60m", 210), round(p_target_ftp * reqs["60m_ratio"]))

        existing["target_envelope"] = env
        existing["synced_program_goal"] = p_goal
        existing["synced_target_ftp"] = p_target_ftp
        set_setting("spiderweb_goal", existing, user_id=uid)
        return existing

    # Otherwise, build a freshly aligned Spiderweb Goal from p_goal and p_target_ftp while preserving explicit Settings inputs
    if p_goal == "FTP_BUILD":
        target_20m = max(cur_envelope.get("20m", 240) + 5, round(p_target_ftp / 0.95))
        return set_active_spiderweb_goal(
            {
                "goal_type": "duration",
                "target_key": "20m",
                "target_watts": target_20m,
                "preserve_program_settings": True,
                "explicit_target_ftp": p_target_ftp
            },
            user_id=uid
        )
    elif p_goal == "GRAN_FONDO":
        target_60m = max(cur_envelope.get("60m", 210) + 5, round(p_target_ftp * 0.94))
        return set_active_spiderweb_goal(
            {
                "goal_type": "duration",
                "target_key": "60m",
                "target_watts": target_60m,
                "preserve_program_settings": True,
                "explicit_target_ftp": p_target_ftp
            },
            user_id=uid
        )
    elif p_goal == "VO2_CRIT":
        return set_active_spiderweb_goal(
            {
                "goal_type": "phenotype",
                "target_key": "Puncheur",
                "preserve_program_settings": True,
                "explicit_target_ftp": p_target_ftp
            },
            user_id=uid
        )
    else: # HEALTH_LONGEVITY
        return set_active_spiderweb_goal(
            {
                "goal_type": "phenotype",
                "target_key": "All-Rounder",
                "preserve_program_settings": True,
                "explicit_target_ftp": p_target_ftp
            },
            user_id=uid
        )


def clear_active_spiderweb_goal(user_id: Optional[str] = None) -> bool:
    """Clears the active spiderweb training goal and resets program_target_ftp to the macrocycle archetype baseline."""
    uid = user_id or get_current_user_id()
    delete_setting("spiderweb_goal", user_id=uid)
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))
    p_goal = str(get_setting("program_goal", "FTP_BUILD", user_id=uid))
    gains = {"FTP_BUILD": 15, "GRAN_FONDO": 10, "VO2_CRIT": 12, "HEALTH_LONGEVITY": 5}
    set_setting("program_target_ftp", ftp + gains.get(p_goal, 15), user_id=uid)
    return True


def calculate_spiderweb_target_changes(
    user_id: Optional[str] = None,
    timeframe: str = "30d"
) -> Dict[str, Any]:
    """
    Computes precise target wattage changes, W/kg deltas, and training stimulus
    needed to improve across individual duration categories (5s, 1m, 5m, 20m, 60m)
    or transform athlete phenotype into any targeted rider type.
    """
    uid = user_id or get_current_user_id()
    profile = get_power_spiderweb_profile(user_id=uid, timeframe=timeframe)
    ftp = profile["athlete"]["ftp_watts"]
    weight_kg = profile["athlete"]["weight_kg"]
    cur_phenotype = profile["phenotype"]
    active_goal = profile.get("active_goal")

    cur_envelope = {ax["key"]: ax["current_watts"] for ax in profile.get("axes", [])}

    # 1. Duration Category Improvement Analysis
    duration_targets = []
    category_workout_guidance = {
        "5s": {
            "stimulus": "Neuromuscular motor unit synchronization & peak phosphagen turnover.",
            "workouts": "6x 15s maximal standing starts with 4min full recovery; 3x 30s high-cadence torque openers."
        },
        "1m": {
            "stimulus": "Anaerobic glycolytic capacity (W') & lactate buffering tolerance.",
            "workouts": "8x 30/30s microbursts (120% / 50% FTP); 4x 90s all-out anaerobic surges."
        },
        "5m": {
            "stimulus": "Maximal Aerobic Power (MAP), cardiac stroke volume & VO2 max ceiling.",
            "workouts": "5x 4-Min MAP intervals @ 112–118% FTP with 3min recovery; 40/20s high-frequency ladders."
        },
        "20m": {
            "stimulus": "Lactate shuttle efficiency, mitochondrial density & critical power (FTP).",
            "workouts": "2x 20-Min Sweet Spot (90–94% FTP); 3x 12-Min Threshold Over-Unders (95% / 105% FTP)."
        },
        "60m": {
            "stimulus": "Type I slow-twitch endurance, fat oxidation rate & glycogen sparing.",
            "workouts": "90–120 Min Zone 2 aerobic endurance ride @ 65–72% FTP; 3x 20-Min steady tempo progressions."
        }
    }

    for meta in RADAR_DURATIONS:
        k = meta["key"]
        cur_w = cur_envelope.get(k, 0)
        cur_wkg = round(cur_w / max(40.0, weight_kg), 2)
        bm_w = next((ax["benchmark_watts"] for ax in profile["axes"] if ax["key"] == k), 300)

        # Tier 1: Progressive +5% (Achievable in 2-3 weeks)
        tier1_w = round(cur_w * 1.05) if cur_w > 0 else round(ftp * 1.1)
        tier1_delta = tier1_w - cur_w
        tier1_wkg = round(tier1_w / max(40.0, weight_kg), 2)

        # Tier 2: Category Leap +10% (4-6 week block)
        tier2_w = round(cur_w * 1.10) if cur_w > 0 else round(ftp * 1.25)
        tier2_delta = tier2_w - cur_w
        tier2_wkg = round(tier2_w / max(40.0, weight_kg), 2)

        # Tier 3: Benchmark Ceiling (Elite)
        tier3_w = max(bm_w, round(cur_w * 1.15), tier2_w + 5)
        tier3_delta = tier3_w - cur_w
        tier3_wkg = round(tier3_w / max(40.0, weight_kg), 2)

        duration_targets.append({
            "key": k,
            "label": meta["label"],
            "name": meta["name"],
            "icon": meta["icon"],
            "energy_system": meta["energy"],
            "current_watts": cur_w,
            "current_w_kg": cur_wkg,
            "benchmark_watts": bm_w,
            "tier1_progressive": {
                "label": "Progressive Target (+5%)",
                "target_watts": tier1_w,
                "target_w_kg": tier1_wkg,
                "delta_watts": tier1_delta,
                "delta_pct": 5.0,
                "timeline": "2–3 Weeks Focused Overload"
            },
            "tier2_transformative": {
                "label": "Transformative Leap (+10%)",
                "target_watts": tier2_w,
                "target_w_kg": tier2_wkg,
                "delta_watts": tier2_delta,
                "delta_pct": 10.0,
                "timeline": "4–6 Week Periodized Block"
            },
            "tier3_benchmark": {
                "label": "Benchmark Ceiling (Elite)",
                "target_watts": tier3_w,
                "target_w_kg": tier3_wkg,
                "delta_watts": tier3_delta,
                "delta_pct": round((tier3_delta / max(1, cur_w)) * 100.0, 1),
                "timeline": "Macro-Cycle Progression"
            },
            "guidance": category_workout_guidance.get(k, {})
        })

    # 2. Rider Type Transformation Analysis
    rider_type_targets = []
    cur_pheno_title = cur_phenotype.get("title", "")

    for pheno in RIDER_PHENOTYPE_DEFINITIONS:
        reqs = pheno["requirements"]
        sig_axes = pheno.get("signature_axes", [])

        # Build progressive target envelope
        target_env = {}
        for dur_meta in RADAR_DURATIONS:
            dur_k = dur_meta["key"]
            base_req = round(ftp * reqs.get(f"{dur_k}_ratio", 1.0))
            curr_val = cur_envelope.get(dur_k, 0)
            if dur_k in sig_axes:
                # Hallmark signature duration for this archetype:
                # If current power is near or exceeds archetype baseline, challenge with a +5% progressive stimulus
                if curr_val >= round(base_req * 0.97):
                    target_env[dur_k] = max(base_req, round(curr_val * 1.05))
                else:
                    target_env[dur_k] = base_req
            else:
                # Non-signature axes: maintain current power or archetype baseline
                target_env[dur_k] = max(curr_val, base_req)

        if "min_20m_wkg" in reqs:
            wkg_tgt = round(weight_kg * reqs["min_20m_wkg"])
            if cur_envelope.get("20m", 0) >= round(wkg_tgt * 0.97):
                target_env["20m"] = max(target_env.get("20m", 0), round(cur_envelope.get("20m", 0) * 1.05))
            else:
                target_env["20m"] = max(target_env.get("20m", 0), wkg_tgt)
        if "min_5m_wkg" in reqs:
            wkg_tgt_5 = round(weight_kg * reqs["min_5m_wkg"])
            if cur_envelope.get("5m", 0) >= round(wkg_tgt_5 * 0.97):
                target_env["5m"] = max(target_env.get("5m", 0), round(cur_envelope.get("5m", 0) * 1.05))
            else:
                target_env["5m"] = max(target_env.get("5m", 0), wkg_tgt_5)

        axis_gaps = []
        total_delta = 0
        readiness_accum = 0.0
        total_weight = 0.0

        for ax_meta in RADAR_DURATIONS:
            dur_k = ax_meta["key"]
            curr_val = cur_envelope.get(dur_k, 0)
            tgt_val = target_env[dur_k]
            gap = max(0, tgt_val - curr_val)
            is_met = (curr_val >= tgt_val)
            total_delta += gap

            # Continuous readiness relative to required archetype baseline
            base_req = round(ftp * reqs.get(f"{dur_k}_ratio", 1.0))
            axis_readiness = min(100.0, (curr_val / max(1.0, float(base_req))) * 100.0) if base_req > 0 else 100.0
            ax_weight = 2.5 if dur_k in sig_axes else 1.0
            readiness_accum += axis_readiness * ax_weight
            total_weight += ax_weight

            axis_gaps.append({
                "key": dur_k,
                "name": ax_meta["name"],
                "icon": ax_meta["icon"],
                "current_watts": curr_val,
                "current_w_kg": round(curr_val / max(40.0, weight_kg), 2),
                "target_watts": tgt_val,
                "target_w_kg": round(tgt_val / max(40.0, weight_kg), 2),
                "delta_watts": gap,
                "delta_pct": round((gap / max(1, curr_val)) * 100.0, 1) if curr_val > 0 else 0.0,
                "is_met": is_met
            })

        is_current_type = (pheno["id"].lower() == cur_pheno_title.lower() or pheno["title"].lower() == cur_pheno_title.lower())
        completion_pct = round(readiness_accum / max(1.0, total_weight), 1)

        rider_type_targets.append({
            "id": pheno["id"],
            "title": pheno["title"],
            "badge": pheno["badge"],
            "icon": pheno["icon"],
            "description": pheno["description"],
            "primary_strength": pheno["primary_strength"],
            "focus_energy_system": pheno["focus_energy_system"],
            "signature_axes": sig_axes,
            "is_current_type": is_current_type,
            "completion_pct": completion_pct,
            "total_delta_watts": total_delta,
            "target_envelope": target_env,
            "axis_gaps": axis_gaps,
            "recommended_workouts": pheno["recommended_workouts"]
        })

    return {
        "current_phenotype": cur_phenotype,
        "athlete": profile["athlete"],
        "active_goal": active_goal,
        "duration_category_targets": duration_targets,
        "rider_type_transformation_targets": rider_type_targets
    }

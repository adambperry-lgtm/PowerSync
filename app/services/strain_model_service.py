import math
import datetime
from typing import Dict, Any, List, Optional
from app.database import get_setting, get_db_connection, get_current_user_id

# ============================================================================
# 3-Tier Physiological Strain Engine (Xert XSS / Skiba W'bal Equivalent)
# ============================================================================

def get_athlete_fitness_signature(ftp: Optional[int] = None) -> Dict[str, Any]:
    """
    Returns the athlete's 3-parameter fitness signature:
    1. Threshold Power (TP / Critical Power in Watts)
    2. High Intensity Energy (HIE / W' anaerobic work capacity in kJ)
    3. Peak Power (P_max / maximum instantaneous neuromuscular sprint power in Watts)
    """
    tp = int(ftp or get_setting("athlete_ftp", 250))
    w_prime_kj = float(get_setting("athlete_w_prime_kj", 20.0))
    peak_power = int(get_setting("athlete_peak_power_watts", 1050))
    
    return {
        "tp": tp,
        "cp": tp,
        "w_prime_kj": w_prime_kj,
        "w_prime_joules": w_prime_kj * 1000.0,
        "peak_power_watts": peak_power
    }

def calculate_intervals_strain(
    intervals: List[Dict[str, Any]],
    ftp: Optional[int] = None,
    w_prime_kj: Optional[float] = None,
    peak_power_watts: Optional[int] = None
) -> Dict[str, Any]:
    """
    Simulates second-by-second W'bal dynamics and partitions physiological strain
    into Low (Aerobic), High (Glycolytic / W' depletion), and Peak (Neuromuscular) Strain.
    """
    sig = get_athlete_fitness_signature(ftp)
    cp = float(ftp or sig["tp"])
    w_prime = float((w_prime_kj or sig["w_prime_kj"]) * 1000.0)
    p_max = float(peak_power_watts or sig["peak_power_watts"])

    w_bal = w_prime
    min_w_bal = w_prime
    low_xss = 0.0
    high_xss = 0.0
    peak_xss = 0.0
    
    w_bal_samples = []
    sample_interval = 15 # Sample W'bal every 15s for visual curve
    t_total = 0

    expanded_intervals = []
    for it in intervals:
        if it.get("type") == "Repeats" or (it.get("repeat") and it.get("on_duration_sec")):
            reps = int(it.get("repeat", 1))
            on_dur = int(it.get("on_duration_sec", 60))
            off_dur = int(it.get("off_duration_sec", 60))
            on_pct = float(it.get("on_power_pct", 100.0))
            off_pct = float(it.get("off_power_pct", 55.0))
            for _ in range(reps):
                expanded_intervals.append({"duration_sec": on_dur, "power_pct": on_pct})
                if off_dur > 0:
                    expanded_intervals.append({"duration_sec": off_dur, "power_pct": off_pct})
        else:
            expanded_intervals.append(it)

    for it in expanded_intervals:
        dur = int(it.get("duration_sec", 60))
        # Support power either as absolute watts or percentage of FTP
        p_pct = it.get("power_pct")
        if p_pct is not None:
            p = cp * (float(p_pct) / 100.0)
        else:
            p = float(it.get("power", cp * 0.75))
            
        # Ramp/Warmup support
        p_low = it.get("power_low_pct")
        p_high = it.get("power_high_pct")
        is_ramp = (p_low is not None and p_high is not None)
        
        for s in range(dur):
            t_total += 1
            if is_ramp:
                frac = s / max(1, dur)
                curr_p = cp * ((p_low + (p_high - p_low) * frac) / 100.0)
            else:
                curr_p = p
                
            # 1. Low Strain (Aerobic energy below CP)
            # Calibrated so 1 hour at 100% CP = exactly 100 Low Strain points
            p_aerobic = min(curr_p, cp)
            low_xss += (1.0 / 36.0) * ((p_aerobic / max(1.0, cp)) ** 1.35)
            
            # 2. W' balance & High Strain (Glycolytic work above CP)
            if curr_p > cp:
                dw = curr_p - cp
                w_bal = max(0.0, w_bal - dw)
                if w_bal < min_w_bal:
                    min_w_bal = w_bal
                depletion_pct = max(0.0, min(1.0, 1.0 - (w_bal / w_prime)))
                # Exponential strain penalty as athlete approaches exhaustion
                strain_amp = 1.0 + 2.0 * (depletion_pct ** 1.5)
                high_xss += (dw / max(1.0, w_prime)) * 25.0 * strain_amp
            else:
                # Skiba recovery dynamic time constant
                dw_rec = cp - curr_p
                tau = 546.0 * math.exp(-0.01 * dw_rec) + 316.0
                w_bal = w_prime - (w_prime - w_bal) * math.exp(-1.0 / tau)
                
            # 3. Peak Strain (Neuromuscular sprint efforts > 135% CP toward P_max)
            p_peak_threshold = cp * 1.35
            if curr_p > p_peak_threshold:
                sprint_ratio = max(0.0, min(1.0, (curr_p - p_peak_threshold) / max(10.0, p_max - p_peak_threshold)))
                peak_xss += (sprint_ratio ** 1.8) * (1.0 / 3.6) * 1.5
                
            if t_total % sample_interval == 0:
                w_bal_samples.append(round((w_bal / w_prime) * 100.0, 1))

    total_xss = round(low_xss + high_xss + peak_xss, 1)
    min_pct = round((min_w_bal / w_prime) * 100.0, 1)
    min_kj = round(min_w_bal / 1000.0, 1)
    
    # Focus duration determination
    if total_xss <= 0:
        focus = "Rest / Recovery"
    elif peak_xss / max(1.0, total_xss) > 0.08:
        focus = "Sprinter (0:20 Focus)"
    elif high_xss / max(1.0, total_xss) > 0.32:
        focus = "Puncheur (2:00 Focus)"
    elif high_xss / max(1.0, total_xss) > 0.16:
        focus = "Breakaway Specialist (5:00 Focus)"
    elif (high_xss / max(1.0, total_xss)) > 0.05:
        focus = "Rouleur (20:00 Focus)"
    elif (low_xss / max(1.0, total_xss)) >= 0.85 and (total_xss >= 65):
        focus = "Climber / Sweet Spot (45:00 Focus)"
    else:
        focus = "Endurance / Century (>1h Focus)"

    return {
        "low_xss": round(low_xss, 1),
        "high_xss": round(high_xss, 1),
        "peak_xss": round(peak_xss, 1),
        "total_xss": total_xss,
        "min_w_bal_kj": min_kj,
        "min_w_bal_pct": min_pct,
        "battery_depleted_pct": round(100.0 - min_pct, 1),
        "focus_duration": focus,
        "w_bal_curve": w_bal_samples[:60] # Downsampled curve for UI sparklines
    }

def calculate_activity_strain(
    activity: Dict[str, Any],
    ftp: Optional[int] = None,
    w_prime_kj: Optional[float] = None,
    peak_power_watts: Optional[int] = None
) -> Dict[str, Any]:
    """
    Computes 3-tier strain for a completed ride.
    """
    sig = get_athlete_fitness_signature(ftp)
    cp = float(ftp or sig["tp"])
    w_prime = float((w_prime_kj or sig["w_prime_kj"]) * 1000.0)
    p_max = float(peak_power_watts or sig["peak_power_watts"])

    moving_time_sec = float(activity.get("moving_time_sec") or 0)
    if moving_time_sec <= 0:
        return {
            "low_xss": 0.0,
            "high_xss": 0.0,
            "peak_xss": 0.0,
            "total_xss": 0.0,
            "min_w_bal_pct": 100.0,
            "focus_duration": "Active Recovery",
            "battery_depleted_pct": 0.0
        }

    dur_h = moving_time_sec / 3600.0
    p_avg = float(activity.get("average_watts") or 0.0)
    p_np = float(activity.get("weighted_average_watts") or p_avg)
    p_max_act = float(activity.get("max_watts") or activity.get("max_heartrate") or 0.0)
    if p_max_act < p_np:
        p_max_act = p_np * 1.35
        
    if p_np <= 0:
        p_np = cp * 0.65
        p_avg = cp * 0.60
        
    vi = max(1.0, p_np / max(1.0, p_avg))
    
    # 1. Base aerobic strain below CP
    p_base = min(cp, p_avg)
    low_xss = dur_h * 100.0 * ((p_base / cp) ** 1.35)
    
    # 2. High strain above CP
    high_xss = 0.0
    min_w_bal_pct = 100.0
    
    if p_np > cp:
        over_cp = p_np - cp
        work_above_kj = (over_cp * moving_time_sec) / 1000.0
        w_prime_depletions = work_above_kj / max(1.0, (w_prime / 1000.0))
        high_xss = w_prime_depletions * 25.0 * (1.0 + (vi - 1.0) * 2.0)
        min_w_bal_pct = max(5.0, 100.0 - min(95.0, (w_prime_depletions * 45.0)))
    elif vi > 1.08:
        # Punchy terrain or group surge variance
        surge_fraction = min(0.35, (vi - 1.0) * 1.5)
        high_est_watts = (p_np * 0.25)
        high_xss = dur_h * surge_fraction * (high_est_watts / cp) * 70.0
        min_w_bal_pct = max(25.0, 100.0 - (surge_fraction * 120.0))
    else:
        min_w_bal_pct = 95.0
        
    # 3. Peak strain
    peak_xss = 0.0
    if p_max_act > cp * 1.35:
        burst_ratio = min(1.0, (p_max_act - cp * 1.35) / max(10.0, p_max - cp * 1.35))
        peak_xss = (burst_ratio ** 1.8) * min(25.0, dur_h * 8.5)
        min_w_bal_pct = max(0.0, min_w_bal_pct - (burst_ratio * 15.0))
        
    total_xss = round(low_xss + high_xss + peak_xss, 1)
    
    # Focus classification
    if total_xss <= 0:
        focus = "Rest"
    elif peak_xss / max(1.0, total_xss) > 0.08:
        focus = "Sprinter (0:20 Focus)"
    elif high_xss / max(1.0, total_xss) > 0.32:
        focus = "Puncheur (2:00 Focus)"
    elif high_xss / max(1.0, total_xss) > 0.16:
        focus = "Breakaway Specialist (5:00 Focus)"
    elif vi >= 1.08 and high_xss > 10:
        focus = "Rouleur (20:00 Focus)"
    elif (p_avg / cp) >= 0.82:
        focus = "Climber / Sweet Spot (45:00 Focus)"
    else:
        focus = "Endurance / Century (>1h Focus)"
        
    return {
        "low_xss": round(low_xss, 1),
        "high_xss": round(high_xss, 1),
        "peak_xss": round(peak_xss, 1),
        "total_xss": total_xss,
        "min_w_bal_pct": round(min_w_bal_pct, 1),
        "battery_depleted_pct": round(100.0 - min_w_bal_pct, 1),
        "focus_duration": focus
    }

def calculate_trailing_strain_systems(
    activities: Optional[List[Dict[str, Any]]] = None,
    days: int = 7,
    ftp: Optional[int] = None
) -> Dict[str, Any]:
    """
    Computes trailing 7-day and acute 48-hour sums across the three physiological systems.
    Evaluates acute fatigue in the Glycolytic and Neuromuscular systems independently.
    """
    sig = get_athlete_fitness_signature(ftp)
    cp = sig["tp"]
    
    if activities is None:
        uid = get_current_user_id()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 30", (uid,))
        rows = c.fetchall()
        conn.close()
        activities = [dict(r) for r in rows] if rows else []
        
    if not activities:
        from app.services.mock_data import get_mock_strava_activities
        activities = get_mock_strava_activities()
        
    today = datetime.date.today()
    
    daily_strains = {}
    for i in range(1, days + 1):
        d_str = (today - datetime.timedelta(days=i)).isoformat()
        daily_strains[d_str] = {"low": 0.0, "high": 0.0, "peak": 0.0, "total": 0.0}
        
    for act in activities:
        s_date = (act.get("start_date") or "")[:10]
        if s_date in daily_strains:
            st = calculate_activity_strain(act, ftp=cp)
            daily_strains[s_date]["low"] += st["low_xss"]
            daily_strains[s_date]["high"] += st["high_xss"]
            daily_strains[s_date]["peak"] += st["peak_xss"]
            daily_strains[s_date]["total"] += st["total_xss"]
            
    sorted_days = sorted(daily_strains.keys(), reverse=True) # yesterday first
    
    total_low_7d = sum(daily_strains[d]["low"] for d in daily_strains)
    total_high_7d = sum(daily_strains[d]["high"] for d in daily_strains)
    total_peak_7d = sum(daily_strains[d]["peak"] for d in daily_strains)
    total_xss_7d = sum(daily_strains[d]["total"] for d in daily_strains)
    
    # Acute 48h window (yesterday and day before)
    acute_48h_days = sorted_days[:2] if len(sorted_days) >= 2 else sorted_days
    acute_low_48h = sum(daily_strains[d]["low"] for d in acute_48h_days)
    acute_high_48h = sum(daily_strains[d]["high"] for d in acute_48h_days)
    acute_peak_48h = sum(daily_strains[d]["peak"] for d in acute_48h_days)
    acute_xss_48h = sum(daily_strains[d]["total"] for d in acute_48h_days)
    
    yesterday_key = sorted_days[0] if sorted_days else None
    yesterday_strains = daily_strains.get(yesterday_key, {"low": 0.0, "high": 0.0, "peak": 0.0, "total": 0.0}) if yesterday_key else {"low": 0.0, "high": 0.0, "peak": 0.0, "total": 0.0}
    
    # Assess acute physiological bottleneck
    if acute_high_48h >= 35.0 or yesterday_strains["high"] >= 25.0:
        system_status = "Glycolytic Debt (W' Battery Reconstitution)"
        system_badge = "🔋 W' Battery Depleted"
        system_color = "amber"
        recommendation_directive = "STEER_TO_AEROBIC_LOW"
        rationale = f"Heavy acute anaerobic work ({acute_high_48h:.1f} High Strain in last 48h). Glycolytic enzymes and W' battery are in deep recovery. Steer workout away from VO2max/intervals to pure Low Strain aerobic volume."
    elif acute_peak_48h >= 12.0 or yesterday_strains["peak"] >= 8.0:
        system_status = "Neuromuscular Recovery Required"
        system_badge = "⚡ Neuromuscular Fatigue"
        system_color = "amber"
        recommendation_directive = "STEER_TO_STEADY_STATE"
        rationale = f"Recent high neuromuscular sprint recruitment ({acute_peak_48h:.1f} Peak Strain). Fast-twitch motor units require restoration. Avoid max sprints today."
    elif total_xss_7d > 0 and (total_high_7d / total_xss_7d) > 0.25:
        system_status = "Polarized High-Load Week"
        system_badge = "🔥 High-Intensity Block"
        system_color = "cyan"
        recommendation_directive = "BALANCE_AEROBIC"
        rationale = f"High-intensity strain represents {round((total_high_7d / total_xss_7d) * 100)}% of your weekly strain. Balance with aerobic density."
    else:
        system_status = "Anaerobic Engine Fresh & Primed"
        system_badge = "⚡ W' Battery 100% Ready"
        system_color = "emerald"
        recommendation_directive = "READY_FOR_INTENSITY"
        rationale = "Anaerobic and neuromuscular systems are completely reconstituted. High-intensity intervals are fully cleared if Whoop recovery permits."
        
    return {
        "signature": sig,
        "total_xss": round(total_xss_7d, 1),
        "low_xss": round(total_low_7d, 1),
        "high_xss": round(total_high_7d, 1),
        "peak_xss": round(total_peak_7d, 1),
        "trailing_7d": {
            "low_xss": round(total_low_7d, 1),
            "high_xss": round(total_high_7d, 1),
            "peak_xss": round(total_peak_7d, 1),
            "total_xss": round(total_xss_7d, 1)
        },
        "acute_48h": {
            "low_xss": round(acute_low_48h, 1),
            "high_xss": round(acute_high_48h, 1),
            "peak_xss": round(acute_peak_48h, 1),
            "total_xss": round(acute_xss_48h, 1)
        },
        "yesterday": {
            "low_xss": round(yesterday_strains["low"], 1),
            "high_xss": round(yesterday_strains["high"], 1),
            "peak_xss": round(yesterday_strains["peak"], 1),
            "total_xss": round(yesterday_strains["total"], 1)
        },
        "system_status": system_status,
        "system_badge": system_badge,
        "system_color": system_color,
        "recommendation_directive": recommendation_directive,
        "system_rationale": rationale
    }

import datetime
from typing import Dict, Any, List, Optional
from app.database import get_setting, set_setting, get_db_connection, get_athlete_date

DEFAULT_GOALS = {
    "FTP_BUILD": {
        "id": "FTP_BUILD",
        "title": "Threshold & FTP Booster",
        "description": "Increase sustained 20-min and 60-min power output with structured sweet spot and threshold progressions.",
        "target_ftp_gain": 15,
        "weekly_tss_baseline": 360,
        "weekly_xss_baseline": 360,
        "phase_focus_duration": "Climber / Sweet Spot (45:00 Focus)",
        "target_hours": 6.5
    },
    "GRAN_FONDO": {
        "id": "GRAN_FONDO",
        "title": "Gran Fondo & Century Base",
        "description": "Build deep mitochondrial density, aerobic efficiency, and all-day fatigue resistance.",
        "target_ftp_gain": 10,
        "weekly_tss_baseline": 420,
        "weekly_xss_baseline": 420,
        "phase_focus_duration": "Endurance / Century (>1h Focus)",
        "target_hours": 8.0
    },
    "VO2_CRIT": {
        "id": "VO2_CRIT",
        "title": "Punchy Power & Criterium",
        "description": "Sharpen top-end aerobic ceiling, anaerobic capacity, and microburst recovery repeatability.",
        "target_ftp_gain": 12,
        "weekly_tss_baseline": 340,
        "weekly_xss_baseline": 340,
        "phase_focus_duration": "Puncheur / Microburst (10:00 Focus)",
        "target_hours": 5.5
    },
    "HEALTH_LONGEVITY": {
        "id": "HEALTH_LONGEVITY",
        "title": "Aerobic Health & Longevity",
        "description": "Maintain cardiovascular vitality, metabolic flexibility, and balanced autonomic recovery.",
        "target_ftp_gain": 5,
        "weekly_tss_baseline": 260,
        "weekly_xss_baseline": 260,
        "phase_focus_duration": "Endurance / Active Health (>1h Focus)",
        "target_hours": 4.5
    }
}

def get_current_program(
    strava_weekly_tss: int = 0,
    strava_weekly_xss: int = 0,
    strain_systems: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    goal_id = get_setting("program_goal", "FTP_BUILD")
    if goal_id not in DEFAULT_GOALS:
        goal_id = "FTP_BUILD"
        
    goal_def = DEFAULT_GOALS[goal_id]
    current_ftp = int(get_setting("athlete_ftp", 250))
    target_ftp = int(get_setting("program_target_ftp", current_ftp + goal_def["target_ftp_gain"]))
    weekly_tss_target = int(get_setting("program_weekly_tss_target", goal_def["weekly_tss_baseline"]))
    weekly_xss_target = int(get_setting("program_weekly_xss_target", goal_def.get("weekly_xss_baseline", weekly_tss_target)))

    # Resolve weekly XSS actual
    if strava_weekly_xss <= 0 and strain_systems:
        strava_weekly_xss = int(strain_systems.get("total_xss") or strain_systems.get("trailing_7d", {}).get("total_xss", 0))
    if strava_weekly_xss <= 0 and strava_weekly_tss > 0:
        strava_weekly_xss = strava_weekly_tss
    
    # Dates
    today = get_athlete_date()
    start_date_str = get_setting("program_start_date")
    if not start_date_str:
        # Default start 3 weeks ago
        start_date = today - datetime.timedelta(days=21)
        start_date_str = start_date.isoformat()
        set_setting("program_start_date", start_date_str)
    else:
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
        except Exception:
            start_date = today - datetime.timedelta(days=21)

    target_date_str = get_setting("program_target_date")
    if not target_date_str:
        # Default target 5 weeks ahead (8-week block total)
        target_date = today + datetime.timedelta(days=35)
        target_date_str = target_date.isoformat()
        set_setting("program_target_date", target_date_str)
    else:
        try:
            target_date = datetime.date.fromisoformat(target_date_str)
        except Exception:
            target_date = today + datetime.timedelta(days=35)

    total_days = max(7, (target_date - start_date).days)
    elapsed_days = max(0, (today - start_date).days)
    total_weeks = max(1, round(total_days / 7))
    current_week = min(total_weeks, max(1, (elapsed_days // 7) + 1))
    
    # Determine Periodization Phase (Base -> Build -> Peak -> Taper)
    pct_elapsed = min(1.0, elapsed_days / float(total_days))
    if pct_elapsed < 0.40:
        phase = "Base Phase"
        phase_focus = "Aerobic Base & Muscular Durability"
        phase_desc = "Building mitochondrial volume and cadence economy with Zone 2 foundations."
        target_focus_duration = "Endurance / Century (>1h Focus)"
        target_strain_distribution = {"low_pct": 85, "high_pct": 12, "peak_pct": 3}
    elif pct_elapsed < 0.80:
        phase = "Build Phase"
        phase_focus = "Sweet Spot & Threshold Progression"
        phase_desc = "Increasing muscular endurance and raising functional threshold power."
        target_focus_duration = "Climber / Sweet Spot (45:00 Focus)"
        target_strain_distribution = {"low_pct": 75, "high_pct": 20, "peak_pct": 5}
    elif pct_elapsed < 0.92:
        phase = "Peak Phase"
        phase_focus = "VO2 Max & Race Pacing"
        phase_desc = "High-intensity microbursts and sharpening top-end aerobic capacity."
        target_focus_duration = "Puncheur / VO2 Max (10:00 Focus)"
        target_strain_distribution = {"low_pct": 65, "high_pct": 25, "peak_pct": 10}
    else:
        phase = "Taper & Freshness"
        phase_focus = "Recovery & Event Readiness"
        phase_desc = "Volume drops by 40% to shed fatigue while keeping intensity sharp."
        target_focus_duration = "Sprinter / Neuromuscular (0:20 Focus)"
        target_strain_distribution = {"low_pct": 85, "high_pct": 10, "peak_pct": 5}

    # Weekly TSS & XSS compliance
    weekly_pct = min(100, int((strava_weekly_tss / float(weekly_tss_target)) * 100)) if weekly_tss_target > 0 else 0
    weekly_xss_pct = min(100, int((strava_weekly_xss / float(weekly_xss_target)) * 100)) if weekly_xss_target > 0 else 0
    days_left = max(0, (target_date - today).days)

    return {
        "goal_id": goal_id,
        "goal_title": goal_def["title"],
        "goal_description": goal_def["description"],
        "target_ftp": target_ftp,
        "current_ftp": current_ftp,
        "ftp_delta": target_ftp - current_ftp,
        "start_date": start_date_str,
        "target_date": target_date_str,
        "days_remaining": days_left,
        "total_weeks": total_weeks,
        "current_week": current_week,
        "phase": phase,
        "phase_focus": phase_focus,
        "phase_desc": phase_desc,
        "target_focus_duration": target_focus_duration,
        "target_strain_distribution": target_strain_distribution,
        "progress_pct": int(pct_elapsed * 100),
        "weekly_tss_target": weekly_tss_target,
        "weekly_tss_actual": strava_weekly_tss,
        "weekly_compliance_pct": weekly_pct,
        "weekly_xss_target": weekly_xss_target,
        "weekly_xss_actual": strava_weekly_xss,
        "weekly_xss_compliance_pct": weekly_xss_pct,
        "all_goals": list(DEFAULT_GOALS.values())
    }

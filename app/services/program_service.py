import datetime
from typing import Dict, Any, List, Optional
from app.database import get_setting, set_setting, get_db_connection, get_athlete_date

DEFAULT_GOALS = {
    # 6 First-Class Rider Types aligned directly with Power Spiderweb
    "PURSUITER": {
        "id": "PURSUITER",
        "title": "Pursuiter / VO2 Specialist",
        "icon": "🫁",
        "badge": "🫁 Pursuiter Target",
        "description": "Maximal Aerobic Power (MAP) development, elevated VO2 max ceiling, and 3-8 minute breakaway pacing.",
        "target_ftp_gain": 12,
        "weekly_tss_baseline": 360,
        "weekly_xss_baseline": 360,
        "phase_focus_duration": "Pursuiter / MAP (05:00 Focus)",
        "specialty_energy_system": "Maximal Aerobic Power (MAP) & Stroke Volume",
        "target_hours": 6.5
    },
    "CLIMBER": {
        "id": "CLIMBER",
        "title": "Climber",
        "icon": "⛰️",
        "badge": "⛰️ Climber Target",
        "description": "Exceptional power-to-weight ratio over extended elevation gradients and sustained alpine passes.",
        "target_ftp_gain": 15,
        "weekly_tss_baseline": 380,
        "weekly_xss_baseline": 380,
        "phase_focus_duration": "Climber / High W/kg (20:00 Focus)",
        "specialty_energy_system": "Sustained W/kg & High Aerobic Ceiling",
        "target_hours": 7.0
    },
    "ROULEUR": {
        "id": "ROULEUR",
        "title": "Rouleur / TT Specialist",
        "icon": "⏱️",
        "badge": "⏱️ Rouleur Target",
        "description": "Diesel sustained aerobic power, 20m–60m critical power, and fatigue resistance over prolonged efforts.",
        "target_ftp_gain": 15,
        "weekly_tss_baseline": 400,
        "weekly_xss_baseline": 400,
        "phase_focus_duration": "Rouleur / TT (45:00 Focus)",
        "specialty_energy_system": "20m–60m Sustained Lactate Threshold & TT Pacing",
        "target_hours": 7.0
    },
    "PUNCHEUR": {
        "id": "PUNCHEUR",
        "title": "Puncheur",
        "icon": "🥊",
        "badge": "🥊 Puncheur Target",
        "description": "Explosive 1-3 min hill attacks, sharp anaerobic capacity (W'), and repeated high-intensity surges.",
        "target_ftp_gain": 12,
        "weekly_tss_baseline": 350,
        "weekly_xss_baseline": 350,
        "phase_focus_duration": "Puncheur / Microburst (02:00 Focus)",
        "specialty_energy_system": "Anaerobic Capacity (W') & Lactate Buffering",
        "target_hours": 6.0
    },
    "SPRINTER": {
        "id": "SPRINTER",
        "title": "Sprinter",
        "icon": "⚡",
        "badge": "⚡ Sprinter Target",
        "description": "Maximal neuromuscular recruitment, high peak power (P_max), and explosive 5-second sprint velocity.",
        "target_ftp_gain": 8,
        "weekly_tss_baseline": 320,
        "weekly_xss_baseline": 320,
        "phase_focus_duration": "Sprinter / Neuromuscular (00:20 Focus)",
        "specialty_energy_system": "Peak Sprint P_max & Neuromuscular Recruitment",
        "target_hours": 5.5
    },
    "ALL_ROUNDER": {
        "id": "ALL_ROUNDER",
        "title": "All-Rounder",
        "icon": "🎯",
        "badge": "🎯 All-Rounder Target",
        "description": "Harmonious spiderweb equilibrium with versatile capabilities across sprint, anaerobic capacity, and sustained threshold.",
        "target_ftp_gain": 12,
        "weekly_tss_baseline": 380,
        "weekly_xss_baseline": 380,
        "phase_focus_duration": "All-Rounder / Polarized (20:00 Focus)",
        "specialty_energy_system": "Harmonious Multi-System Progression (+5% Envelope Lift)",
        "target_hours": 6.5
    },
    # Legacy backward-compatible archetypes
    "FTP_BUILD": {
        "id": "FTP_BUILD",
        "title": "Threshold & FTP Booster",
        "icon": "⏱️",
        "badge": "⏱️ Rouleur Target",
        "description": "Increase sustained 20-min and 60-min power output with structured sweet spot and threshold progressions.",
        "target_ftp_gain": 15,
        "weekly_tss_baseline": 360,
        "weekly_xss_baseline": 360,
        "phase_focus_duration": "Rouleur / Sweet Spot (45:00 Focus)",
        "specialty_energy_system": "20m–60m Sustained Lactate Threshold (FTP)",
        "target_hours": 6.5
    },
    "GRAN_FONDO": {
        "id": "GRAN_FONDO",
        "title": "Gran Fondo & Century Base",
        "icon": "🎯",
        "badge": "🎯 All-Rounder Target",
        "description": "Build deep mitochondrial density, aerobic efficiency, and all-day fatigue resistance.",
        "target_ftp_gain": 10,
        "weekly_tss_baseline": 420,
        "weekly_xss_baseline": 420,
        "phase_focus_duration": "Endurance / Century (>1h Focus)",
        "specialty_energy_system": "Aerobic Efficiency & Multi-System Durability",
        "target_hours": 8.0
    },
    "VO2_CRIT": {
        "id": "VO2_CRIT",
        "title": "Punchy Power & Criterium",
        "icon": "🥊",
        "badge": "🥊 Puncheur Target",
        "description": "Sharpen top-end aerobic ceiling, anaerobic capacity, and microburst recovery repeatability.",
        "target_ftp_gain": 12,
        "weekly_tss_baseline": 340,
        "weekly_xss_baseline": 340,
        "phase_focus_duration": "Puncheur / Microburst (10:00 Focus)",
        "specialty_energy_system": "Anaerobic Capacity (W') & Microburst Repeatability",
        "target_hours": 5.5
    },
    "HEALTH_LONGEVITY": {
        "id": "HEALTH_LONGEVITY",
        "title": "Aerobic Health & Longevity",
        "icon": "❤️",
        "badge": "❤️ Health Target",
        "description": "Maintain cardiovascular vitality, metabolic flexibility, and balanced autonomic recovery.",
        "target_ftp_gain": 5,
        "weekly_tss_baseline": 260,
        "weekly_xss_baseline": 260,
        "phase_focus_duration": "Endurance / Active Health (>1h Focus)",
        "specialty_energy_system": "Zone 2 Cardiovascular Vitality",
        "target_hours": 4.5
    }
}

def get_current_program(
    strava_weekly_tss: Any = 0,
    strava_weekly_xss: int = 0,
    strain_systems: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    from app.database import get_current_user_id, get_active_target_plan
    if isinstance(strava_weekly_tss, str) and not user_id:
        uid = strava_weekly_tss
        strava_weekly_tss = 0
    else:
        uid = user_id or get_current_user_id()
        try:
            strava_weekly_tss = int(strava_weekly_tss or 0)
        except (ValueError, TypeError):
            strava_weekly_tss = 0

    # 1. Check for Active Target Event (Races, Gran Fondos with fixed date)
    active_event = get_active_target_plan(uid)
    has_specific_event = bool(active_event and not active_event.get("is_past", False))

    # 2. Retrieve Active Spiderweb Goal (Rider Type or Duration Target Envelope)
    from app.services.power_profile_service import get_active_spiderweb_goal, sync_spiderweb_goal_from_program
    active_spiderweb_goal = get_active_spiderweb_goal(user_id=uid)

    saved_goal = str(get_setting("program_goal", "ALL_ROUNDER", user_id=uid)).upper()
    if saved_goal not in DEFAULT_GOALS:
        saved_goal = "ALL_ROUNDER"

    if not active_spiderweb_goal:
        try:
            active_spiderweb_goal = sync_spiderweb_goal_from_program(program_goal=saved_goal, user_id=uid)
        except Exception:
            active_spiderweb_goal = None

    # Resolve active rider type / goal definition
    effective_key = (active_spiderweb_goal.get("target_key") if active_spiderweb_goal else saved_goal).upper()
    goal_def = DEFAULT_GOALS.get(effective_key, DEFAULT_GOALS.get(saved_goal, DEFAULT_GOALS["ALL_ROUNDER"]))

    current_ftp = int(get_setting("athlete_ftp", 250, user_id=uid))

    # Target envelope from active spiderweb goal
    target_envelope = active_spiderweb_goal.get("target_envelope", {}) if active_spiderweb_goal else {}

    # Target FTP: derived from target envelope absent a specific event, or from setting
    if target_envelope.get("20m"):
        envelope_ftp = max(current_ftp + 5, round(target_envelope["20m"] * 0.95))
    elif target_envelope.get("60m"):
        envelope_ftp = max(current_ftp + 5, target_envelope["60m"])
    else:
        envelope_ftp = current_ftp + goal_def["target_ftp_gain"]

    target_ftp = int(get_setting("program_target_ftp", user_id=uid) or envelope_ftp)
    weekly_tss_target = int(get_setting("program_weekly_tss_target", goal_def["weekly_tss_baseline"], user_id=uid))
    weekly_xss_target = int(get_setting("program_weekly_xss_target", goal_def.get("weekly_xss_baseline", weekly_tss_target), user_id=uid))

    # Resolve weekly XSS actual
    if strava_weekly_xss <= 0 and strain_systems:
        strava_weekly_xss = int(strain_systems.get("total_xss") or strain_systems.get("trailing_7d", {}).get("total_xss", 0))
    if strava_weekly_xss <= 0 and strava_weekly_tss > 0:
        strava_weekly_xss = strava_weekly_tss

    today = get_athlete_date(uid)

    # Dates
    if has_specific_event:
        target_date_str = active_event["target_date"][:10]
        try:
            target_date = datetime.date.fromisoformat(target_date_str)
        except Exception:
            target_date = today + datetime.timedelta(days=35)
        start_date_str = get_setting("program_start_date", user_id=uid) or (today - datetime.timedelta(days=21)).isoformat()
        try:
            start_date = datetime.date.fromisoformat(start_date_str[:10])
        except Exception:
            start_date = today - datetime.timedelta(days=21)
    else:
        start_date_str = get_setting("program_start_date", user_id=uid)
        if not start_date_str:
            start_date = today - datetime.timedelta(days=21)
            start_date_str = start_date.isoformat()
            set_setting("program_start_date", start_date_str, user_id=uid)
        else:
            try:
                start_date = datetime.date.fromisoformat(start_date_str[:10])
            except Exception:
                start_date = today - datetime.timedelta(days=21)

        target_date_str = get_setting("program_target_date", user_id=uid)
        if not target_date_str:
            target_date = today + datetime.timedelta(days=35)
            target_date_str = target_date.isoformat()
            set_setting("program_target_date", target_date_str, user_id=uid)
        else:
            try:
                target_date = datetime.date.fromisoformat(target_date_str[:10])
            except Exception:
                target_date = today + datetime.timedelta(days=35)

    total_days = max(7, (target_date - start_date).days)
    elapsed_days = max(0, (today - start_date).days)
    total_weeks = max(1, round(total_days / 7))
    current_week = min(total_weeks, max(1, (elapsed_days // 7) + 1))
    pct_elapsed = min(1.0, elapsed_days / float(total_days))

    # Determine Periodization Phase (Base -> Build -> Peak / Specialty -> Taper / Mastery)
    is_travel_recovery = bool(get_setting("travel_recovery_week_active", False, user_id=uid))

    if is_travel_recovery:
        phase = "Recovery & Travel Week"
        phase_focus = "Rest, Recovery & Light Cross-Training"
        phase_desc = "Scheduled deload & travel week. Priority is metabolic recovery, mobility, and shedding chronic fatigue before launching a new training block next week."
        target_focus_duration = "Active Recovery & Mobility"
        target_strain_distribution = {"low_pct": 95, "high_pct": 5, "peak_pct": 0}
        phase_4_label = "4. Recovery Deload"
    elif has_specific_event:
        # Event lead-up with true race taper
        phase_4_label = "4. Taper & Fresh"
        if pct_elapsed < 0.40:
            phase = "Base Phase"
            phase_focus = "Aerobic Base & Durability"
            phase_desc = f"Building aerobic volume and muscular stamina for {active_event.get('title', 'Target Event')}."
            target_focus_duration = "Endurance / Century (>1h Focus)"
            target_strain_distribution = {"low_pct": 85, "high_pct": 12, "peak_pct": 3}
        elif pct_elapsed < 0.80:
            phase = "Build Phase"
            phase_focus = "Threshold & Sweet Spot Progression"
            phase_desc = "Lifting FTP and threshold power density towards event demands."
            target_focus_duration = "Climber / Sweet Spot (45:00 Focus)"
            target_strain_distribution = {"low_pct": 75, "high_pct": 20, "peak_pct": 5}
        elif pct_elapsed < 0.92:
            phase = "Peak Phase"
            phase_focus = "Race Pacing & Event Simulation"
            phase_desc = "Sharpening race-specific energy systems and high-intensity efforts."
            target_focus_duration = goal_def.get("phase_focus_duration", "Race Pacing (10:00 Focus)")
            target_strain_distribution = {"low_pct": 65, "high_pct": 25, "peak_pct": 10}
        else:
            phase = "Taper & Freshness"
            phase_focus = "Fatigue Shedding & Event Priming"
            phase_desc = f"Volume drops by 40% to maximize freshness for {active_event.get('title', 'Race Day')}."
            target_focus_duration = "Priming Openers (0:20 Focus)"
            target_strain_distribution = {"low_pct": 85, "high_pct": 10, "peak_pct": 5}
    else:
        # ABSENT A SPECIFIC EVENT: Rider type & target envelope drive the periodization macrocycle
        phase_4_label = "4. Mastery & Test"
        rec_workouts = active_spiderweb_goal.get("recommended_workouts", []) if active_spiderweb_goal else []
        workouts_hint = f" Key workouts: {', '.join(rec_workouts[:2])}." if rec_workouts else ""
        focus_energy = active_spiderweb_goal.get("focus_energy_system", goal_def.get("specialty_energy_system", "Specialized Energy System")) if active_spiderweb_goal else goal_def.get("specialty_energy_system", "Specialized Energy System")

        if pct_elapsed < 0.40:
            phase = "Base Phase"
            phase_focus = "Aerobic Base & Muscular Durability"
            phase_desc = f"Building deep aerobic volume and capillary foundations to support your {goal_def['title']} progression."
            target_focus_duration = "Aerobic Base (>1h Focus)"
            target_strain_distribution = {"low_pct": 85, "high_pct": 12, "peak_pct": 3}
        elif pct_elapsed < 0.75:
            phase = "Build Phase"
            phase_focus = "Threshold & Progressive Power Density"
            phase_desc = f"Expanding muscular endurance and raising your functional threshold floor toward your {target_ftp}W target."
            target_focus_duration = "Sweet Spot / Threshold (45:00 Focus)"
            target_strain_distribution = {"low_pct": 75, "high_pct": 20, "peak_pct": 5}
        elif pct_elapsed < 0.90:
            phase = "Specialty Phase"
            phase_focus = f"{focus_energy}"
            phase_desc = f"Signature weapon development for {goal_def['title']}.{workouts_hint}"
            target_focus_duration = goal_def.get("phase_focus_duration", "Specialty Interval Focus")
            target_strain_distribution = {"low_pct": 65, "high_pct": 25, "peak_pct": 10}
        else:
            phase = "Mastery & Benchmark Test"
            phase_focus = "5-Axis Target Envelope Testing"
            phase_desc = f"Target envelope validation. Testing breakthrough attempts across signature durations to confirm {goal_def['title']} capability."
            target_focus_duration = "Envelope Benchmark Testing"
            target_strain_distribution = {"low_pct": 70, "high_pct": 20, "peak_pct": 10}

    # Weekly TSS & XSS compliance
    weekly_pct = min(100, int((strava_weekly_tss / float(weekly_tss_target)) * 100)) if weekly_tss_target > 0 else 0
    weekly_xss_pct = min(100, int((strava_weekly_xss / float(weekly_xss_target)) * 100)) if weekly_xss_target > 0 else 0
    days_left = max(0, (target_date - today).days)

    # Goal title & description
    if has_specific_event:
        goal_title = f"{active_event.get('title')} Preparation"
        if active_spiderweb_goal and active_spiderweb_goal.get("target_title"):
            goal_title += f" • {active_spiderweb_goal['target_title']}"
        goal_description = f"Periodized event roadmap for {active_event.get('title')} on {target_date_str}. Developing your {active_spiderweb_goal.get('target_badge', goal_def['title'])} power envelope."
    else:
        # ABSENT A SPECIFIC EVENT: Driven directly by rider type & target envelope
        if active_spiderweb_goal and active_spiderweb_goal.get("target_title"):
            goal_title = active_spiderweb_goal["target_title"]
        else:
            goal_title = f"{goal_def['title']} Transformation"

        if target_envelope:
            env_parts = [f"{k}: {target_envelope[k]}W" for k in ["5s", "1m", "5m", "20m", "60m"] if k in target_envelope]
            env_str = " • ".join(env_parts)
            goal_description = f"Long-term phenotype adaptation block. Driving your 5-axis target envelope ({env_str}) with specialized {goal_def.get('specialty_energy_system', 'interval')} conditioning."
        else:
            goal_description = goal_def["description"]

    return {
        "goal_id": goal_def["id"],
        "base_goal_title": goal_def["title"],
        "goal_title": goal_title,
        "goal_description": goal_description,
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
        "phase_4_label": phase_4_label,
        "has_specific_event": has_specific_event,
        "event_title": active_event.get("title") if has_specific_event else None,
        "target_focus_duration": target_focus_duration,
        "target_strain_distribution": target_strain_distribution,
        "progress_pct": int(pct_elapsed * 100),
        "weekly_tss_target": weekly_tss_target,
        "weekly_tss_actual": strava_weekly_tss,
        "weekly_compliance_pct": weekly_pct,
        "weekly_xss_target": weekly_xss_target,
        "weekly_xss_actual": strava_weekly_xss,
        "weekly_xss_compliance_pct": weekly_xss_pct,
        "target_envelope": target_envelope,
        "active_spiderweb_goal": active_spiderweb_goal,
        "all_goals": list(DEFAULT_GOALS.values())
    }


def update_program_goal(goal_key: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Updates the athlete's program goal and synchronizes the spiderweb target envelope.
    """
    uid = user_id or get_current_user_id()
    clean_goal = str(goal_key).upper().strip()
    set_setting("program_goal", clean_goal, user_id=uid)
    try:
        from app.services.power_profile_service import sync_spiderweb_goal_from_program
        sync_spiderweb_goal_from_program(program_goal=clean_goal, user_id=uid)
    except Exception:
        pass
    return get_current_program(user_id=uid)


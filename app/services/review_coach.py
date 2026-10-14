import datetime
import math
import json
import requests
from typing import Dict, Any, List, Optional
from app.database import get_db_connection, get_setting, set_setting, get_active_target_plan
from app.services.mock_data import get_mock_whoop_data, get_mock_strava_activities
from app.services.program_service import get_current_program
from app.services.strava_service import get_strava_trailing_stats
from app.services.whoop_service import get_trailing_whoop_stats

def get_today_and_recent_activities() -> Dict[str, Any]:
    """
    Identifies activities completed today (or in the last 24h),
    and falls back to recent activities if none completed today.
    """
    strava_tokens = get_setting("strava_tokens", None)
    activities = []
    
    if strava_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, name, sport_type, start_date, moving_time_sec, distance_meters,
                   total_elevation_gain, average_watts, weighted_average_watts,
                   average_heartrate, max_heartrate, suffer_score, kilojoules
            FROM strava_activities
            ORDER BY start_date DESC
            LIMIT 15
        """)
        rows = c.fetchall()
        conn.close()
        activities = [dict(r) for r in rows]
    
    if not activities:
        activities = get_mock_strava_activities()

    today_iso = datetime.date.today().isoformat()
    
    today_activities = []
    for a in activities:
        # Determine the activity's local or calendar date
        act_date = a.get("start_date", "")[:10]
        raw_str = a.get("raw_json")
        if raw_str:
            try:
                import ast
                raw_dict = ast.literal_eval(raw_str) if isinstance(raw_str, str) and raw_str.startswith("{") else {}
                local_start = raw_dict.get("start_date_local", "")
                if local_start:
                    act_date = local_start[:10]
            except Exception:
                pass
        
        if act_date == today_iso:
            today_activities.append(a)

    latest_activity = activities[0] if activities else None

    return {
        "today_activities": today_activities,
        "has_trained_today": len(today_activities) > 0,
        "latest_activity": latest_activity,
        "all_recent": activities[:5]
    }

def get_whoop_for_date(target_date_str: str) -> Optional[Dict[str, Any]]:
    """Fetches stored Whoop metrics for a specific date (YYYY-MM-DD)."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT date, recovery_score, hrv_rmssd, resting_heart_rate,
               sleep_performance, sleep_duration_hours, day_strain
        FROM whoop_metrics
        WHERE date = ?
    """, (target_date_str,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def parse_athlete_feedback_for_outlook(note: str, today: datetime.date, ftp: int = 250) -> Dict[int, Dict[str, Any]]:
    """
    Parses subjective athlete debrief notes (e.g. 'tomorrow will be zone 2 or a rest day',
    'tired from poor sleep', 'Friday rest day') to dynamically adapt the 3-day forecast.
    """
    if not note or not note.strip():
        return {}

    n = note.lower().strip()
    overrides = {}

    # 1. Determine target day offset(s)
    target_offsets = []
    weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for off in [1, 2, 3]:
        d = today + datetime.timedelta(days=off)
        w_name = weekday_names[d.weekday()]
        if w_name in n:
            target_offsets.append(off)

    if not target_offsets:
        if any(w in n for w in ["tomorrow", "tmrw", "next day"]):
            target_offsets = [1]
        elif any(w in n for w in ["day after tomorrow", "in two days", "+2"]):
            target_offsets = [2]
        elif any(w in n for w in ["in three days", "+3"]):
            target_offsets = [3]
        else:
            # Default to tomorrow (offset 1) if subjective note targets upcoming training
            target_offsets = [1]

    has_rest = any(w in n for w in ["rest day", "rest", "day off", "off day", "take off", "passive rest", "skip"])
    has_z2 = any(w in n for w in ["zone 2", "zone 1", "z2", "z1", "easy spin", "easy ride", "flush", "recovery spin", "endurance"])
    has_fatigue = any(w in n for w in ["tired", "fatigued", "exhausted", "fried", "sore", "poor sleep", "bad sleep", "drained", "heavy legs", "sluggish", "cooked"])

    for off in target_offsets:
        if has_rest and has_z2:
            overrides[off] = {
                "type": "zone_2_or_rest",
                "title": "Zone 2 Spin or Rest Day",
                "duration_min": 35,
                "estimated_tss": 20,
                "estimated_xss": 20,
                "low_xss": 20,
                "high_xss": 0,
                "peak_xss": 0,
                "focus": "Active Recovery or Rest",
                "focus_duration": "Active Recovery / Base (>1h Focus)",
                "description": f"Adapted to your note (\"{note}\"): High-intensity intervals removed. Gentle Zone 2 spin (<65% FTP, <{int(ftp * 0.65)}W, ~20 Low XSS) or optional rest day."
            }
        elif has_rest:
            overrides[off] = {
                "type": "rest",
                "title": "Rest Day",
                "duration_min": 0,
                "estimated_tss": 0,
                "estimated_xss": 0,
                "low_xss": 0,
                "high_xss": 0,
                "peak_xss": 0,
                "focus": "Rest & Recovery",
                "focus_duration": "Rest & Recovery",
                "description": f"Adapted to your note (\"{note}\"): Scheduled rest day. Focus on hydration, mobility, and restorative sleep."
            }
        elif has_z2:
            overrides[off] = {
                "type": "zone_2",
                "title": "Zone 2 Aerobic Base",
                "duration_min": 35,
                "estimated_tss": 24,
                "estimated_xss": 24,
                "low_xss": 24,
                "high_xss": 0,
                "peak_xss": 0,
                "focus": "Aerobic Base",
                "focus_duration": "Endurance / Century (>1h Focus)",
                "description": f"Adapted to your note (\"{note}\"): Steady Zone 2 endurance spin (<68% FTP, <{int(ftp * 0.68)}W) with progressive ramp warmup and cooldown."
            }
        elif has_fatigue:
            overrides[off] = {
                "type": "fatigue_downgrade",
                "title": "Active Recovery (35m)",
                "duration_min": 35,
                "estimated_tss": 18,
                "estimated_xss": 18,
                "low_xss": 18,
                "high_xss": 0,
                "peak_xss": 0,
                "focus": "Active Recovery",
                "focus_duration": "Active Recovery (>1h Focus)",
                "description": f"Adjusted for reported fatigue (\"{note}\"): Easy 35-minute recovery spin (<55% FTP, <{int(ftp * 0.55)}W) or rest day to recover."
            }

    return overrides

def build_preference_aligned_outlook_days(
    today: datetime.date,
    today_recovery: int,
    today_strain: float,
    workout_strain: float,
    is_today: bool,
    is_yesterday: bool,
    has_trained_today: bool,
    session_summary: Dict[str, Any],
    ftp: int,
    program: Dict[str, Any],
    custom_prompt: str = ""
) -> List[Dict[str, Any]]:
    """
    Constructs a 3-day forward forecast that models acute fatigue decay (tau ~ 3.0 days)
    while strictly aligning with the athlete's persistent weekly schedule preferences:
      - Monday, Tuesday, Thursday: 35–45 minutes ONLY (indoor efficiency, secondary rest candidates)
      - Wednesday & Friday: 60+ minutes (an hour or more, outdoor priority if weather allows)
      - Saturday: Dedicated weekly rest day (0 min)
      - Sunday: 60–90+ minutes (longer outdoor endurance or long indoor session)
      - Warmup/Cooldown: Progressive wattage ramps (never flat Zone 2 blocks)
      - Threshold / Sweet Spot: Strongly favors Over/Under intervals
      - Dynamically adapts to subjective athlete notes (e.g. 'tomorrow will be zone 2 or a rest day')
    """
    from app.services.preferences_service import get_day_target_config, get_weekday_rest_quota_and_status

    rest_quota_status = get_weekday_rest_quota_and_status(ref_date=today)
    must_rest_days = rest_quota_status.get("must_rest_days", [])

    trained_today_heavy = is_today and ((workout_strain >= 13.5) or (session_summary.get("suffer_score", 0) >= 60))
    trained_yesterday_heavy = is_yesterday and ((workout_strain >= 13.5) or (session_summary.get("suffer_score", 0) >= 40) or (session_summary.get("verdict") == "Intensity Overreach"))
    today_passive_or_light = (not has_trained_today) and (today_strain < 13.5)

    # Parse athlete subjective notes for dynamic forecast adaptation
    feedback_overrides = parse_athlete_feedback_for_outlook(custom_prompt, today, ftp)

    # 1. Base recovery progression over next 3 days
    if trained_today_heavy:
        # Acute fatigue spike peaks tomorrow morning (Day +1)
        day1_recovery = max(38, min(62, today_recovery - 10))
        day2_recovery = min(84, day1_recovery + 24)
        day3_recovery = min(88, day2_recovery + 6)
    elif trained_yesterday_heavy and today_passive_or_light:
        # 48 hours post-workout: fatigue clears, recovery rebounds
        day1_recovery = min(74, today_recovery + 22)
        day2_recovery = min(86, day1_recovery + 14)
        day3_recovery = 76
    else:
        # Standard balanced progression
        day1_recovery = min(88, today_recovery + 12)
        day2_recovery = max(45, day1_recovery - 14)
        day3_recovery = 74

    recoveries = [day1_recovery, day2_recovery, day3_recovery]
    outlook_days = []

    for offset in [1, 2, 3]:
        target_date = today + datetime.timedelta(days=offset)
        rec_est = recoveries[offset - 1]
        zone = "green" if rec_est > 66 else ("yellow" if rec_est >= 34 else "red")
        date_relative = "Tomorrow" if offset == 1 else f"Day +{offset}"
        date_formatted = target_date.strftime("%a, %b %-d")

        cfg = get_day_target_config(target_date)
        w_key = cfg.get("weekday_key", "")
        day_name = cfg.get("day_name", w_key.capitalize())
        min_dur = cfg.get("min_duration_min", 35)
        max_dur = cfg.get("max_duration_min", 45)
        preferred_dur = cfg.get("preferred_duration_min", 45)
        is_directive_rest = (w_key in must_rest_days) or cfg.get("is_directive_rest", False)
        is_default_rest = (cfg.get("is_default_rest", False) and not is_directive_rest) or (w_key == "saturday")
        mode = cfg.get("mode", "indoor_priority")

        # CASE 0: Directive-Mandated Rest / Easy Day (e.g. Thursday when Mon/Tue/Wed workouts were logged)
        if is_directive_rest:
            item = {
                "day_offset": offset,
                "date_relative": date_relative,
                "date_formatted": date_formatted,
                "projected_recovery": max(78, rec_est),
                "projected_zone": "green",
                "title": "Rest Day or Easy Spin",
                "duration_min": 0,
                "estimated_tss": 0,
                "estimated_xss": 0,
                "low_xss": 0,
                "high_xss": 0,
                "peak_xss": 0,
                "focus_duration": "Rest & Recovery",
                "focus": "Rest & Recovery",
                "is_directive_rest": True,
                "description": (
                    f"Expected Recovery: ~{max(78, rec_est)}% (Supercompensation). "
                    f"Per your forward directive, {day_name} is recommended as a full rest day or gentle active recovery spin "
                    f"(<55% FTP, <{int(ftp * 0.55)}W, ~15 Low XSS) to allow cellular supercompensation before Friday's ride."
                )
            }

        # CASE A: Dedicated Rest Day (e.g. Saturday)
        elif is_default_rest or mode == "rest_day":
            item = {
                "day_offset": offset,
                "date_relative": date_relative,
                "date_formatted": date_formatted,
                "projected_recovery": rec_est,
                "projected_zone": zone,
                "title": "Rest & Recovery",
                "duration_min": 0,
                "estimated_tss": 0,
                "estimated_xss": 0,
                "low_xss": 0,
                "high_xss": 0,
                "peak_xss": 0,
                "focus_duration": "Rest & Recovery",
                "focus": "Rest & Recovery",
                "description": (
                    f"Expected Recovery: ~{rec_est}% ({zone.capitalize()}). Dedicated weekly rest day consistent with your scheduling preferences. "
                    f"Focus on hydration, mobility, and restorative sleep before Sunday's longer endurance ride."
                )
            }

        # CASE B: Sunday (Outdoor or Long Indoor Ride)
        elif w_key == "sunday" or mode == "outdoor_or_long_indoor":
            dur = max(60, min(90, preferred_dur or 75))
            if rec_est >= 60:
                est_tss = int(dur * 0.95)
                est_xss = est_tss
                low_x = int(est_xss * 0.85)
                high_x = int(est_xss * 0.15)
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": "Outdoor Endurance or Long Indoor Ride",
                    "duration_min": dur,
                    "estimated_tss": est_tss,
                    "estimated_xss": est_xss,
                    "low_xss": low_x,
                    "high_xss": high_x,
                    "peak_xss": 0,
                    "focus_duration": "Rouleur (20:00 Focus)",
                    "focus": "Aerobic Endurance",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% (Prime). Sunday volume ride ({dur} min, outdoors if weather permits, or indoor endurance). "
                        f"Features progressive wattage ramps to build endurance and contribute toward your weekly {program.get('weekly_tss_target', 360)} TSS target."
                    )
                }
            else:
                dur = 60
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": "Zone 2 Endurance",
                    "duration_min": 60,
                    "estimated_tss": 42,
                    "estimated_xss": 42,
                    "low_xss": 42,
                    "high_xss": 0,
                    "peak_xss": 0,
                    "focus_duration": "Endurance / Century (>1h Focus)",
                    "focus": "Aerobic Base",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% ({zone.capitalize()}). Steady 60-minute Zone 2 spin "
                        f"(<{int(ftp * 0.68)}W, ~42 Low XSS) with progressive ramp warmup and cooldown."
                    )
                }

        # CASE C: Wednesday & Friday (60+ Minutes, Outdoor Priority if Weather Allows)
        elif w_key in ["wednesday", "friday"] or mode == "outdoor_priority":
            dur = max(60, min(90, preferred_dur or 60))
            if rec_est >= 66:
                est_tss = 65 if dur == 60 else 75
                est_xss = 68 if dur == 60 else 78
                low_x = 50 if dur == 60 else 58
                high_x = 18 if dur == 60 else 20
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": "Sweet Spot Over-Unders",
                    "duration_min": dur,
                    "estimated_tss": est_tss,
                    "estimated_xss": est_xss,
                    "low_xss": low_x,
                    "high_xss": high_x,
                    "peak_xss": 0,
                    "focus_duration": "Climber / Sweet Spot (45:00 Focus)",
                    "focus": "Sweet Spot & Threshold",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% (Green). Prescribed {dur}+ min session consistent with your {day_name} preference (outdoors if weather permits, or indoor). "
                        f"Features progressive wattage ramp warmup and structured Over/Under intervals ({int(ftp * 0.90)}W / {int(ftp * 1.05)}W) to build threshold power."
                    )
                }
            elif rec_est >= 45:
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": "Zone 2 Aerobic Foundation",
                    "duration_min": 60,
                    "estimated_tss": 46,
                    "estimated_xss": 46,
                    "low_xss": 44,
                    "high_xss": 2,
                    "peak_xss": 0,
                    "focus_duration": "Endurance / Century (>1h Focus)",
                    "focus": "Aerobic Base",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% (Yellow). 60-min steady Zone 2 ride (outdoors if weather permits) with progressive ramp warmup and cooldown."
                    )
                }
            else:
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": "Active Recovery or Rest",
                    "duration_min": 45,
                    "estimated_tss": 22,
                    "estimated_xss": 22,
                    "low_xss": 22,
                    "high_xss": 0,
                    "peak_xss": 0,
                    "focus_duration": "Active Recovery (>1h Focus)",
                    "focus": "Active Recovery",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% (Red). Easy active recovery spin (<55% FTP, <{int(ftp * 0.55)}W) or complete rest to allow full recovery."
                    )
                }

        # CASE D: Monday, Tuesday, Thursday (35–45 Minutes ONLY, Secondary Rest Candidates)
        else:
            if rec_est < 50:
                # Active flush or rest day candidate
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": "Active Recovery or Rest (35m)",
                    "duration_min": 35,
                    "estimated_tss": 18,
                    "estimated_xss": 18,
                    "low_xss": 18,
                    "high_xss": 0,
                    "peak_xss": 0,
                    "focus_duration": "Active Recovery (>1h Focus)",
                    "focus": "Active Recovery",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% ({'Red' if rec_est < 34 else 'Yellow'}). Consistent with your preference that one of Mon/Tue/Thu serves as an extra rest day: "
                        f"35-min gentle spin (<55% FTP, <{int(ftp * 0.55)}W) or rest day to absorb recent training stress."
                    )
                }
            else:
                # High-efficiency 40-minute Over/Unders session
                dur = min(45, max(35, preferred_dur or 40))
                item = {
                    "day_offset": offset,
                    "date_relative": date_relative,
                    "date_formatted": date_formatted,
                    "projected_recovery": rec_est,
                    "projected_zone": zone,
                    "title": f"⚡ {dur}-Min Sweet Spot Over-Unders",
                    "duration_min": dur,
                    "estimated_tss": 45,
                    "estimated_xss": 46,
                    "low_xss": 34,
                    "high_xss": 12,
                    "peak_xss": 0,
                    "focus_duration": "Climber / Sweet Spot (45:00 Focus)",
                    "focus": "Sweet Spot & Threshold",
                    "description": (
                        f"Expected Recovery: ~{rec_est}% (Ready). High-efficiency {dur}-minute indoor session respecting your 35–45 min weekday limit. "
                        f"Includes a progressive wattage ramp warmup (45% -> 75% FTP), structured Over/Under threshold blocks ({int(ftp * 0.90)}W / {int(ftp * 1.05)}W), and progressive ramp cooldown."
                    )
                }

        # Check for athlete subjective debrief note overrides (e.g. "tomorrow will be zone 2 or a rest day")
        if offset in feedback_overrides:
            ovr = feedback_overrides[offset]
            item["title"] = ovr["title"]
            item["duration_min"] = ovr["duration_min"]
            item["estimated_tss"] = ovr["estimated_tss"]
            item["estimated_xss"] = ovr["estimated_xss"]
            item["low_xss"] = ovr["low_xss"]
            item["high_xss"] = ovr["high_xss"]
            item["peak_xss"] = ovr["peak_xss"]
            item["focus"] = ovr["focus"]
            item["focus_duration"] = ovr["focus_duration"]
            item["description"] = ovr["description"]
            item["is_athlete_adjusted"] = True

        outlook_days.append(item)

    return outlook_days

def build_daily_review_and_outlook_local(
    whoop_data: Dict[str, Any],
    trailing_strava: Dict[str, Any],
    today_acts: List[Dict[str, Any]],
    latest_act: Optional[Dict[str, Any]],
    program: Dict[str, Any],
    ftp: int = 250,
    max_hr: int = 185,
    custom_prompt: str = ""
) -> Dict[str, Any]:
    """
    Generates a deep physiological Debrief of completed workouts
    and a forward-looking 3-day training outlook based on acute fatigue decay.
    Accurately distinguishes sessions completed today vs. yesterday/earlier.
    """
    today = datetime.date.today()
    today_iso = today.isoformat()
    yesterday_iso = (today - datetime.timedelta(days=1)).isoformat()
    
    today_recovery = int(whoop_data.get("recovery_score", 50))
    today_hrv = float(whoop_data.get("hrv_rmssd", 40.0))
    today_strain = float(whoop_data.get("day_strain", 0.0))
    sleep_score = int(whoop_data.get("sleep_performance", 85))
    sleep_needed = float(whoop_data.get("sleep_needed_hours", 8.0))
    
    acute_tss = int(trailing_strava.get("acute_weighted_tss", 0))
    total_tss = int(trailing_strava.get("total_tss", 0))
    load_profile = trailing_strava.get("load_profile", "Evenly Distributed")
    
    has_trained_today = len(today_acts) > 0
    analyzed_act = today_acts[0] if has_trained_today else latest_act
    
    # 1. EVALUATION OF COMPLETED SESSION
    if analyzed_act:
        act_name = analyzed_act.get("name", "Ride")
        act_sec = analyzed_act.get("moving_time_sec", 0)
        act_min = act_sec // 60
        act_dist_km = round(analyzed_act.get("distance_meters", 0) / 1000.0, 1)
        act_elev_m = int(analyzed_act.get("total_elevation_gain", 0))
        act_watts = round(analyzed_act.get("weighted_average_watts") or analyzed_act.get("average_watts") or 0.0)
        act_hr = round(analyzed_act.get("average_heartrate") or 0)
        act_suffer = int(analyzed_act.get("suffer_score") or 0)
        pct_ftp = round((act_watts / max(1, ftp)) * 100) if act_watts > 0 else 65

        from app.services.strain_model_service import calculate_activity_strain
        act_strain = calculate_activity_strain(analyzed_act, ftp=ftp)

        # Determine activity date
        act_date_str = analyzed_act.get("start_date", "")[:10]
        raw_str = analyzed_act.get("raw_json")
        if raw_str:
            try:
                import ast
                raw_dict = ast.literal_eval(raw_str) if isinstance(raw_str, str) and raw_str.startswith("{") else {}
                local_start = raw_dict.get("start_date_local", "")
                if local_start:
                    act_date_str = local_start[:10]
            except Exception:
                pass

        is_today = (act_date_str == today_iso)
        is_yesterday = (act_date_str == yesterday_iso)
        
        try:
            act_d = datetime.date.fromisoformat(act_date_str)
            days_ago = (today - act_d).days
        except Exception:
            days_ago = 0 if is_today else (1 if is_yesterday else 2)

        if is_today:
            relative_day_label = "Today"
        elif is_yesterday:
            relative_day_label = "Yesterday"
        else:
            relative_day_label = f"{days_ago} Days Ago"

        # Query Whoop telemetry specifically for the date the activity occurred
        workout_whoop = get_whoop_for_date(act_date_str)
        if workout_whoop:
            workout_recovery = int(workout_whoop.get("recovery_score") or 50)
            workout_strain = float(workout_whoop.get("day_strain") or 0.0)
            workout_hrv = float(workout_whoop.get("hrv_rmssd") or 40.0)
        elif is_today:
            workout_recovery = today_recovery
            workout_strain = today_strain
            workout_hrv = today_hrv
        else:
            workout_recovery = 50
            workout_strain = 12.0
            workout_hrv = 35.0

        # Check pacing fidelity relative to the recovery on the day of the workout
        if workout_recovery < 34:
            target_pct_ftp = 50
            target_zone_name = "Zone 1 Active Recovery"
        elif workout_recovery <= 66:
            target_pct_ftp = 66
            target_zone_name = "Zone 2 Aerobic Base"
        else:
            target_pct_ftp = 90
            target_zone_name = "Sweet Spot / VO2 Max"

        power_diff = act_watts - int(ftp * (target_pct_ftp / 100.0))
        diff_pct = abs(pct_ftp - target_pct_ftp)
        compliance_score = max(55, min(99, 100 - int(diff_pct * 1.5)))

        if diff_pct <= 8:
            verdict = "Execution Bullseye"
            verdict_badge = "🎯 Target Mastered"
            verdict_color = "emerald"
            if is_today:
                assessment_text = (
                    f"Outstanding discipline during today's '{act_name}' ({act_min}m, {act_watts}W avg, {pct_ftp}% FTP). "
                    f"You matched your {workout_recovery}% Whoop recovery by holding power within your target "
                    f"{target_zone_name} ceiling ({workout_strain:.1f} Whoop day strain). Your average heart rate ({act_hr} bpm) "
                    f"indicates clean aerobic effort without excessive strain."
                )
            elif is_yesterday:
                assessment_text = (
                    f"Outstanding pacing discipline during yesterday's '{act_name}' ({act_min}m, {act_watts}W avg, {pct_ftp}% FTP). "
                    f"You executed to your {workout_recovery}% Whoop recovery baseline, logging {act_suffer} TSS and "
                    f"{workout_strain:.1f} day strain within your target {target_zone_name}. This balanced aerobic stimulus "
                    f"protected recovery, keeping today's readiness at {today_recovery}% ({today_strain:.1f} strain today)."
                )
            else:
                assessment_text = (
                    f"Disciplined pacing in '{act_name}' from {relative_day_label} ({act_min}m, {act_watts}W avg, {pct_ftp}% FTP, "
                    f"{workout_strain:.1f} strain on {workout_recovery}% recovery). Today's recovery sits at {today_recovery}%."
                )
        elif pct_ftp > target_pct_ftp + 8:
            verdict = "Intensity Overreach"
            verdict_badge = "⚠️ Exceeded Target Zone"
            verdict_color = "amber"
            if is_today:
                assessment_text = (
                    f"In today's session '{act_name}' ({act_min}m, {act_watts}W, {pct_ftp}% FTP), power was pushed {diff_pct}% "
                    f"above your prescribed {target_zone_name} target. While cardiovascular stimulus was strong "
                    f"({act_suffer} TSS logged, {workout_strain:.1f} Whoop strain), digging into anaerobic and sweet-spot reserves "
                    f"on a {workout_recovery}% recovery day shifts your acute fatigue load upward. "
                    f"Prioritize hydration and sleep tonight to ensure tomorrow's adaptation."
                )
            elif is_yesterday:
                assessment_text = (
                    f"In yesterday's session '{act_name}' ({act_min}m, {act_watts}W, {pct_ftp}% FTP), power was pushed {diff_pct}% "
                    f"above your prescribed {target_zone_name} target. You logged {act_suffer} TSS and accumulated a heavy "
                    f"{workout_strain:.1f} Whoop day strain against a {workout_recovery}% recovery baseline. Digging into anaerobic "
                    f"and sweet-spot reserves yesterday is the primary driver of today's recovery dip to {today_recovery}% "
                    f"(with {today_strain:.1f} Whoop strain accumulated so far today). With today serving as an absorption day, "
                    f"prioritize restorative sleep tonight to clear residual glycogen debt and unlock tomorrow's rebound."
                )
            else:
                assessment_text = (
                    f"In '{act_name}' from {relative_day_label} ({act_min}m, {act_watts}W, {pct_ftp}% FTP), power was pushed {diff_pct}% "
                    f"above your prescribed {target_zone_name} target ({act_suffer} TSS logged, {workout_strain:.1f} Whoop strain on "
                    f"{workout_recovery}% recovery). Today's recovery sits at {today_recovery}% with {today_strain:.1f} daytime strain."
                )
        else:
            verdict = "Conservative Pacing"
            verdict_badge = "🛡️ Recovery Preserved"
            verdict_color = "cyan"
            if is_today:
                assessment_text = (
                    f"Controlled session in today's '{act_name}' ({act_min}m, {act_watts}W, {pct_ftp}% FTP). "
                    f"You kept cardiac stress low ({act_hr} bpm), absorbing an easy active recovery stimulus "
                    f"({workout_strain:.1f} Whoop day strain). Your energy reserves remain well-protected for upcoming training."
                )
            elif is_yesterday:
                assessment_text = (
                    f"Controlled session during yesterday's '{act_name}' ({act_min}m, {act_watts}W, {pct_ftp}% FTP, "
                    f"{workout_strain:.1f} day strain). You kept cardiac stress low ({act_hr} bpm), preserving energy "
                    f"and supporting today's recovery ({today_recovery}%)."
                )
            else:
                assessment_text = (
                    f"Controlled session in '{act_name}' from {relative_day_label} ({act_min}m, {act_watts}W, {pct_ftp}% FTP, "
                    f"{workout_strain:.1f} strain on {workout_recovery}% recovery). Today's recovery sits at {today_recovery}%."
                )

        session_summary = {
            "title": act_name,
            "is_today": is_today,
            "is_yesterday": is_yesterday,
            "relative_day_label": relative_day_label,
            "date": act_date_str,
            "moving_time_formatted": f"{act_min // 60}h {act_min % 60}m" if act_min >= 60 else f"{act_min}m",
            "moving_time_min": act_min,
            "distance_km": act_dist_km,
            "distance_miles": round(act_dist_km * 0.621371, 1),
            "elevation_m": act_elev_m,
            "elevation_ft": int(act_elev_m * 3.28084),
            "weighted_watts": act_watts,
            "pct_ftp": pct_ftp,
            "avg_hr": act_hr,
            "suffer_score": act_suffer,
            "compliance_score": compliance_score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "verdict_color": verdict_color,
            "assessment_text": assessment_text,
            "workout_strain": workout_strain,
            "workout_recovery": workout_recovery,
            "today_strain": today_strain,
            "today_recovery": today_recovery,
            "day_strain": workout_strain if not is_today else today_strain,
            "target_zone": target_zone_name,
            "target_watts": int(ftp * (target_pct_ftp / 100.0)),
            "low_strain_xss": act_strain.get("low_xss", 0.0),
            "high_strain_xss": act_strain.get("high_xss", 0.0),
            "peak_strain_xss": act_strain.get("peak_xss", 0.0),
            "total_xss": act_strain.get("total_xss", 0.0),
            "min_w_bal_pct": act_strain.get("min_w_bal_pct", 100.0),
            "battery_depleted_pct": act_strain.get("battery_depleted_pct", 0.0),
            "focus_duration": act_strain.get("focus_duration", "Endurance / Century (>1h Focus)"),
            "strain_data": act_strain
        }
    else:
        is_today = True
        is_yesterday = False
        workout_strain = 0.0
        workout_recovery = today_recovery
        session_summary = {
            "title": "Rest / Off-Bike Day",
            "is_today": True,
            "is_yesterday": False,
            "relative_day_label": "Today",
            "date": today_iso,
            "moving_time_formatted": "0m",
            "moving_time_min": 0,
            "compliance_score": 100,
            "verdict": "Full Rest Observed",
            "verdict_badge": "🛋️ Passive Recovery",
            "verdict_color": "emerald",
            "assessment_text": (
                f"Zero moving time logged today. With today's Whoop recovery of {today_recovery}% and current day strain of {today_strain:.1f}, "
                f"taking a rest day allows fatigue to clear before your next structured session."
            ),
            "workout_strain": 0.0,
            "workout_recovery": today_recovery,
            "today_strain": today_strain,
            "today_recovery": today_recovery,
            "day_strain": today_strain,
            "target_zone": "Passive Rest",
            "target_watts": 0,
            "low_strain_xss": 0.0,
            "high_strain_xss": 0.0,
            "peak_strain_xss": 0.0,
            "total_xss": 0.0,
            "min_w_bal_pct": 100.0,
            "battery_depleted_pct": 0.0,
            "focus_duration": "Rest / Recovery",
            "strain_data": {
                "low_xss": 0.0,
                "high_xss": 0.0,
                "peak_xss": 0.0,
                "total_xss": 0.0,
                "min_w_bal_pct": 100.0,
                "battery_depleted_pct": 0.0,
                "focus_duration": "Rest / Recovery"
            }
        }

    # 2. MULTI-DAY OUTLOOK (Next 3 Days)
    # Model forward fatigue decay (tau = 3.0 days) strictly compliant with athlete weekly schedule preferences
    outlook_days = build_preference_aligned_outlook_days(
        today=today,
        today_recovery=today_recovery,
        today_strain=today_strain,
        workout_strain=workout_strain,
        is_today=is_today,
        is_yesterday=is_yesterday,
        has_trained_today=has_trained_today,
        session_summary=session_summary,
        ftp=ftp,
        program=program,
        custom_prompt=custom_prompt
    )

    # Check if athlete has an active upcoming target plan
    active_plan = get_active_target_plan()
    days_until_event = active_plan.get("days_until") if active_plan else None

    # Dynamically inject target event into outlook if within horizon
    if active_plan and days_until_event is not None and days_until_event >= 1:
        p_title = active_plan.get("title", "Target Event")
        p_dist = float(active_plan.get("distance_miles") or 50.0)
        p_tss = int(active_plan.get("estimated_tss") or 160)
        p_dur = int(active_plan.get("estimated_duration_min") or 180)
        p_type = active_plan.get("intensity_type", "Endurance")

        for item in outlook_days:
            offset = item["day_offset"]
            if item.get("is_athlete_adjusted"):
                continue
            if offset == days_until_event:
                # Target Event Day
                est_xss = int(p_tss * 1.05) if p_type in ["Punchy / Rolling", "Climber / Hilly"] else p_tss
                low_x = int(est_xss * 0.8)
                high_x = int(est_xss * 0.15)
                peak_x = max(0, est_xss - low_x - high_x)
                f_dur = "Rouleur (20:00 Focus)" if p_type == "Tempo / Steady" else ("Climber / Sweet Spot (45:00 Focus)" if p_type == "Climber / Hilly" else "Endurance / Century (>1h Focus)")

                item["title"] = f"🎯 TARGET EVENT: {p_title}"
                item["focus"] = f"{p_dist:.1f} Miles • {p_type}"
                item["duration_min"] = p_dur
                item["estimated_tss"] = p_tss
                item["estimated_xss"] = est_xss
                item["low_xss"] = low_x
                item["high_xss"] = high_x
                item["peak_xss"] = peak_x
                item["focus_duration"] = f_dur
                item["projected_recovery"] = 84
                item["projected_zone"] = "green"
                item["description"] = (
                    f"TARGET EVENT DAY: {p_title} ({p_dist:.1f} mi, est. {est_xss} XSS / {p_tss} TSS). "
                    f"Target pacing: {p_type} ({f_dur}). Fuel with 60–80g carbs/hr and maintain consistent electrolyte hydration."
                )
            elif offset == days_until_event - 1:
                # T-1 Day
                item["title"] = "⚡ Pre-Event Neuromuscular Primer"
                item["focus"] = "Neural Priming & Glycogen Sparing"
                item["duration_min"] = 30
                item["estimated_tss"] = 22
                item["estimated_xss"] = 22
                item["low_xss"] = 14
                item["high_xss"] = 5
                item["peak_xss"] = 3
                item["focus_duration"] = "Sprinter / Neuromuscular (0:20 Focus)"
                item["projected_recovery"] = 78
                item["projected_zone"] = "green"
                item["description"] = (
                    f"T-1 Primer: 30-min easy spin with 3x 30s cadence openers (~22 XSS). "
                    f"Wakes up motor unit firing while sparing glycogen for tomorrow's {p_dist:.1f} mi ride."
                )
            elif offset == days_until_event - 2:
                # T-2 Day
                item["title"] = "Pre-Event Recovery Spin"
                item["focus"] = "Active Recovery"
                item["duration_min"] = 35
                item["estimated_tss"] = 20
                item["estimated_xss"] = 20
                item["low_xss"] = 20
                item["high_xss"] = 0
                item["peak_xss"] = 0
                item["focus_duration"] = "Active Flush / Base (>1h Focus)"
                item["projected_recovery"] = 70
                item["projected_zone"] = "green"
                item["description"] = (
                    f"T-2 Primer: Gentle Zone 1 spin (<55% FTP, ~20 Low XSS) to promote recovery before {p_title}."
                )

    # 2b. Dynamically inject Coach-Scheduled Workouts into 3-Day Forecast
    from app.database import get_scheduled_workout_for_date
    for item in outlook_days:
        offset = item["day_offset"]
        # If athlete explicitly requested rest or zone 2 for this day, or if day is directive rest, honor it
        if item.get("is_athlete_adjusted") or item.get("is_directive_rest"):
            continue

        target_iso = (today + datetime.timedelta(days=offset)).isoformat()
        scheduled_w = get_scheduled_workout_for_date(target_iso)
        if scheduled_w:
            w_title = scheduled_w.get("title", "Scheduled Workout")
            w_dur = int(scheduled_w.get("duration_minutes") or 45)
            w_tss = int(scheduled_w.get("estimated_tss") or 50)
            w_focus = scheduled_w.get("focus_area") or "Structured Intervals"
            w_desc = scheduled_w.get("description") or f"Scheduled {w_focus} workout with AI Coach."

            est_xss = int(w_tss * 1.05) if ("vo2" in w_focus.lower() or "over-under" in w_focus.lower()) else w_tss
            if "over-under" in w_focus.lower() or "threshold" in w_focus.lower():
                low_x = int(est_xss * 0.65)
                high_x = int(est_xss * 0.30)
                peak_x = max(0, est_xss - low_x - high_x)
                f_dur = "Climber / Sweet Spot (45:00 Focus)"
            elif "vo2" in w_focus.lower():
                low_x = int(est_xss * 0.50)
                high_x = int(est_xss * 0.40)
                peak_x = max(0, est_xss - low_x - high_x)
                f_dur = "Pursuiter / VO2 Max (6:00 Focus)"
            elif "sweet spot" in w_focus.lower():
                low_x = int(est_xss * 0.75)
                high_x = int(est_xss * 0.25)
                peak_x = 0
                f_dur = "Climber / Sweet Spot (45:00 Focus)"
            elif "recovery" in w_focus.lower():
                low_x = est_xss
                high_x = 0
                peak_x = 0
                f_dur = "Active Recovery (>1h Focus)"
            else:
                low_x = int(est_xss * 0.85)
                high_x = int(est_xss * 0.15)
                peak_x = 0
                f_dur = "Endurance / Base (>1h Focus)"

            item["title"] = f"📅 {w_title}"
            item["focus"] = w_focus
            item["duration_min"] = w_dur
            item["estimated_tss"] = w_tss
            item["estimated_xss"] = est_xss
            item["low_xss"] = low_x
            item["high_xss"] = high_x
            item["peak_xss"] = peak_x
            item["focus_duration"] = f_dur
            item["is_coach_scheduled"] = True
            item["scheduled_workout_id"] = scheduled_w.get("id")
            item["description"] = f"Coach-Scheduled: {w_desc} Calibrated for your {ftp}W FTP and synced to Zwift/Intervals.icu."

    # 3. RECOVERY PROTOCOL FOR TONIGHT
    sleep_target_hrs = round(max(7.5, sleep_needed), 1)
    carb_target_g = round(session_summary.get("moving_time_min", 0) * 0.9) if session_summary.get("moving_time_min", 0) > 0 else 0

    if active_plan and days_until_event is not None and days_until_event <= 2:
        sleep_target_hrs = max(8.5, sleep_target_hrs)
        recovery_protocol = {
            "sleep_target_hours": sleep_target_hrs,
            "sleep_target_text": f"Aim for {sleep_target_hrs} hours of restorative sleep to ensure you are well-rested before the event.",
            "nutrition_headline": "Pre-Event Fueling & Hydration",
            "nutrition_advice": f"High complex-carbohydrate intake (7–9g/kg carbs) to replenish glycogen stores before {active_plan.get('title')}.",
            "hydration_target": "Drink 750–1000 ml water with electrolytes throughout the evening to stay well-hydrated."
        }
    else:
        recovery_protocol = {
            "sleep_target_hours": sleep_target_hrs,
            "sleep_target_text": f"Aim for {sleep_target_hrs} hours of restorative sleep tonight to support recovery.",
            "nutrition_headline": "Nutrition & Recovery",
            "nutrition_advice": f"Consume ~{max(40, carb_target_g)}g complex carbohydrates with 25–30g lean protein to refuel.",
            "hydration_target": "500–750 ml water with electrolytes before bed to support overnight recovery."
        }

    from app.services.strain_model_service import calculate_trailing_strain_systems
    strain_systems = calculate_trailing_strain_systems(ftp=ftp)

    return {
        "today_assessment": session_summary,
        "outlook_days": outlook_days,
        "recovery_protocol": recovery_protocol,
        "strain_systems": strain_systems,
        "macrocycle_context": {
            "goal_title": program.get("title", "Threshold & FTP Booster"),
            "phase": program.get("phase", "Build Phase"),
            "current_ftp": ftp,
            "target_ftp": program.get("target_ftp", ftp + 15),
            "weekly_tss_actual": acute_tss,
            "weekly_tss_target": program.get("weekly_tss_target", 360),
            "weekly_xss_actual": program.get("weekly_xss_actual", acute_tss),
            "weekly_xss_target": program.get("weekly_xss_target", program.get("weekly_tss_target", 360)),
            "phase_focus_duration": program.get("target_focus_duration", "Climber / Sweet Spot (45:00 Focus)")
        }
    }

def generate_ai_review_and_outlook(custom_prompt: str = "") -> Dict[str, Any]:
    """
    Main entry point: pulls live Whoop and Strava telemetry,
    checks if Gemini LLM is enabled (and uses it for deep qualitative insights),
    or uses our local sports-science model.
    """
    from app.routers.dashboard import get_dashboard_data
    dash = get_dashboard_data()
    
    whoop_data = dash.get("whoop", {})
    strava_stats = dash.get("strava", {}).get("weekly_stats", {})
    athlete = dash.get("athlete", {})
    program = dash.get("program", {})
    ftp = int(athlete.get("ftp", 250))
    max_hr = int(athlete.get("max_hr", 185))
    
    act_info = get_today_and_recent_activities()
    today_acts = act_info.get("today_activities", [])
    latest_act = act_info.get("latest_activity")
    
    today_iso = datetime.date.today().isoformat()
    if custom_prompt and custom_prompt.strip():
        set_setting("latest_debrief_athlete_note", custom_prompt.strip())
        set_setting("latest_debrief_athlete_note_date", today_iso)
    else:
        saved_date = get_setting("latest_debrief_athlete_note_date", "")
        if saved_date == today_iso:
            custom_prompt = get_setting("latest_debrief_athlete_note", "")
        else:
            custom_prompt = ""

    # 1. Generate local sports-science baseline
    base_review = build_daily_review_and_outlook_local(
        whoop_data=whoop_data,
        trailing_strava=strava_stats,
        today_acts=today_acts,
        latest_act=latest_act,
        program=program,
        ftp=ftp,
        max_hr=max_hr,
        custom_prompt=custom_prompt
    )
    base_review["athlete_note"] = custom_prompt
    
    # 2. Check if Gemini API key is configured
    gemini_key = get_setting("gemini_api_key", "").strip()
    if gemini_key:
        try:
            enhanced_assessment = call_gemini_coach_review(
                api_key=gemini_key,
                review_data=base_review,
                whoop_data=whoop_data,
                custom_prompt=custom_prompt
            )
            if enhanced_assessment and enhanced_assessment.get("insights"):
                clean_insights = str(enhanced_assessment.get("insights")).strip()
                # Ensure no JSON leakage
                if clean_insights.startswith("{") or clean_insights.startswith('"insights"'):
                    import re
                    m = re.search(r'"insights"\s*:\s*"((?:[^"\\]|\\.)*)', clean_insights, re.DOTALL)
                    if m and len(m.group(1).strip()) > 20:
                        clean_insights = m.group(1).replace(r'\"', '"').replace(r'\n', '\n').strip()
                    else:
                        clean_insights = ""
                if len(clean_insights) > 25:
                    base_review["today_assessment"]["assessment_text"] = clean_insights
                    base_review["today_assessment"]["ai_coach_insights"] = clean_insights
                if custom_prompt and "Athlete Note:" not in base_review["today_assessment"]["assessment_text"]:
                    base_review["today_assessment"]["assessment_text"] += f"\n\nAthlete Note: '{custom_prompt}' — accounted for in fatigue decay and forward outlook modeling."
            if enhanced_assessment.get("tomorrow_guidance"):
                clean_guidance = str(enhanced_assessment["tomorrow_guidance"]).strip()
                if len(clean_guidance) > 10 and not clean_guidance.startswith("{"):
                    orig_desc = base_review["outlook_days"][0]["description"]
                    if clean_guidance not in orig_desc:
                        base_review["outlook_days"][0]["description"] = f"{orig_desc} AI Guidance: {clean_guidance}"
        except Exception as e:
            print(f"Gemini API review call error: {e}")
            if custom_prompt and "Athlete Note:" not in base_review["today_assessment"]["assessment_text"]:
                base_review["today_assessment"]["assessment_text"] += f"\n\nAthlete Note: '{custom_prompt}' — accounted for in fatigue decay and forward outlook modeling."
    else:
        if custom_prompt and "Athlete Note:" not in base_review["today_assessment"]["assessment_text"]:
            base_review["today_assessment"]["assessment_text"] += f"\n\nAthlete Note: '{custom_prompt}' — accounted for in fatigue decay and forward outlook modeling."

    return base_review

def call_gemini_coach_review(api_key: str, review_data: Dict[str, Any], whoop_data: Dict[str, Any], custom_prompt: str = "") -> Optional[Dict[str, str]]:
    """Invokes Google Gemini to generate natural-sounding qualitative coach feedback."""
    models_to_try = ["gemini-3-flash-preview", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]
    sess = review_data["today_assessment"]
    
    temporal_context = (
        f"Session was completed TODAY: '{sess.get('title')}' on today's {sess.get('workout_recovery')}% recovery baseline ({sess.get('workout_strain')} Whoop day strain)."
        if sess.get("is_today") else
        f"Session was completed YESTERDAY ({sess.get('date')}): '{sess.get('title')}' on yesterday's {sess.get('workout_recovery')}% recovery baseline ({sess.get('workout_strain')} Whoop day strain). "
        f"Note: TODAY's recovery is {sess.get('today_recovery')}% with {sess.get('today_strain')} daytime strain accumulated so far, as a direct consequence of yesterday's effort. Do NOT attribute today's {sess.get('today_strain')} strain to yesterday's ride."
    )

    from app.services.preferences_service import get_coaching_preferences
    prefs = get_coaching_preferences()
    directives_summary = "; ".join(prefs.get("directives", [
        "Mon/Tue/Thu: 35-45m only",
        "Wed/Fri: 60+ min (outdoors if weather allows)",
        "Sat: dedicated rest day",
        "Sun: 60-90+ min endurance"
    ]))
    
    prompt = (
        f"You are PowerSync's elite cycling sports-science coach. Provide a concise, qualitative debrief for the athlete.\n"
        f"Athlete FTP: {review_data['macrocycle_context']['current_ftp']}W.\n"
        f"Athlete Permanent Schedule & Workout Preferences: {directives_summary}\n"
        f"Timeline & Data: {temporal_context}\n"
        f"Session Metrics: {sess.get('moving_time_formatted')}, {sess.get('weighted_watts')}W ({sess.get('pct_ftp')}% FTP), {sess.get('suffer_score')} TSS.\n"
        f"Physiological Strain Breakdown: {sess.get('total_xss', 0)} Total XSS ({sess.get('low_strain_xss', 0)} Low / {sess.get('high_strain_xss', 0)} High / {sess.get('peak_strain_xss', 0)} Peak), W' Anaerobic Battery Depleted: {sess.get('battery_depleted_pct', 0)}%, Focus Duration: {sess.get('focus_duration', 'Endurance')}.\n"
        f"Target Zone was: {sess.get('target_zone')}. Compliance verdict: {sess.get('verdict')}.\n"
        f"Tomorrow outlook: {review_data['outlook_days'][0]['title']} (est. {review_data['outlook_days'][0].get('estimated_xss', 50)} XSS, Focus: {review_data['outlook_days'][0].get('focus_duration', 'Sweet Spot')}, {review_data['outlook_days'][0]['focus']}).\n"
        f"Mandatory: All advice and tomorrow guidance MUST strictly respect the athlete's workout and schedule preferences.\n"
        f"Format response as strict JSON: {{\"insights\": \"1-2 paragraphs assessing session against recovery and explaining fatigue state, under 150 words\", \"tomorrow_guidance\": \"short 1-2 sentence guidance for tomorrow, under 40 words\"}}"
    )
    if custom_prompt:
        prompt += f"\nAthlete note: '{custom_prompt}'"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json"
        }
    }

    import re
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
                text_parts = [p.get("text", "") for p in parts if "text" in p and p.get("text") and not p.get("thought")]
                raw_text = "\n".join(text_parts).strip()
                clean = raw_text.strip().replace("```json", "").replace("```", "").strip()
                # 1. Try standard JSON parse
                try:
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and parsed.get("insights") and len(str(parsed["insights"]).strip()) > 20:
                        return {
                            "insights": str(parsed["insights"]).strip(),
                            "tomorrow_guidance": str(parsed.get("tomorrow_guidance", "")).strip()
                        }
                except Exception:
                    pass

                # 2. Try regex extraction if JSON was unclosed or had trailing issues
                m_insights = re.search(r'"insights"\s*:\s*"((?:[^"\\]|\\.)*)', clean, re.DOTALL)
                m_guidance = re.search(r'"tomorrow_guidance"\s*:\s*"((?:[^"\\]|\\.)*)', clean, re.DOTALL)
                if m_insights:
                    insights_txt = m_insights.group(1).replace(r'\"', '"').replace(r'\n', '\n').strip()
                    if len(insights_txt) > 20:
                        guidance_txt = m_guidance.group(1).replace(r'\"', '"').replace(r'\n', '\n').strip() if m_guidance else ""
                        return {
                            "insights": insights_txt,
                            "tomorrow_guidance": guidance_txt
                        }

                # 3. If plain text without JSON markers
                if clean and not clean.startswith("{") and not clean.startswith("[") and '"insights"' not in clean and len(clean) > 25:
                    return {"insights": clean, "tomorrow_guidance": ""}
        except Exception as e:
            print(f"Gemini review error with {model}: {e}")

    return None

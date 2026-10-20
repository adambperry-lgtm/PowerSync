import json
import requests
import datetime
from typing import Dict, Any, List, Optional
from app.services.zwift_service import generate_zwo_xml, generate_intervals_icu_text
from app.database import get_active_target_plan, get_current_user_id
from app.services.workout_catalog import select_diverse_archetype

def enrich_workout_strain(workout: Dict[str, Any], ftp: int = 250) -> Dict[str, Any]:
    """
    Enriches a workout dictionary with 3-tier physiological strain metrics:
    Low XSS, High XSS, Peak XSS, Total XSS, Focus Duration, and W'bal battery depletion.
    """
    if not workout:
        return workout
    intervals = workout.get("intervals", [])
    if intervals:
        from app.services.strain_model_service import calculate_intervals_strain
        strain_res = calculate_intervals_strain(intervals, ftp=ftp)
        workout["strain_data"] = strain_res
        workout["low_xss"] = strain_res.get("low_xss", 0.0)
        workout["high_xss"] = strain_res.get("high_xss", 0.0)
        workout["peak_xss"] = strain_res.get("peak_xss", 0.0)
        workout["total_xss"] = strain_res.get("total_xss", 0.0)
        workout["focus_duration"] = strain_res.get("focus_duration", "Endurance / Century (>1h Focus)")
        workout["min_w_bal_pct"] = strain_res.get("min_w_bal_pct", 100.0)
        workout["battery_depleted_pct"] = strain_res.get("battery_depleted_pct", 0.0)
    else:
        workout["strain_data"] = {
            "low_xss": 0.0,
            "high_xss": 0.0,
            "peak_xss": 0.0,
            "total_xss": 0.0,
            "focus_duration": "Rest / Recovery",
            "min_w_bal_pct": 100.0,
            "battery_depleted_pct": 0.0,
            "w_bal_curve": []
        }
        workout["low_xss"] = 0.0
        workout["high_xss"] = 0.0
        workout["peak_xss"] = 0.0
        workout["total_xss"] = 0.0
        workout["focus_duration"] = "Rest / Recovery"
        workout["min_w_bal_pct"] = 100.0
        workout["battery_depleted_pct"] = 0.0
    return workout

def build_adaptive_workout_local(
    recovery_score: int,
    hrv_rmssd: float,
    sleep_score: int,
    recent_volume_hours: float,
    recent_high_intensity: bool,
    target_duration_min: int = 60,
    ftp: int = 250,
    user_note: str = "",
    program_phase: str = "Build Phase",
    today_strain: float = 0.0,
    today_activities: Optional[List[Dict[str, Any]]] = None,
    trailing_7d_strain_avg: float = 0.0,
    trailing_7d_high_strain_count: int = 0,
    recent_weighted_strain: float = 0.0,
    yesterday_strain: float = 0.0,
    total_tss: int = 0,
    acute_weighted_tss: int = 0,
    yesterday_tss: int = 0,
    load_profile: str = "Evenly Distributed",
    strain_profile: str = "Evenly Distributed",
    target_plan: Optional[Dict[str, Any]] = None,
    target_date: Optional[datetime.date] = None
) -> Dict[str, Any]:
    duration = target_duration_min
    active_plan = target_plan if target_plan is not None else get_active_target_plan()
    days_until = active_plan.get("days_until") if active_plan else None
    
    # 3-Tier Strain Assessment (XSS Equivalent)
    from app.services.strain_model_service import calculate_trailing_strain_systems, calculate_intervals_strain
    strain_systems = calculate_trailing_strain_systems(ftp=ftp)
    acute_high_xss = strain_systems.get("acute_48h", {}).get("high_xss", 0.0)
    yesterday_high_xss = strain_systems.get("yesterday", {}).get("high_xss", 0.0)
    acute_peak_xss = strain_systems.get("acute_48h", {}).get("peak_xss", 0.0)
    has_glycolytic_surge = (acute_high_xss >= 30.0 or yesterday_high_xss >= 20.0)

    # 0. Parse explicit duration or intent from user_note if provided
    import re
    note_clean = (user_note or "").strip().lower()
    wants_rest_note = bool(note_clean and any(k in note_clean for k in [
        "rest day", "take today off", "full rest", "skip today", "no ride", "day off"
    ]) and not any(k in note_clean for k in ["active", "spin", "flush"]))

    if note_clean and not wants_rest_note:
        dur_min_match = re.search(r'\b(\d{2,3})\s*(?:m|min|mins|minute|minutes)\b', note_clean)
        dur_hr_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b', note_clean)
        if dur_min_match:
            parsed_d = int(dur_min_match.group(1))
            if 15 <= parsed_d <= 240:
                duration = parsed_d
        elif dur_hr_match:
            parsed_d = round(float(dur_hr_match.group(1)) * 60)
            if 15 <= parsed_d <= 240:
                duration = parsed_d

    # 0A. Check if today is a scheduled weekly rest day per athlete preferences
    from app.services.preferences_service import get_day_target_config
    day_cfg = get_day_target_config(target_date)
    is_dir_rest = day_cfg.get("is_directive_rest", False)
    is_default_rest = day_cfg.get("is_default_rest", False)
    has_explicit_override = bool(note_clean and not wants_rest_note)

    if has_explicit_override and duration <= 0:
        pref_d = day_cfg.get("preferred_duration_min", 45)
        duration = pref_d if pref_d > 0 else 45

    is_scheduled_rest_day = wants_rest_note or ((is_default_rest or is_dir_rest or duration == 0) and not has_explicit_override)
    
    if is_scheduled_rest_day:
        title = "Rest Day or Easy Spin" if is_dir_rest and not wants_rest_note else "Rest & Recovery"
        focus_area = "Rest & Recovery"
        badge_text = "✨ Adapted Rest Day" if wants_rest_note else ("📋 Schedule Directive" if is_dir_rest else "🛋️ Scheduled Rest Day")
        ai_rationale = (
            f"Adapted to your instruction ('{user_note}'): Today is set as a full passive rest day to prioritize autonomic recovery ({recovery_score}% Whoop recovery) and glycogen restoration."
            if wants_rest_note else (
                f"Expected Recovery: ~{recovery_score}% (Supercompensation). Per your forward directive, {day_cfg.get('day_name', 'today')} is recommended as a full rest day or gentle active recovery spin (<55% FTP, <{int(ftp * 0.55)}W, ~15 Low XSS) to allow cellular supercompensation before Friday's ride."
                if is_dir_rest else
                (day_cfg.get("notes") or f"Per your coaching schedule preferences, {day_cfg.get('day_name', 'today')} is designated as your dedicated rest day. Your Whoop recovery is {recovery_score}%. Focus on hydration, mobility, and restorative sleep before your upcoming sessions.")
            )
        )
        workout_obj = {
            "id": "workout_primary",
            "option_type": "rest",
            "badge": badge_text,
            "badge_color": "emerald",
            "title": title,
            "description": f"Scheduled rest day for {day_cfg.get('day_name', 'today')}",
            "focus_area": focus_area,
            "duration_minutes": 0,
            "estimated_tss": 0,
            "ai_rationale": ai_rationale,
            "intervals": []
        }
        workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
        workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
        return enrich_workout_strain(workout_obj, ftp)

    # 0B. Check if athlete already trained today or reached target daily strain
    cur_eval_date = target_date or datetime.date.today()
    is_eval_today = (cur_eval_date == datetime.date.today())
    today_acts = today_activities or []
    today_moving_min = sum(a.get("moving_time_sec", 0) for a in today_acts) // 60
    has_substantial_ride = today_moving_min >= 30 or len(today_acts) > 0
    high_strain_reached = today_strain >= 13.5 or (today_strain >= 11.5 and recovery_score <= 55)
    
    if is_eval_today and (has_substantial_ride or high_strain_reached) and not has_explicit_override:
        act_name = today_acts[0].get("name", "training session") if today_acts else "an intense session"
        dur_note = f" ({today_moving_min}m)" if today_moving_min > 0 else ""
        title = "Daily Target Achieved — Rest & Recovery"
        focus_area = "Active Recovery & Restoration"
        trailing_note = f" (trailing 7D strain avg: {trailing_7d_strain_avg:.1f})" if trailing_7d_strain_avg > 0 else ""
        ai_rationale = (
            f"You've already completed '{act_name}'{dur_note} today with a current Whoop day strain of {today_strain:.1f}{trailing_note}. "
            f"Given your {recovery_score}% recovery score, your body has absorbed its optimal training stimulus for today. "
            f"Further high-intensity riding would cause non-functional overreaching and impair tomorrow's adaptation. "
            f"Recommended action: Rest, hydrate, or do a gentle 20-minute active recovery spin to flush the legs."
        )
        intervals = [
            {"type": "Warmup", "duration_sec": 300, "power_low_pct": 35, "power_high_pct": 45, "cadence": 85, "name": "Gentle Spin"},
            {"type": "SteadyState", "duration_sec": 600, "power_pct": 48, "cadence": 88, "name": "Zone 1 Active Flush"},
            {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 45, "power_high_pct": 35, "cadence": 80, "name": "Easy Spin Out"}
        ]
        duration = 20
        estimated_tss = 8
        workout_obj = {
            "id": "workout_primary",
            "option_type": "recovery",
            "badge": f"✅ {today_strain:.1f} Strain Met",
            "badge_color": "emerald",
            "title": title,
            "description": f"Daily target met with {today_strain:.1f} Whoop strain. Recommended active recovery.",
            "focus_area": focus_area,
            "duration_minutes": duration,
            "estimated_tss": estimated_tss,
            "ai_rationale": ai_rationale,
            "intervals": intervals
        }
        workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
        workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
        return enrich_workout_strain(workout_obj, ftp)

    # 0C. Explicit User Note Workout Adaptation (when athlete enters a training instruction)
    if note_clean:
        from app.services.zwift_service import reconcile_workout_intervals
        w_sec = 360 if duration <= 40 else 420
        c_sec = 240 if duration <= 40 else 300
        custom_matched = True

        if any(k in note_clean for k in ["recovery", "easy", "flush", "zone 1", "z1", "spin", "tired", "exhausted", "sore", "light", "gentle"]):
            title = f"{duration}-Min Active Recovery & Flush"
            focus_area = "Active Recovery"
            estimated_tss = max(8, int(duration * 0.38))
            ai_rationale = (
                f"Adapted to your instruction ('{user_note}'): Dialed into a gentle {duration}-minute Zone 1 active recovery spin (<55% FTP, ~{round(ftp * 0.50)}W) "
                f"calibrated for your {recovery_score}% Whoop recovery to promote blood flow and clear metabolic fatigue without autonomic strain."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 40, "power_high_pct": 52, "cadence": 86, "name": "Gentle Ramp Up"},
                {"type": "SteadyState", "duration_sec": max(300, (duration * 60) - 540), "power_pct": 52, "cadence": 90, "name": "Zone 1 Active Flush"},
                {"type": "Cooldown", "duration_sec": 240, "power_low_pct": 52, "power_high_pct": 38, "cadence": 82, "name": "Easy Spin Out"}
            ]
        elif any(k in note_clean for k in ["sweet spot", "sweetspot", "sst", "sub-threshold", "subthreshold"]):
            uid = get_current_user_id()
            plan_note = f"T-{days_until} Event Prep" if (active_plan and days_until is not None) else None
            selected = select_diverse_archetype("sweet_spot", duration, ftp=ftp, plan_ctx=plan_note, user_id=uid)
            title = selected["title"]
            focus_area = selected["focus_area"]
            estimated_tss = selected["estimated_tss"]
            ai_rationale = (
                f"Adapted to your instruction ('{user_note}'): Configured {title} "
                f"({selected['ai_rationale']}) for high aerobic density with controlled autonomic cost ({recovery_score}% Whoop recovery)."
            )
            intervals = selected["intervals"]
        elif any(k in note_clean for k in ["over-under", "over under", "overunder", "threshold", "zone 4", "z4", "lactate", "ftp"]):
            uid = get_current_user_id()
            plan_note = f"T-{days_until} Event Prep" if (active_plan and days_until is not None) else None
            forced_id = "sst_over_under" if any(k in note_clean for k in ["over-under", "over under", "overunder"]) else None
            selected = select_diverse_archetype("sweet_spot", duration, ftp=ftp, plan_ctx=plan_note, user_id=uid, forced_archetype_id=forced_id)
            title = selected["title"]
            focus_area = selected["focus_area"]
            estimated_tss = selected["estimated_tss"]
            ai_rationale = (
                f"Adapted to your instruction ('{user_note}'): Built {title} "
                f"({selected['ai_rationale']}) to maximize lactate clearance and raise your threshold ceiling."
            )
            intervals = selected["intervals"]
        elif any(k in note_clean for k in ["vo2", "hiit", "microburst", "high intensity", "hard", "anaerobic", "sprint", "tabata", "zone 5", "z5", "intervals", "30/30", "40/20"]):
            if any(k in note_clean for k in ["microburst", "30/30", "40/20", "tabata", "sprint"]):
                title = f"{duration}-Min High-Cadence Microbursts"
                focus_area = "VO2 Max & Neuromuscular"
                estimated_tss = int(duration * 0.88)
                main_sec = max(480, (duration * 60) - w_sec - c_sec - 300)
                reps = max(6, main_sec // 60)
                ai_rationale = (
                    f"Adapted to your instruction ('{user_note}'): Prescribed {duration}-minute High-Cadence Microbursts "
                    f"(30s @ 120% FTP / {round(ftp * 1.20)}W, 30s @ 50% FTP) to drive peak oxygen uptake and fast-twitch recruitment."
                )
                intervals = [
                    {"type": "Warmup", "duration_sec": w_sec, "power_low_pct": 45, "power_high_pct": 78, "cadence": 90, "name": "Gradual Wattage Ramp"},
                    {"type": "Repeats", "repeat": reps, "on_duration_sec": 30, "off_duration_sec": 30, "on_power_pct": 120, "off_power_pct": 50, "cadence": 102, "cadence_rest": 85, "name": f"{reps}x 30/30s VO2 Microbursts"},
                    {"type": "SteadyState", "duration_sec": 300, "power_pct": 65, "cadence": 90, "name": "Aerobic Bridge"},
                    {"type": "Cooldown", "duration_sec": c_sec, "power_low_pct": 65, "power_high_pct": 40, "cadence": 82, "name": "Progressive Cooldown Ramp"}
                ]
            else:
                title = f"{duration}-Min VO2 Max Intervals"
                focus_area = "VO2 Max & High Aerobic"
                estimated_tss = int(duration * 0.90)
                main_sec = max(360, (duration * 60) - w_sec - c_sec)
                reps = max(2, main_sec // 360)
                ai_rationale = (
                    f"Adapted to your instruction ('{user_note}'): Prescribed {duration}-minute VO2 Max 3-minute intervals at 115% FTP ({round(ftp * 1.15)}W) "
                    f"to push maximal stroke volume and aerobic ceiling."
                )
                intervals = [
                    {"type": "Warmup", "duration_sec": w_sec, "power_low_pct": 45, "power_high_pct": 78, "cadence": 90, "name": "Gradual Wattage Ramp"},
                    {"type": "Repeats", "repeat": reps, "on_duration_sec": 180, "off_duration_sec": 180, "on_power_pct": 115, "off_power_pct": 50, "cadence": 98, "cadence_rest": 85, "name": f"{reps}x 3m VO2 Max Blocks (115% FTP)"},
                    {"type": "Cooldown", "duration_sec": c_sec, "power_low_pct": 65, "power_high_pct": 40, "cadence": 82, "name": "Progressive Cooldown Ramp"}
                ]
        elif any(k in note_clean for k in ["tempo", "zone 3", "z3", "muscular endurance", "cadence", "climbing", "climb"]):
            title = f"{duration}-Min Tempo Cadence Ladders"
            focus_area = "Tempo / Muscular Endurance"
            estimated_tss = int(duration * 0.70)
            val_sec = 180 if duration < 45 else 240
            work_sec = max(240, ((duration * 60) - w_sec - c_sec - val_sec) // 2)
            ai_rationale = (
                f"Adapted to your instruction ('{user_note}'): Built a {duration}-minute Zone 3 Tempo session (80–82% FTP, ~{round(ftp * 0.81)}W) "
                f"targeting muscular endurance and sustained torque."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": w_sec, "power_low_pct": 45, "power_high_pct": 72, "cadence": 88, "name": "Gradual Wattage Ramp"},
                {"type": "SteadyState", "duration_sec": work_sec, "power_pct": 80, "cadence": 92, "name": "Tempo Block 1"},
                {"type": "SteadyState", "duration_sec": val_sec, "power_pct": 55, "cadence": 85, "name": "Recovery Valley"},
                {"type": "SteadyState", "duration_sec": work_sec, "power_pct": 82, "cadence": 94, "name": "Tempo Block 2"},
                {"type": "Cooldown", "duration_sec": c_sec, "power_low_pct": 65, "power_high_pct": 40, "cadence": 82, "name": "Progressive Cooldown Ramp"}
            ]
        elif any(k in note_clean for k in ["zone 2", "z2", "endurance", "base", "aerobic", "steady", "foundation", "fat burn"]):
            title = f"{duration}-Min Zone 2 Aerobic Foundation"
            focus_area = "Zone 2 Aerobic Base"
            estimated_tss = int(duration * 0.58)
            ai_rationale = (
                f"Adapted to your instruction ('{user_note}'): Prescribed a {duration}-minute steady Zone 2 aerobic base session at 68% FTP ({round(ftp * 0.68)}W) "
                f"with progressive warmup and cooldown ramps to build mitochondrial density and fat oxidation."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": w_sec, "power_low_pct": 45, "power_high_pct": 68, "cadence": 88, "name": "Gradual Wattage Ramp"},
                {"type": "SteadyState", "duration_sec": max(300, (duration * 60) - w_sec - c_sec), "power_pct": 68, "cadence": 90, "name": "Zone 2 Endurance Base"},
                {"type": "Cooldown", "duration_sec": c_sec, "power_low_pct": 65, "power_high_pct": 40, "cadence": 82, "name": "Progressive Cooldown Ramp"}
            ]
        else:
            custom_matched = False

        if custom_matched:
            intervals = reconcile_workout_intervals(intervals, duration, ftp=ftp)
            workout_obj = {
                "id": "workout_primary",
                "option_type": "primary",
                "badge": "✨ Adapted to Your Note",
                "badge_color": "cyan",
                "title": title,
                "description": f"Adapted workout: {user_note}",
                "focus_area": focus_area,
                "duration_minutes": duration,
                "estimated_tss": estimated_tss,
                "ai_rationale": ai_rationale,
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
            return enrich_workout_strain(workout_obj, ftp)

    # 0D. TARGET PLAN ACTIVE ADAPTATION: T-0 (Event Day), T-1 (Primer), T-2 (Flush), T-3 (Taper Onset)
    if active_plan and days_until is not None and days_until >= 0 and not has_explicit_override:
        plan_title = active_plan.get("title", "Target Event")
        plan_dist = float(active_plan.get("distance_miles") or 50.0)
        plan_tss = int(active_plan.get("estimated_tss") or 160)
        plan_target_date = active_plan.get("target_date", "")

        if days_until == 0:
            # EVENT DAY TODAY!
            duration = min(180, int(active_plan.get("estimated_duration_min") or 180))
            title = f"Target Event: {plan_title}"
            focus_area = f"{plan_dist:.1f} Miles • Event Day Execution"
            estimated_tss = plan_tss
            ai_rationale = (
                f"Today is your scheduled target event: '{plan_title}' ({plan_dist:.1f} mi, est. {plan_tss} TSS). "
                f"Execution strategy: Maintain smooth aerobic economy in Zone 2 on flats (60–68% FTP) and cap climbs strictly below threshold (<85% FTP) to preserve muscle glycogen. "
                f"Fuel with 60–80g carbs/hr and maintain consistent electrolyte hydration."
            )
            w_sec = 600
            c_sec = 300
            main_sec = (duration * 60) - w_sec - c_sec
            intervals = [
                {"type": "Warmup", "duration_sec": w_sec, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Gradual Warmup"},
                {"type": "SteadyState", "duration_sec": main_sec, "power_pct": 68, "cadence": 90, "name": f"Event Pacing Simulation ({plan_dist:.1f} mi)"},
                {"type": "Cooldown", "duration_sec": c_sec, "power_low_pct": 60, "power_high_pct": 45, "cadence": 82, "name": "Cooldown Spin"}
            ]
            workout_obj = {
                "id": "workout_primary",
                "option_type": "event_day",
                "badge": "🏁 TARGET EVENT TODAY",
                "badge_color": "magenta",
                "title": title,
                "description": f"Target event execution for {plan_title}",
                "focus_area": focus_area,
                "duration_minutes": duration,
                "estimated_tss": estimated_tss,
                "ai_rationale": ai_rationale,
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
            return enrich_workout_strain(workout_obj, ftp)

        elif days_until == 1:
            # T-1 PRIMER (Day Before Event)
            duration = 30
            title = "Pre-Event Neuromuscular Primer"
            focus_area = "Neural Activation & Glycogen Sparing"
            estimated_tss = 22
            ai_rationale = (
                f"Target Event Horizon: Tomorrow is your scheduled '{plan_title}' ({plan_dist:.1f} mi, ~{plan_tss} TSS). "
                f"To guarantee green Whoop recovery and full glycogen stores tomorrow morning, today is strictly capped at a 30-minute primer. "
                f"Includes three 30-second cadence spin-ups (105% FTP, 102+ rpm) to open neuromuscular pathways and prime enzyme turnover without glycogen depletion."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": 480, "power_low_pct": 50, "power_high_pct": 65, "cadence": 90, "name": "Easy Spin Up"},
                {
                    "type": "Repeats",
                    "repeat": 3,
                    "on_duration_sec": 30,
                    "off_duration_sec": 90,
                    "on_power_pct": 105,
                    "off_power_pct": 50,
                    "cadence": 102,
                    "cadence_rest": 85,
                    "name": "3x 30s Neuromuscular Openers"
                },
                {"type": "SteadyState", "duration_sec": 600, "power_pct": 60, "cadence": 90, "name": "Aerobic Flush"},
                {"type": "Cooldown", "duration_sec": 360, "power_low_pct": 55, "power_high_pct": 40, "cadence": 80, "name": "Smooth Spin Out"}
            ]
            workout_obj = {
                "id": "workout_primary",
                "option_type": "primer",
                "badge": "⚡ T-1 Event Primer",
                "badge_color": "cyan",
                "title": title,
                "description": f"Pre-event neuromuscular primer for tomorrow's {plan_title}",
                "focus_area": focus_area,
                "duration_minutes": duration,
                "estimated_tss": estimated_tss,
                "ai_rationale": ai_rationale,
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
            return enrich_workout_strain(workout_obj, ftp)

        elif days_until == 2:
            # T-2 FLUSH (2 Days Before Event)
            duration = 35
            title = "Pre-Event Active Recovery Flush"
            focus_area = "Active Flush & Supercompensation"
            estimated_tss = 20
            ai_rationale = (
                f"Target Event Horizon: 2 days until '{plan_title}' ({plan_dist:.1f} mi on {plan_target_date}). "
                f"Entering peak taper window. Prescribed gentle Zone 1 active recovery (52–58% FTP) to clear metabolic waste, "
                f"stimulate circulation, and allow deep cellular glycogen supercompensation. Emphasize hydration and 8+ hours of sleep tonight."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 45, "power_high_pct": 55, "cadence": 85, "name": "Gentle Spin"},
                {"type": "SteadyState", "duration_sec": 1500, "power_pct": 54, "cadence": 88, "name": "Metabolic Flush"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 40, "cadence": 80, "name": "Easy Spin Out"}
            ]
            workout_obj = {
                "id": "workout_primary",
                "option_type": "recovery",
                "badge": "🌱 T-2 Taper Flush",
                "badge_color": "emerald",
                "title": title,
                "description": f"Taper active recovery flush 2 days before {plan_title}",
                "focus_area": focus_area,
                "duration_minutes": duration,
                "estimated_tss": estimated_tss,
                "ai_rationale": ai_rationale,
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
            return enrich_workout_strain(workout_obj, ftp)

        elif days_until == 3:
            # T-3 TAPER ONSET (3 Days Before Event)
            duration = 45
            title = "Taper Onset: Controlled Tempo Touch"
            focus_area = "Taper Onset & Muscular Tension"
            estimated_tss = 38
            ai_rationale = (
                f"Target Event Horizon: 3 days until '{plan_title}' ({plan_dist:.1f} mi). "
                f"Beginning pre-event taper. Training duration is scaled down to 45 minutes with 2x 6-minute controlled Zone 3 tempo blocks (80% FTP) "
                f"to maintain neuromuscular tension and blood plasma volume without digging into recovery reserves."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": 480, "power_low_pct": 50, "power_high_pct": 72, "cadence": 90, "name": "Warmup"},
                {"type": "SteadyState", "duration_sec": 360, "power_pct": 80, "cadence": 92, "name": "Tempo Block 1"},
                {"type": "SteadyState", "duration_sec": 240, "power_pct": 55, "cadence": 85, "name": "Recovery Valley"},
                {"type": "SteadyState", "duration_sec": 360, "power_pct": 80, "cadence": 92, "name": "Tempo Block 2"},
                {"type": "SteadyState", "duration_sec": 720, "power_pct": 65, "cadence": 90, "name": "Aerobic Bridge"},
                {"type": "Cooldown", "duration_sec": 540, "power_low_pct": 60, "power_high_pct": 45, "cadence": 85, "name": "Smooth Spin Out"}
            ]
            workout_obj = {
                "id": "workout_primary",
                "option_type": "taper_onset",
                "badge": "🎯 T-3 Taper Onset",
                "badge_color": "cyan",
                "title": title,
                "description": f"Pre-event taper onset 3 days before {plan_title}",
                "focus_area": focus_area,
                "duration_minutes": duration,
                "estimated_tss": estimated_tss,
                "ai_rationale": ai_rationale,
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
            return enrich_workout_strain(workout_obj, ftp)

    # 0E. FORECAST CONTINUITY INTEGRATION
    # Check if there is an active 3-day forward forecast stored for this date
    cur_date_iso = (target_date or datetime.date.today()).isoformat()
    uid = get_current_user_id()
    from app.services.forecast_service import get_forecast_for_date, is_forecast_valid_for_recovery
    forecast = get_forecast_for_date(cur_date_iso, user_id=uid)
    forecast_divergence_note = ""

    if forecast and not has_explicit_override:
        is_valid, validation_msg = is_forecast_valid_for_recovery(forecast, recovery_score)
        if is_valid:
            # The forecast assumptions hold true! Select the promised workout archetype and structure.
            f_title = forecast.get("title") or "Endurance Session"
            f_dur = int(forecast.get("duration_min") if forecast.get("duration_min") is not None else duration)
            f_focus = forecast.get("focus_area") or forecast.get("focus") or "Structured Training"
            f_tss = int(forecast.get("estimated_tss") or int(f_dur * 0.75))
            f_intervals = list(forecast.get("intervals") or [])
            f_rationale = forecast.get("ai_rationale") or forecast.get("description") or ""

            # Check if forecast prescribed rest or active recovery
            if f_dur == 0 or forecast.get("is_directive_rest") or forecast.get("is_default_rest"):
                workout_obj = {
                    "id": "workout_primary",
                    "option_type": "rest",
                    "badge": "⭐ Coach's Choice • Forecast Confirmed",
                    "badge_color": "emerald",
                    "title": f_title,
                    "description": f"Forecast Confirmed for Whoop Recovery {recovery_score}%",
                    "focus_area": f_focus,
                    "duration_minutes": 0,
                    "estimated_tss": 0,
                    "ai_rationale": (
                        f"Forecast Confirmed: Projected recovery was ~{forecast.get('projected_recovery', recovery_score)}%, "
                        f"and actual Whoop recovery is {recovery_score}% ({validation_msg}). "
                        f"Per your confirmed forecast: {f_rationale}"
                    ),
                    "intervals": []
                }
                workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
                workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
                return enrich_workout_strain(workout_obj, ftp)

            proj_rec = forecast.get("projected_recovery", recovery_score)
            p_zone = forecast.get("projected_zone", "green")
            badge_color = "emerald" if p_zone == "green" else ("amber" if p_zone == "yellow" else "rose")

            continuity_desc = (
                f"Forecast Confirmed: Projected recovery was ~{proj_rec}%, and actual Whoop recovery is {recovery_score}% ({validation_msg}). "
                f"Executing the planned session from your forward forecast: {f_rationale}"
            )

            workout_obj = {
                "id": "workout_primary",
                "option_type": "primary",
                "badge": "⭐ Coach's Choice • Forecast Confirmed",
                "badge_color": badge_color,
                "title": f_title,
                "description": f"Forecast Confirmed for Whoop Recovery {recovery_score}%",
                "focus_area": f_focus,
                "duration_minutes": f_dur,
                "estimated_tss": f_tss,
                "ai_rationale": continuity_desc,
                "intervals": f_intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
            return enrich_workout_strain(workout_obj, ftp)
        else:
            # Assumptions diverged (e.g. forecast anticipated Green 75% but athlete woke up Red 28%)
            forecast_divergence_note = (
                f"⚡ Forecast Adapted: Morning Whoop recovery ({recovery_score}%) diverged from projected "
                f"{forecast.get('projected_recovery')}% ({validation_msg}). "
                f"Pivoting today's session from forecasted '{forecast.get('title')}' to align with your actual physiological readiness. "
            )

    # 1. Whoop Red Zone (< 34%)
    if recovery_score < 34:
        title = "Zone 1 Active Flush & Restoration"
        focus_area = "Active Recovery"
        strain_ctx = f", weighted strain {recent_weighted_strain:.1f}" if recent_weighted_strain > 0 else ""
        ai_rationale = (
            f"Your Whoop recovery is in the red ({recovery_score}%) with {sleep_score}% sleep performance{strain_ctx}. "
            f"Combined with {recent_volume_hours:.1f} hours logged on Strava, accumulated autonomic and systemic fatigue suggests active recovery over high power. "
            f"Power is strictly capped in Zone 1 (<55% FTP) to clear metabolic waste without cardiovascular strain."
        )
        intervals = [
            {"type": "Warmup", "duration_sec": 300, "power_low_pct": 40, "power_high_pct": 50, "cadence": 85, "name": "Gentle Spin"},
            {"type": "SteadyState", "duration_sec": (duration - 10) * 60, "power_pct": 52, "cadence": 90, "name": "Zone 1 Flush"},
            {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 38, "cadence": 80, "name": "Easy Spin Out"}
        ]
        estimated_tss = int(duration * 0.35)

    # 2. Whoop Yellow Zone (34% - 66%)
    elif recovery_score <= 66:
        effective_strain = recent_weighted_strain if recent_weighted_strain > 0 else trailing_7d_strain_avg
        effective_tss = acute_weighted_tss if acute_weighted_tss > 0 else total_tss

        # Recency-weighted fatigue triggers:
        # A) Recent Fatigue Surge (e.g. yesterday 200 TSS or >= 14.2 strain)
        is_recent_fatigue_surge = (
            yesterday_tss >= 80 or
            yesterday_strain >= 14.2 or
            (acute_weighted_tss >= 340 and yesterday_tss >= 50) or
            (effective_strain >= 12.0 and yesterday_strain >= 13.0) or
            load_profile == "Recent Surge (Yesterday Heavy)"
        )

        # B) Front-Loaded Supercompensated (e.g. 200 TSS was 7 days ago, yesterday was 0-30 TSS / rest)
        is_front_loaded_fresh = (
            yesterday_tss < 35 and
            yesterday_strain < 8.5 and
            (total_tss >= 160 or recent_volume_hours >= 4.0) and
            (load_profile == "Front-Loaded (Supercompensated/Fresh)" or (total_tss > 0 and acute_weighted_tss <= total_tss * 0.90))
        )

        # C) Cumulative Volume Load
        is_high_strain_load = (
            is_recent_fatigue_surge or
            (not is_front_loaded_fresh and (
                recent_volume_hours > 7.0 or
                effective_tss >= 350 or
                effective_strain >= 11.5 or
                trailing_7d_high_strain_count >= 3 or
                (recent_volume_hours >= 5.5 and effective_strain >= 10.0)
            ))
        )

        if is_recent_fatigue_surge:
            title = "Zone 2 Steady Aerobic Maintenance"
            focus_area = "Aerobic Base / Active Recovery"
            ai_rationale = (
                f"Whoop recovery is moderate at {recovery_score}%. While your 7-day load totals {recent_volume_hours:.1f} hrs ({total_tss} TSS), "
                f"your fatigue is acutely concentrated in the last 24 hours (yesterday logged {yesterday_tss} TSS and {yesterday_strain:.1f} Whoop strain, "
                f"producing an acute weighted load of {effective_tss} TSS). Because acute muscular damage and glycogen depletion take 3–5 days to clear, "
                f"a simple weekly average would miss this recency spike. Today's goal is steady Zone 2 endurance (65% FTP)—building mitochondrial "
                f"density and clearing metabolic fatigue without sympathetic burnout."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": 480, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Gradual Warmup"},
                {"type": "SteadyState", "duration_sec": (duration - 13) * 60, "power_pct": 65, "cadence": 90, "name": "Z2 Endurance Base"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 45, "cadence": 85, "name": "Cooldown"}
            ]
            estimated_tss = int(duration * 0.55)

        elif is_front_loaded_fresh:
            uid = get_current_user_id()
            plan_note = f"T-{days_until} Event Prep" if (active_plan and days_until is not None) else None
            selected = select_diverse_archetype("tempo", duration, ftp=ftp, plan_ctx=plan_note, user_id=uid)
            title = selected["title"]
            focus_area = selected["focus_area"]
            ai_rationale = (
                f"Whoop recovery is stable at {recovery_score}%. While your 7-day volume totals {recent_volume_hours:.1f} hrs ({total_tss} TSS), "
                f"your heavy training was front-loaded earlier in the cycle. With yesterday being an easy recovery day ({yesterday_strain:.1f} strain, {yesterday_tss} TSS), "
                f"acute residual fatigue has decayed (acute weighted load: {effective_tss} TSS). Your body has supercompensated, "
                f"giving you the physiological green light for {title}: {selected['ai_rationale']}"
            )
            intervals = selected["intervals"]
            estimated_tss = selected["estimated_tss"]

        elif is_high_strain_load:
            title = "Zone 2 Steady Aerobic Maintenance"
            focus_area = "Aerobic Base"
            load_context = []
            if recent_volume_hours > 0:
                load_context.append(f"{recent_volume_hours:.1f} hrs on Strava")
            if effective_strain > 0:
                peak_str = f" with {trailing_7d_high_strain_count} peak days ≥14.0" if trailing_7d_high_strain_count > 0 else ""
                load_context.append(f"recency-weighted Whoop strain of {effective_strain:.1f}{peak_str}")
            load_str = " and a ".join(load_context) if load_context else "accumulated volume"
            ai_rationale = (
                f"Whoop recovery is moderate at {recovery_score}%. Factoring in {load_str}, "
                f"your physiology reflects accumulated systemic and mechanical load. "
                f"Today's goal is steady Zone 2 endurance (65% FTP)—building mitochondrial density and capillary beds without autonomic overreach."
            )
            intervals = [
                {"type": "Warmup", "duration_sec": 480, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Gradual Warmup"},
                {"type": "SteadyState", "duration_sec": (duration - 13) * 60, "power_pct": 66, "cadence": 90, "name": "Z2 Endurance Base"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 45, "cadence": 85, "name": "Cooldown"}
            ]
            estimated_tss = int(duration * 0.55)

        else:
            uid = get_current_user_id()
            plan_note = f"T-{days_until} Event Prep" if (active_plan and days_until is not None) else None
            selected = select_diverse_archetype("tempo", duration, ftp=ftp, plan_ctx=plan_ctx if 'plan_ctx' in locals() else plan_note, user_id=uid)
            title = selected["title"]
            focus_area = selected["focus_area"]
            strain_desc = f", weighted strain {effective_strain:.1f}" if effective_strain > 0 else ""
            ai_rationale = (
                f"Whoop recovery is stable ({recovery_score}%) with moderate training fatigue ({recent_volume_hours:.1f} hrs{strain_desc}). "
                f"Prescribed {title}: {selected['ai_rationale']}"
            )
            intervals = selected["intervals"]
            estimated_tss = selected["estimated_tss"]

    # 3. Whoop Green Zone (> 66%) - Primed for adaptation!
    else:
        # Even with Green recovery, check if yesterday was a heavy training spike or high glycolytic drain
        is_yesterday_surge = yesterday_tss >= 90 or yesterday_strain >= 15.0 or load_profile == "Recent Surge (Yesterday Heavy)" or has_glycolytic_surge
        chronic_heavy_strain = (trailing_7d_strain_avg >= 14.0 or trailing_7d_high_strain_count >= 4 or recent_weighted_strain >= 14.0)

        # Standard warmup & cooldown progressive wattage ramps
        warmup_sec = 360 if duration <= 40 else 420
        cooldown_sec = 240 if duration <= 40 else 300

        if is_yesterday_surge or chronic_heavy_strain or recent_high_intensity:
            uid = get_current_user_id()
            plan_note = f"T-{days_until} Event Prep" if (active_plan and days_until is not None) else None
            selected = select_diverse_archetype("sweet_spot", duration, ftp=ftp, plan_ctx=plan_note, user_id=uid)
            title = selected["title"]
            focus_area = selected["focus_area"]
            if is_yesterday_surge:
                glycolytic_note = f" Additionally, your anaerobic battery incurred heavy glycolytic strain ({acute_high_xss:.1f} High XSS) in the last 48 hours." if has_glycolytic_surge else ""
                ai_rationale = (
                    f"Strong morning recovery ({recovery_score}%, HRV {hrv_rmssd:.0f} ms), but yesterday was an intense session ({yesterday_tss} TSS, {yesterday_strain:.1f} Whoop strain).{glycolytic_note} "
                    f"Because acute peripheral fatigue takes time to clear, today is dialed into {title}. {selected['ai_rationale']}"
                )
            elif chronic_heavy_strain:
                ai_rationale = (
                    f"Strong morning recovery ({recovery_score}%, HRV {hrv_rmssd:.0f} ms), but your recency-weighted Whoop strain is elevated at {recent_weighted_strain:.1f} ({trailing_7d_high_strain_count} peak days ≥14.0). "
                    f"To balance high acute readiness against chronic systemic strain, today features {title} for maximum aerobic density without sympathetic burnout. {selected['ai_rationale']}"
                )
            else:
                strain_note = f" (weighted strain: {recent_weighted_strain:.1f})" if recent_weighted_strain > 0 else ""
                ai_rationale = (
                    f"You're in the green at {recovery_score}% recovery with strong HRV ({hrv_rmssd:.0f} ms){strain_note}. "
                    f"Today's session ({title}) provides the optimal metabolic stimulus with manageable autonomic fatigue. {selected['ai_rationale']}"
                )
            intervals = selected["intervals"]
            estimated_tss = selected["estimated_tss"]
        else:
            uid = get_current_user_id()
            plan_note = f"T-{days_until} Event Prep" if (active_plan and days_until is not None) else None
            selected = select_diverse_archetype("vo2_max", duration, ftp=ftp, plan_ctx=plan_note, user_id=uid)
            title = selected["title"]
            focus_area = selected["focus_area"]
            strain_note = f" with well-managed acute load ({recent_weighted_strain:.1f} weighted strain)" if recent_weighted_strain > 0 else ""
            ai_rationale = (
                f"Exceptional Whoop readiness today ({recovery_score}% Recovery, {sleep_score}% Sleep){strain_note}. "
                f"Low acute fatigue makes this the ideal window for high-intensity work. "
                f"Today's session ({title}) targets {selected['focus_area']}: {selected['ai_rationale']}"
            )
            intervals = selected["intervals"]
            estimated_tss = selected["estimated_tss"]

    badge_text = "⭐ Coach's Choice"
    badge_color = "cyan"
    if forecast_divergence_note:
        badge_text = "🔄 Adapted from Forecast"
        badge_color = "amber"
        ai_rationale = forecast_divergence_note + ai_rationale

    if active_plan and days_until is not None and days_until >= 4:
        badge_text = f"🎯 T-{days_until} Prep • Coach's Choice"
        ai_rationale = f"Target Event Horizon: '{active_plan.get('title')}' ({float(active_plan.get('distance_miles') or 50):.1f} mi) in {days_until} days. {ai_rationale}"

    if user_note and user_note.strip():
        badge_text = "✨ Adapted to Your Note"
        ai_rationale = f"Adapted to your instruction ('{user_note.strip()}'): {ai_rationale}"

    workout_obj = {
        "id": "workout_primary",
        "option_type": "primary",
        "badge": badge_text,
        "badge_color": badge_color,
        "title": title,
        "description": f"Adaptive AI Workout for Whoop Recovery {recovery_score}%",
        "focus_area": focus_area,
        "duration_minutes": duration,
        "estimated_tss": estimated_tss,
        "ai_rationale": ai_rationale,
        "intervals": intervals
    }
    workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
    workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
    return enrich_workout_strain(workout_obj, ftp)

def build_alternative_endurance_workout(
    recovery_score: int,
    duration_min: int = 60,
    ftp: int = 250,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Generates an aerobic base / lower-strain alternative using the dynamic archetype catalog."""
    uid = user_id or get_current_user_id()
    dur = duration_min
    selected = select_diverse_archetype("endurance_base", dur, ftp=ftp, user_id=uid)
    workout = {
        "id": "workout_alt_base",
        "option_type": "endurance",
        "badge": "🚴 Low-Strain Base",
        "badge_color": "emerald",
        "title": selected["title"],
        "description": "Aerobic base alternative session",
        "focus_area": selected["focus_area"],
        "duration_minutes": dur,
        "estimated_tss": selected["estimated_tss"],
        "ai_rationale": (
            f"Alternative Option: If you want a lower cardiac cost today, this {selected['title']} "
            f"builds capillary density and fat oxidation without digging into your recovery reserves."
        ),
        "intervals": selected["intervals"]
    }
    workout["zwo_content"] = generate_zwo_xml(workout, ftp)
    workout["intervals_icu_text"] = generate_intervals_icu_text(workout)
    return enrich_workout_strain(workout, ftp)

def build_alternative_express_workout(
    recovery_score: int,
    ftp: int = 250,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Generates a time-crunched 35-min high-efficiency session using the dynamic archetype catalog."""
    uid = user_id or get_current_user_id()
    dur = 35
    selected = select_diverse_archetype("express", dur, ftp=ftp, user_id=uid)
    workout = {
        "id": "workout_alt_express",
        "option_type": "express",
        "badge": "⏱️ Time-Crunched (35m)",
        "badge_color": "amber",
        "title": selected["title"],
        "description": "Time-crunched alternative session",
        "focus_area": selected["focus_area"],
        "duration_minutes": dur,
        "estimated_tss": selected["estimated_tss"],
        "ai_rationale": f"Alternative Option: Short on time? {selected['ai_rationale']}",
        "intervals": selected["intervals"]
    }
    workout["zwo_content"] = generate_zwo_xml(workout, ftp)
    workout["intervals_icu_text"] = generate_intervals_icu_text(workout)
    return enrich_workout_strain(workout, ftp)

def build_workout_bundle(
    recovery_score: int,
    hrv_rmssd: float,
    sleep_score: int,
    recent_volume_hours: float,
    recent_high_intensity: bool,
    target_duration_min: int = 60,
    ftp: int = 250,
    user_note: str = "",
    program_phase: str = "Build Phase",
    today_strain: float = 0.0,
    today_activities: Optional[List[Dict[str, Any]]] = None,
    trailing_7d_strain_avg: float = 0.0,
    trailing_7d_high_strain_count: int = 0,
    recent_weighted_strain: float = 0.0,
    yesterday_strain: float = 0.0,
    total_tss: int = 0,
    acute_weighted_tss: int = 0,
    yesterday_tss: int = 0,
    load_profile: str = "Evenly Distributed",
    strain_profile: str = "Evenly Distributed",
    target_date: Optional[datetime.date] = None
) -> Dict[str, Any]:
    """Generates the primary prescribed workout and 2 tailored alternatives."""
    cur_eval_date = target_date or datetime.date.today()
    is_eval_today = (cur_eval_date == datetime.date.today())
    today_acts = today_activities or []
    today_moving_min = sum(a.get("moving_time_sec", 0) for a in today_acts) // 60
    has_substantial_ride = today_moving_min >= 30 or len(today_acts) > 0
    high_strain_reached = today_strain >= 13.5 or (today_strain >= 11.5 and recovery_score <= 55)

    primary = build_adaptive_workout_local(
        recovery_score=recovery_score,
        hrv_rmssd=hrv_rmssd,
        sleep_score=sleep_score,
        recent_volume_hours=recent_volume_hours,
        recent_high_intensity=recent_high_intensity,
        target_duration_min=target_duration_min,
        ftp=ftp,
        user_note=user_note,
        program_phase=program_phase,
        today_strain=today_strain,
        today_activities=today_activities,
        trailing_7d_strain_avg=trailing_7d_strain_avg,
        trailing_7d_high_strain_count=trailing_7d_high_strain_count,
        recent_weighted_strain=recent_weighted_strain,
        yesterday_strain=yesterday_strain,
        total_tss=total_tss,
        acute_weighted_tss=acute_weighted_tss,
        yesterday_tss=yesterday_tss,
        load_profile=load_profile,
        strain_profile=strain_profile,
        target_date=target_date
    )

    if primary.get("option_type") == "rest" or primary.get("duration_minutes") == 0:
        alt_flush = {
            "id": "workout_alt_flush",
            "option_type": "flush",
            "badge": "🌱 Gentle Leg Flush (20m)",
            "badge_color": "emerald",
            "title": "20-Min Active Recovery Flush",
            "description": "Very light recovery spin to keep muscles loose",
            "focus_area": "Active Flush",
            "duration_minutes": 20,
            "estimated_tss": 10,
            "ai_rationale": "Light 20-minute spin (50% FTP) to stimulate circulation and lymphatic clearance without placing metabolic strain on muscles.",
            "intervals": [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 40, "power_high_pct": 50, "cadence": 85, "name": "Gentle Spin"},
                {"type": "SteadyState", "duration_sec": 600, "power_pct": 50, "cadence": 88, "name": "Easy Flush"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 48, "power_high_pct": 38, "cadence": 80, "name": "Spin Out"}
            ]
        }
        alt_flush["zwo_content"] = generate_zwo_xml(alt_flush, ftp)
        alt_flush["intervals_icu_text"] = generate_intervals_icu_text(alt_flush)
        alt_flush = enrich_workout_strain(alt_flush, ftp)

        alt_base = build_alternative_endurance_workout(
            recovery_score=recovery_score,
            duration_min=45,
            ftp=ftp
        )
        alt_base["badge"] = "🚴 Optional Easy Base"
        alt_base["title"] = "Optional 45m Aerobic Endurance"
        alt_base["ai_rationale"] = "If you feel like riding on your scheduled rest day, keep it to a strict Zone 2 steady endurance cruise."
        alt_base["zwo_content"] = generate_zwo_xml(alt_base, ftp)
        alt_base["intervals_icu_text"] = generate_intervals_icu_text(alt_base)
        alt_base = enrich_workout_strain(alt_base, ftp)

        return {
            "primary": primary,
            "alternatives": [alt_flush, alt_base],
            "all_options": [primary, alt_flush, alt_base]
        }
    
    if is_eval_today and (has_substantial_ride or high_strain_reached) and not (user_note and user_note.strip()):
        alt_rest = {
            "id": "workout_alt_rest",
            "option_type": "rest",
            "badge": "🛋️ Full Passive Rest",
            "badge_color": "emerald",
            "title": "Complete Rest Day",
            "description": "Full recovery off the bike",
            "focus_area": "Passive Recovery",
            "duration_minutes": 0,
            "estimated_tss": 0,
            "ai_rationale": "Zero training load. Spend the rest of today relaxing with clean nutrition and early sleep to supercompensate from your completed session.",
            "intervals": []
        }
        alt_rest["zwo_content"] = generate_zwo_xml(alt_rest, ftp)
        alt_rest["intervals_icu_text"] = generate_intervals_icu_text(alt_rest)
        alt_rest = enrich_workout_strain(alt_rest, ftp)

        alt_override = build_alternative_endurance_workout(
            recovery_score=recovery_score,
            duration_min=max(30, target_duration_min or 45),
            ftp=ftp
        )
        alt_override["badge"] = "⚠️ Manual Override (Z2)"
        alt_override["badge_color"] = "amber"
        alt_override["title"] = "Manual Override: Zone 2 Endurance"
        alt_override["ai_rationale"] = f"Override Session: If you deliberately want a two-a-day training block despite {today_strain:.1f} strain today, cap intensity strictly at 65% FTP."
        alt_override["zwo_content"] = generate_zwo_xml(alt_override, ftp)
        alt_override["intervals_icu_text"] = generate_intervals_icu_text(alt_override)
        alt_override = enrich_workout_strain(alt_override, ftp)

        return {
            "primary": primary,
            "alternatives": [alt_rest, alt_override],
            "all_options": [primary, alt_rest, alt_override]
        }

    active_plan = get_active_target_plan()
    days_until = active_plan.get("days_until") if active_plan else None
    if active_plan and days_until is not None and days_until <= 1 and not (user_note and user_note.strip()):
        alt_rest = {
            "id": "workout_alt_rest",
            "option_type": "rest",
            "badge": "🛋️ Full Passive Rest",
            "badge_color": "emerald",
            "title": "Complete Pre-Event Rest Day",
            "description": "Full recovery off the bike",
            "focus_area": "Passive Recovery & Glycogen Storing",
            "duration_minutes": 0,
            "estimated_tss": 0,
            "ai_rationale": "Zero training load. Rest off the bike with carbo-loading and deep sleep to guarantee fresh legs on event day.",
            "intervals": []
        }
        alt_rest["zwo_content"] = generate_zwo_xml(alt_rest, ftp)
        alt_rest["intervals_icu_text"] = generate_intervals_icu_text(alt_rest)
        alt_rest = enrich_workout_strain(alt_rest, ftp)

        alt_flush = {
            "id": "workout_alt_flush",
            "option_type": "flush",
            "badge": "🌱 Gentle Leg Flush (20m)",
            "badge_color": "emerald",
            "title": "20-Min Easy Leg Flush",
            "description": "Very light spin to keep joints loose",
            "focus_area": "Active Flush",
            "duration_minutes": 20,
            "estimated_tss": 10,
            "ai_rationale": "Very light 20-minute spin (50% FTP) to maintain circulation and joint mobility without using muscle glycogen.",
            "intervals": [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 40, "power_high_pct": 50, "cadence": 85, "name": "Gentle Spin"},
                {"type": "SteadyState", "duration_sec": 600, "power_pct": 50, "cadence": 88, "name": "Easy Flush"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 48, "power_high_pct": 38, "cadence": 80, "name": "Spin Out"}
            ]
        }
        alt_flush["zwo_content"] = generate_zwo_xml(alt_flush, ftp)
        alt_flush["intervals_icu_text"] = generate_intervals_icu_text(alt_flush)
        alt_flush = enrich_workout_strain(alt_flush, ftp)

        return {
            "primary": primary,
            "alternatives": [alt_rest, alt_flush],
            "all_options": [primary, alt_rest, alt_flush]
        }

    alt_base = build_alternative_endurance_workout(
        recovery_score=recovery_score,
        duration_min=max(30, int(primary.get("duration_minutes") or target_duration_min or 45)),
        ftp=ftp
    )
    
    alt_express = build_alternative_express_workout(
        recovery_score=recovery_score,
        ftp=ftp
    )
    
    return {
        "primary": primary,
        "alternatives": [alt_base, alt_express],
        "all_options": [primary, alt_base, alt_express]
    }

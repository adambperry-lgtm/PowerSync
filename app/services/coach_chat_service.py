import os
import re
import json
import requests
import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.database import get_setting, set_setting, get_db_connection, get_active_target_plan

def extract_gemini_key_from_text(text: str) -> Optional[str]:
    """Detects if user provided a Google Gemini API key in their message."""
    match = re.search(r'\b(AIza[0-9A-Za-z-_]{35}|AQ\.[0-9A-Za-z-_]{35,70})\b', text)
    if match:
        return match.group(1)
    return None

def get_gemini_api_key() -> str:
    """Retrieves Gemini API key from database settings or environment variables."""
    key = get_setting("gemini_api_key", "").strip()
    if key and "•" not in key:
        return key
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    return ""

def compile_athlete_context() -> Dict[str, Any]:
    """
    Compiles a comprehensive sports-science snapshot of all athlete telemetry,
    including Whoop biometrics, Strava history, prescriptions, fueling, and goals.
    """
    from app.routers.dashboard import get_dashboard_data
    from app.routers.workouts import get_current_workout_cache, get_current_options_cache
    from app.services.review_coach import get_today_and_recent_activities

    dash = get_dashboard_data()
    athlete = dash.get("athlete", {})
    whoop = dash.get("whoop", {})
    strava = dash.get("strava", {})
    program = dash.get("program", {})

    ftp = int(athlete.get("ftp", 250))
    max_hr = int(athlete.get("max_hr", 185))
    w_prime_kj = float(athlete.get("w_prime_kj") or get_setting("athlete_w_prime_kj", 20.0))
    peak_power_watts = int(athlete.get("peak_power_watts") or get_setting("athlete_peak_power_watts", 1050))

    from app.services.strain_model_service import calculate_trailing_strain_systems
    strain_systems = calculate_trailing_strain_systems(ftp=ftp)

    # Activity timelines
    act_info = get_today_and_recent_activities()
    today_acts = act_info.get("today_activities", [])
    latest_act = act_info.get("latest_activity", {})

    # Power Zones (Coggan)
    power_zones = {
        "Z1_Recovery": f"< {round(ftp * 0.55)}W",
        "Z2_Endurance": f"{round(ftp * 0.56)}–{round(ftp * 0.75)}W",
        "Z3_Tempo": f"{round(ftp * 0.76)}–{round(ftp * 0.87)}W",
        "Sweet_Spot": f"{round(ftp * 0.88)}–{round(ftp * 0.93)}W",
        "Z4_Threshold": f"{round(ftp * 0.94)}–{round(ftp * 1.05)}W",
        "Z5_VO2Max": f"{round(ftp * 1.06)}–{round(ftp * 1.20)}W",
        "Z6_Anaerobic": f"> {round(ftp * 1.20)}W"
    }

    # Current Prescribed Workout
    workout_cache = get_current_workout_cache()
    options_cache = get_current_options_cache()
    active_workout = workout_cache or options_cache.get("workout_primary") or {}
    all_options = list(options_cache.values()) if options_cache else []

    # Active Target Plan (e.g. Gran Fondo, Race)
    target_plan = get_active_target_plan()

    # Trailing Strava stats
    weekly_stats = strava.get("weekly_stats", {})

    # Recent activities summary (last 5)
    recent_rides_summary = []
    for a in strava.get("recent_activities", strava.get("activities", []))[:5]:
        dist_mi = round(a.get("distance_meters", 0) / 1609.34, 1)
        dur_min = round(a.get("moving_time_sec", 0) / 60)
        recent_rides_summary.append({
            "name": a.get("name", "Ride"),
            "date": a.get("start_date", "")[:10],
            "distance_miles": dist_mi,
            "duration_min": dur_min,
            "avg_power_watts": a.get("average_watts", 0),
            "normalized_power_watts": a.get("weighted_average_watts", 0),
            "pct_ftp": round((a.get("weighted_average_watts", 0) / float(ftp)) * 100) if ftp > 0 else 0,
            "tss": round(a.get("suffer_score", 0)),
            "avg_hr": a.get("average_heartrate", 0),
            "max_hr": a.get("max_heartrate", 0)
        })

    sys_status = strain_systems.get("system_status", {})
    if isinstance(sys_status, dict):
        glyc_fatigued = sys_status.get("high_glycolytic") in ("FATIGUED", "FRESHENING") or strain_systems.get("glycolytic_fatigued", False)
        neuro_fatigued = sys_status.get("peak_neuromuscular") in ("FATIGUED", "FRESHENING") or strain_systems.get("neuromuscular_fatigued", False)
    else:
        sys_status_str = str(sys_status).lower()
        glyc_fatigued = "glycolytic" in sys_status_str or strain_systems.get("glycolytic_fatigued", False)
        neuro_fatigued = "neuromuscular" in sys_status_str or strain_systems.get("neuromuscular_fatigued", False)

    snapshot = {
        "local_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "athlete": {
            "ftp_watts": ftp,
            "w_prime_anaerobic_capacity_kj": w_prime_kj,
            "peak_power_watts": peak_power_watts,
            "max_hr_bpm": max_hr,
            "weight_kg": 70.0,
            "power_zones": power_zones
        },
        "whoop_readiness_today": {
            "recovery_score_pct": whoop.get("recovery_score", 50),
            "recovery_zone": "Green (Ready)" if whoop.get("recovery_score", 50) >= 67 else ("Red (Compromised)" if whoop.get("recovery_score", 50) < 34 else "Yellow (Moderate)"),
            "hrv_rmssd_ms": whoop.get("hrv_rmssd", 35.0),
            "resting_hr_bpm": whoop.get("resting_heart_rate", 52),
            "sleep_performance_pct": whoop.get("sleep_performance", 85),
            "sleep_duration_hours": whoop.get("sleep_duration_hours", 7.5),
            "day_strain_today": whoop.get("day_strain", 0.0),
            "trailing_7d_strain_avg": whoop.get("trailing_7d_strain_avg", whoop.get("trailing_strain", 11.0))
        },
        "strain_systems_3tier": {
            "trailing_7d_total_xss": strain_systems.get("trailing_7d", {}).get("total_xss", 0.0),
            "trailing_7d_low_xss": strain_systems.get("trailing_7d", {}).get("low_xss", 0.0),
            "trailing_7d_high_xss": strain_systems.get("trailing_7d", {}).get("high_xss", 0.0),
            "trailing_7d_peak_xss": strain_systems.get("trailing_7d", {}).get("peak_xss", 0.0),
            "acute_48h_high_xss": strain_systems.get("acute_48h", {}).get("high_xss", 0.0),
            "acute_48h_peak_xss": strain_systems.get("acute_48h", {}).get("peak_xss", 0.0),
            "glycolytic_fatigued": glyc_fatigued,
            "neuromuscular_fatigued": neuro_fatigued,
            "directive": strain_systems.get("recommendation_directive", strain_systems.get("directive", "BALANCED_TRAINING")),
            "directive_explanation": strain_systems.get("system_rationale", strain_systems.get("directive_explanation", ""))
        },
        "training_load_strava": {
            "trailing_7d_hours": weekly_stats.get("total_hours", 0.0),
            "trailing_7d_tss": weekly_stats.get("total_tss", 0),
            "trailing_7d_distance_miles": weekly_stats.get("total_distance_miles", weekly_stats.get("total_miles", 0.0)),
            "weekly_tss_target": program.get("weekly_tss_target", 360),
            "macrocycle_goal": program.get("goal_title", program.get("title", "FTP_BUILD")),
            "target_ftp": program.get("target_ftp", ftp + 15),
            "recent_rides": recent_rides_summary
        },
        "today_completed_activity": {
            "has_completed_today": len(today_acts) > 0,
            "activities": [
                {
                    "title": act.get("name"),
                    "duration_min": round(act.get("moving_time_sec", 0) / 60),
                    "distance_miles": round(act.get("distance_meters", 0) / 1609.34, 1),
                    "weighted_watts": act.get("weighted_average_watts", 0),
                    "tss": round(act.get("suffer_score", 0)),
                    "avg_hr": act.get("average_heartrate", 0)
                } for act in today_acts
            ]
        },
        "today_prescribed_workout": {
            "title": active_workout.get("title", "Sweet Spot Aerobic Density"),
            "focus_area": active_workout.get("focus_area", "Sweet Spot"),
            "duration_minutes": active_workout.get("duration_minutes", 60),
            "estimated_tss": active_workout.get("estimated_tss", 65),
            "total_xss": active_workout.get("total_xss", 0.0),
            "low_xss": active_workout.get("low_xss", 0.0),
            "high_xss": active_workout.get("high_xss", 0.0),
            "peak_xss": active_workout.get("peak_xss", 0.0),
            "focus_duration": active_workout.get("focus_duration", ""),
            "ai_rationale": active_workout.get("ai_rationale", ""),
            "alternative_options": [
                {"id": o.get("id"), "title": o.get("title"), "duration": o.get("duration_minutes"), "focus": o.get("focus_area")}
                for o in all_options
            ]
        },
        "active_target_event_plan": {
            "has_target_plan": bool(target_plan),
            "plan_title": target_plan.get("title") if target_plan else None,
            "target_date": target_plan.get("target_date") if target_plan else None,
            "distance_miles": target_plan.get("distance_miles") if target_plan else None,
            "elevation_gain_ft": target_plan.get("elevation_gain_ft") if target_plan else None,
            "intensity_type": target_plan.get("intensity_type") if target_plan else None
        }
    }

    # Include persistent coaching preferences & weekday schedule rules
    from app.services.preferences_service import get_coaching_preferences, get_day_target_config, get_weekday_rest_quota_and_status
    snapshot["athlete_coaching_preferences"] = get_coaching_preferences()
    snapshot["today_schedule_target"] = get_day_target_config()
    snapshot["weekly_rest_directive_status"] = get_weekday_rest_quota_and_status()

    return snapshot

def build_system_prompt(snapshot: Dict[str, Any]) -> str:
    """Builds the conversational sports-science system instruction for Gemini."""
    snapshot_json = json.dumps(snapshot, indent=2)
    return (
        "You are PowerSync AI Coach, a world-class cycling coach and sports physiologist. "
        "You speak directly, naturally, and warmly with your athlete Adam—just like an elite, friendly personal coach messaging with them.\n\n"
        "ATHLETE'S LIVE TELEMETRY & CONTEXT SNAPSHOT:\n"
        f"```json\n{snapshot_json}\n```\n\n"
        "COACHING & CONVERSATIONAL DIRECTIVES:\n"
        "1. DIRECTLY ANSWER THE QUESTION FIRST: Always answer whatever specific question, dilemma, or idea Adam brings up immediately and clearly. Never give evasive, canned, or generic template speeches.\n"
        "2. NATURAL, CONVERSATIONAL VOICE: Speak like a real human coach. Keep messages focused, concise, and easy to read. Use short paragraphs and bullet points only when breaking down workouts, intervals, or nutrition.\n"
        "3. GROUNDED IN REAL METRICS (WITHOUT INFODUMPING): You know Adam's Whoop recovery score, HRV, today's daytime strain, FTP, recent rides, and target event. Weave these relevant numbers in naturally when they support your answer, but do NOT dump an unsolicited list of stats unless Adam explicitly asks for a metrics breakdown.\n"
        "4. ACTIONABLE & SPECIFIC: When recommending pacing, intervals, or nutrition, give exact numbers: target watts, heart rate zones, duration, or grams of carbohydrates per hour.\n"
        "5. FLEXIBLE & COLLABORATIVE: If Adam wants to ride outdoors instead of indoors, do an easy spin instead of intervals, or take a rest day, collaborate with him enthusiastically and explain how to adjust while keeping weekly goals intact.\n"
        "6. NO CANNED INTRODUCTIONS OR DISCLAIMERS: Do not begin with 'As your AI coach' or repeat boilerplate disclaimers. Jump right into the answer.\n"
        "7. TWO-WAY WORKOUT PROPOSAL & SCHEDULING ACTION:\n"
        "Whenever Adam asks you to create, modify, design, replace, or schedule a workout or ride, OR tells you about an upcoming event or ride, append a structured JSON action proposal block at the very end of your response inside a fenced code block with identifier ```json:powersync_action\n\n"
        "There are THREE distinct action types—choose the appropriate one carefully:\n"
        "A. 'apply_today_workout': When Adam wants a workout for TODAY. Replaces or adapts today's workout on the dashboard.\n"
        "B. 'schedule_workout': When Adam wants to schedule a REGULAR DAILY WORKOUT for TOMORROW or an upcoming date (indoor trainer / Zwift session, over-unders, sweet spot, intervals, recovery spin). "
        "IMPORTANT: This is a standard daily workout, NOT a major target event or race! It must NOT create a target event plan, must NOT trigger a multi-day taper lead-up banner, and must NEVER have fake outdoor road distance like 40 miles for a 45-min workout (distance_miles must be 0.0 or realistic virtual miles, and elevation_gain_ft must be 0). When confirmed, it syncs directly to Zwift/Intervals.icu calendar for that target date.\n"
        "C. 'schedule_upcoming_plan': ONLY for Major Target Events, Gran Fondos, Century Rides, Races, or Big Destination Group Rides (typically 25+ miles or event-focused) that require a multi-day lead-up taper periodization.\n"
        "D. 'clear_upcoming_plan': Cancels or clears an active upcoming target event plan.\n\n"
        "CRITICAL WORKOUT DURATION INVARIANT:\n"
        "The total duration across all interval steps MUST EQUAL EXACTLY duration_minutes * 60 seconds! Intervals.icu and Zwift calculate workout duration strictly by summing step durations. If the steps sum to 30m or 39m, Intervals.icu will display 30m or 39m regardless of title! Always make sure (warmup + sum(repeats) + steady/bridge + cooldown) == duration_minutes * 60 seconds.\n\n"
        "Schema examples:\n"
        "```json:powersync_action\n"
        "{\n"
        '  "action_type": "schedule_workout", // or "apply_today_workout" or "schedule_upcoming_plan" or "clear_upcoming_plan"\n'
        '  "title": "45-Min Threshold Over-Unders",\n'
        '  "target_date": "YYYY-MM-DD", // required if schedule_workout or schedule_upcoming_plan\n'
        '  "focus_area": "Threshold Over-Unders",\n'
        '  "duration_minutes": 45,\n'
        '  "estimated_tss": 55,\n'
        '  "distance_miles": 0.0, // 0.0 for indoor interval workouts!\n'
        '  "elevation_gain_ft": 0, // 0 for indoor workouts!\n'
        '  "is_indoor": true,\n'
        '  "intensity_type": "Threshold",\n'
        '  "description": "Tomorrow\'s scheduled threshold over-unders session calibrated for your current FTP and readiness.",\n'
        '  "intervals": [\n'
        '    {"type": "Warmup", "duration_sec": 420, "power_low_pct": 45, "power_high_pct": 75, "cadence": 88, "name": "Gradual Wattage Ramp"},\n'
        '    {"type": "SteadyState", "duration_sec": 180, "power_pct": 90, "cadence": 92, "name": "Threshold Primer"},\n'
        '    {"type": "SteadyState", "duration_sec": 120, "power_pct": 55, "cadence": 85, "name": "Recovery Spin"},\n'
        '    {"type": "Repeats", "repeat": 6, "on_duration_sec": 120, "off_duration_sec": 60, "on_power_pct": 105, "off_power_pct": 90, "cadence": 94, "name": "6x Over-Under Blocks (2m @ 105% / 1m @ 90%)"},\n'
        '    {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 65, "power_high_pct": 40, "cadence": 80, "name": "Progressive Cooldown Ramp"}\n'
        '  ]\n'
        "}\n"
        "```\n"
        "Only output the powersync_action block when proposing, scheduling, or clearing a specific workout or plan.\n"
        "8. 3-TIER PHYSIOLOGICAL STRAIN ENGINE (XSS & W'bal EQUIVALENT):\n"
        "PowerSync tracks Adam's 3-parameter fitness signature (Critical Power/FTP, W' Anaerobic Work Capacity in kJ, and Peak Power P_max in Watts) and dynamically partitions training into Low (aerobic), High (glycolytic W' depletion), and Peak (neuromuscular sprint) strain alongside Skiba W'bal battery tracking. If Adam asks about training impact, XSS vs TSS, anaerobic battery depletion, or his fitness signature, reference these exact values and his current battery status.\n"
        "9. ATHLETE'S PERMANENT WORKOUT & SCHEDULE PREFERENCES (MANDATORY INVARIANTS):\n"
        "Adam has established strict permanent scheduling and interval training preferences that you MUST strictly respect in all advice and workout proposals:\n"
        "- WEEKDAY DURATION CONSTRAINTS:\n"
        "  * Monday, Tuesday, Thursday: 35–45 minutes ONLY (indoor efficiency priority). Never prescribe 60+ min workouts on these days unless explicitly requested. One of these days is also a rest candidate.\n"
        "  * Wednesday & Friday: 60+ minutes (an hour or more), outdoor priority if weather permits.\n"
        "  * Saturday: Dedicated weekly rest day.\n"
        "  * Sunday: 60–90+ minutes (outdoor endurance if weather permits, or long indoor session).\n"
        "- REST DAY DIRECTIVE & CONSECUTIVE TRAINING REASONING:\n"
        "  * Adam's directive specifies: one of Mon/Tue/Wed/Thu must be a rest day (or easy active recovery day).\n"
        "  * Check snapshot['weekly_rest_directive_status']: If Adam has trained on candidate days (e.g. Sunday, Monday, Tuesday, and Wednesday) with 0 rest days taken so far, Thursday is the final candidate day and MUST BE RECOMMENDED AS A REST DAY OR EASY DAY (gentle active recovery spin).\n"
        "  * DO NOT recommend hard intervals, Sweet Spot Over-Unders, or heavy sessions for Thursday in this state unless Adam explicitly asks to override his directive.\n"
        "- WARMUP & COOLDOWN RAMP INVARIANT (NO FLAT ZONE 2 BLOCKS):\n"
        "  * Adam explicitly dislikes flat steady Zone 2 warmups and cooldowns (e.g. 10m flat Z2, 6m flat Z2).\n"
        "  * ALWAYS prescribe progressive wattage ramps: progressive warmup ramp (45% -> 75% FTP over 6–8 min) and progressive cooldown ramp (65% -> 40% FTP over 4–5 min).\n"
        "- INTERVAL STYLE VARIETY & PERIODIZATION:\n"
        "  * Vary interval structures dynamically to drive progressive physiological adaptation without monotony: rotate across sustained blocks, stepped ladders, criss-cross surges, cadence ladders, pyramids, and over-unders.\n"
        "  * Always calibrate interval intensity and volume to his active target plan and current recovery state.\n"
        "- PREFERENCES MEMORY & LEARNING:\n"
        "  * If Adam mentions a new preference, constraint, or rule in chat (e.g., 'Remember that I prefer...', 'From now on...', 'I like/hate...'), confirm warmly that you have remembered and permanently saved it to his PowerSync coaching engine."
    )

def extract_action_from_response(text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Extracts structured workout or planning actions formatted by Gemini in ```json:powersync_action ... ```
    (or legacy ```json:aerosync_action ... ```) or ```json ... "action_type" ... ``` blocks. Removes the block from the conversational text.
    """
    if not text:
        return text, None

    action_data = None
    # 1. Match ```json:powersync_action ... ``` or legacy ```json:aerosync_action ... ```
    match = re.search(r'```(?:json:powersync_action|powersync_action|json:aerosync_action|aerosync_action)\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            action_data = json.loads(match.group(1))
            text = text[:match.start()] + text[match.end():]
        except Exception as e:
            print("Failed to parse powersync_action JSON:", e)

    # 2. Match generic ```json ... "action_type" ... ```
    if not action_data:
        gen_match = re.search(r'```(?:json)?\s*(\{\s*"action_type".*?\})\s*```', text, re.DOTALL)
        if gen_match:
            try:
                action_data = json.loads(gen_match.group(1))
                text = text[:gen_match.start()] + text[gen_match.end():]
            except Exception as e:
                print("Failed to parse generic action JSON:", e)

    return text.strip(), action_data

def build_sports_science_action(user_message: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Constructs a structured action payload from user intent for fallback or supplemental matching.
    """
    msg = user_message.lower().strip()
    ftp = int(snapshot.get("athlete", {}).get("ftp_watts", 250))
    today = datetime.date.today()

    # 0. Check for plan cancellation / clear intent
    has_cancel_verb = any(v in msg for v in ["cancel", "clear", "remove", "delete", "drop", "reset"])
    has_plan_noun = any(n in msg for n in ["plan", "upcoming", "event", "target", "ride", "schedule"])
    is_clear_intent = (has_cancel_verb and has_plan_noun) or any(k in msg for k in [
        "no longer doing", "wont be doing", "won't be doing", "not doing"
    ])
    if is_clear_intent:
        return {
            "action_type": "clear_upcoming_plan",
            "title": "Clear Target Event Plan",
            "description": "Revert to standard training macrocycle progression and clear lead-up taper."
        }

    # 1. Check for daily workout / interval session intent (today OR scheduled for tomorrow/future date)
    is_pure_review = any(k in msg for k in ["review", "history", "why did", "what happened", "explain my"]) and not any(k in msg for k in [
        "give me a", "schedule", "create", "make a", "prescribe", "swap", "change", "what workout", "suggest a workout"
    ])
    wants_workout = (not is_pure_review) and any(k in msg for k in [
        "intervals", "spin", "ride today", "sweet spot", "sst", "tempo",
        "vo2", "recovery", "flush", "threshold", "over-under", "over under", "overunder",
        "trainer", "zwift", "shorter", "20 min", "25 min", "30 min", "45 min", "60 min",
        "75 min", "90 min", "give me a", "make a", "create a", "suggest a", "change to",
        "swap to", "switch to", "can i do", "put together", "schedule", "new workout", "prescribe"
    ])
    
    # Check if this is an explicit major target event or large outdoor ride (NOT a daily workout)
    is_major_event = any(k in msg for k in [
        "gran fondo", "century", "century ride", "target event", "target plan",
        "charity ride", "gravel race", "crit", "fondo"
    ])
    large_dist_match = re.search(r'\b([2-9]\d|\d{3})\s*[-–—]?\s*(?:miles|mile|mi)\b', msg)

    if wants_workout and not is_major_event and not (large_dist_match and not any(w in msg for w in ["over", "interval", "trainer", "zwift"])):
        # Detect duration
        # Detect duration with fallback to athlete's day-of-week target preferences
        dur_match = re.search(r'\b(20|25|30|35|40|45|50|60|75|90|120)\s*(?:m|min|mins|minutes)?\b', msg)

        # Detect timing: tomorrow / future date vs today
        is_future = any(k in msg for k in [
            "tomorrow", "sunday", "saturday", "weekend", "next week",
            "friday", "monday", "thursday", "wednesday", "tuesday", "future"
        ]) or ("schedule" in msg and not any(t in msg for t in ["today", "now"]))

        target_date = None
        if is_future:
            if "tomorrow" in msg:
                target_date = (today + datetime.timedelta(days=1)).isoformat()
            else:
                weekdays = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6
                }
                matched_day = None
                for d_name, d_idx in weekdays.items():
                    if re.search(rf'\b{d_name}\b', msg):
                        matched_day = d_idx
                        break
                if matched_day is not None:
                    days_ahead = (matched_day - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target_date = (today + datetime.timedelta(days=days_ahead)).isoformat()
                else:
                    target_date = (today + datetime.timedelta(days=1)).isoformat()

        if dur_match:
            dur = int(dur_match.group(1))
        else:
            from app.services.preferences_service import get_day_target_config
            t_date = datetime.date.fromisoformat(target_date) if target_date else today
            day_cfg = get_day_target_config(t_date)
            preferred = day_cfg.get("preferred_duration_min", 45)
            dur = preferred if preferred > 0 else 35

        # Invariant: Warmups are progressive ramps (45% -> 75%), Cooldowns are ramps (65% -> 40%)
        w_dur = 360 if dur <= 40 else 420
        c_dur = 240 if dur <= 40 else 300

        # Build specific interval block structure using dynamic workout catalog
        from app.services.workout_catalog import select_diverse_archetype
        if any(k in msg for k in ["over-under", "over under", "overunder"]):
            selected = select_diverse_archetype("sweet_spot", dur, ftp=ftp, forced_archetype_id="sst_over_under")
            focus = selected["focus_area"]
            title = selected["title"]
            tss = selected["estimated_tss"]
            intervals = selected["intervals"]
        elif any(k in msg for k in ["vo2", "microburst", "anaerobic", "tabata"]):
            selected = select_diverse_archetype("vo2_max", dur, ftp=ftp)
            focus = selected["focus_area"]
            title = selected["title"]
            tss = selected["estimated_tss"]
            intervals = selected["intervals"]
        elif any(k in msg for k in ["sweet spot", "sst", "density", "threshold"]):
            selected = select_diverse_archetype("sweet_spot", dur, ftp=ftp)
            focus = selected["focus_area"]
            title = selected["title"]
            tss = selected["estimated_tss"]
            intervals = selected["intervals"]
        elif any(k in msg for k in ["recovery", "easy", "flush", "spin", "rest"]):
            focus = "Active Recovery"
            title = f"{dur}-Min Cadence Flush & Spin"
            tss = round(dur * 0.40)
            intervals = [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 40, "power_high_pct": 52, "cadence": 88, "name": "Gentle Ramp Up"},
                {"type": "SteadyState", "duration_sec": max(300, (dur * 60) - 540), "power_pct": 52, "cadence": 92, "name": "Zone 1 Aerobic Flush"},
                {"type": "Cooldown", "duration_sec": 240, "power_low_pct": 52, "power_high_pct": 38, "cadence": 82, "name": "Gentle Spin Out"}
            ]
        elif any(k in msg for k in ["tempo", "pace", "steady"]):
            selected = select_diverse_archetype("tempo", dur, ftp=ftp)
            focus = selected["focus_area"]
            title = selected["title"]
            tss = selected["estimated_tss"]
            intervals = selected["intervals"]
        else:
            selected = select_diverse_archetype("endurance_base", dur, ftp=ftp)
            focus = selected["focus_area"]
            title = selected["title"]
            tss = selected["estimated_tss"]
            intervals = selected["intervals"]

        from app.services.zwift_service import reconcile_workout_intervals
        intervals = reconcile_workout_intervals(intervals, dur, ftp=ftp)

        if is_future:
            return {
                "action_type": "schedule_workout",
                "title": title,
                "target_date": target_date,
                "focus_area": focus,
                "duration_minutes": dur,
                "estimated_tss": tss,
                "distance_miles": 0.0,
                "elevation_gain_ft": 0.0,
                "is_indoor": True,
                "intensity_type": focus,
                "description": f"Scheduled {dur}m {focus} session for {target_date}.",
                "intervals": intervals
            }
        else:
            return {
                "action_type": "apply_today_workout",
                "title": title,
                "focus_area": focus,
                "duration_minutes": dur,
                "estimated_tss": tss,
                "distance_miles": 0.0,
                "elevation_gain_ft": 0.0,
                "is_indoor": True,
                "intensity_type": focus,
                "description": f"Tailored {dur}m session with {focus} target intervals.",
                "intervals": intervals
            }

    # 2. Check for Major Target Event Plan (Gran Fondo, Century, 50-mile race, etc.)
    if is_major_event or (large_dist_match and any(k in msg for k in ["ride", "plan", "doing", "riding", "sunday", "saturday", "weekend"])):
        try:
            from app.services.plan_service import parse_plan_description
            parsed = parse_plan_description(user_message)
            if parsed.get("success"):
                return {
                    "action_type": "schedule_upcoming_plan",
                    "title": parsed["title"],
                    "target_date": parsed["target_date"],
                    "distance_miles": parsed["distance_miles"],
                    "elevation_gain_ft": parsed["elevation_gain_ft"],
                    "intensity_type": parsed["intensity_type"],
                    "duration_minutes": parsed["estimated_duration_min"],
                    "estimated_tss": parsed["estimated_tss"],
                    "description": f"{parsed['title']} ({parsed['distance_miles']} mi, ~{parsed['estimated_tss']} TSS, {parsed['elevation_gain_ft']} ft elev)"
                }
        except Exception as e:
            print("Error parsing plan description in chat:", e)

    return None

def clean_model_output(text: str) -> str:
    """Strips chain-of-thought scratchpad, markdown thinking blocks, or role-playing echoes."""
    if not text:
        return ""
    # Strip <thought>...</thought> tags if present
    cleaned = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    # Strip raw scratchpad lines if a model outputs its internal planning
    if "* Input:" in cleaned and "* Goal:" in cleaned:
        parts = cleaned.split('"\n')
        if len(parts) > 1:
            cleaned = parts[-1].strip().strip('"')
        else:
            lines = [l for l in cleaned.splitlines() if not re.match(r'^\s*\*\s*(Input|Role|Goal|Option|Since|As a|The user):', l)]
            cleaned = "\n".join(lines).strip()
    return cleaned.strip()

_CACHED_WORKING_MODEL: Optional[Tuple[str, str]] = ("v1beta", "gemini-flash-latest")

def call_gemini_api(api_key: str, system_instruction: str, history: List[Dict[str, str]], user_message: str) -> Optional[str]:
    """Calls Google Gemini API with multi-turn conversation support and model fallbacks."""
    global _CACHED_WORKING_MODEL

    models_to_try = [
        ("v1beta", "gemini-3-flash-preview"),
        ("v1beta", "gemini-2.5-flash"),
        ("v1beta", "gemini-3.8-flash"),
        ("v1beta", "gemini-3.1-flash-lite"),
        ("v1beta", "gemini-3.5-flash"),
        ("v1beta", "gemini-3.7-flash"),
        ("v1beta", "gemini-flash-latest"),
        ("v1beta", "gemini-2.5-pro"),
        ("v1beta", "gemini-pro-latest"),
    ]

    if _CACHED_WORKING_MODEL and _CACHED_WORKING_MODEL in models_to_try:
        models_to_try.remove(_CACHED_WORKING_MODEL)
        models_to_try.insert(0, _CACHED_WORKING_MODEL)
    elif _CACHED_WORKING_MODEL:
        models_to_try.insert(0, _CACHED_WORKING_MODEL)

    # Clean and structure conversation history so turns strictly alternate user -> model
    contents = []
    clean_history = []
    for msg in history:
        text = (msg.get("text") or msg.get("content") or "").strip()
        role = "user" if msg.get("role") in ["user", "athlete"] else "model"
        if text and text != user_message:
            clean_history.append({"role": role, "text": text})

    for msg in clean_history[-8:]:
        role = msg["role"]
        text = msg["text"]
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += f"\n\n{text}"
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    if contents and contents[-1]["role"] == "user":
        contents.pop()

    # Append current user message
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192
        }
    }

    headers = {"Content-Type": "application/json"}

    for api_ver, model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    finish_reason = candidates[0].get("finishReason")
                    if finish_reason == "MAX_TOKENS":
                        print(f"WARNING: Gemini {api_ver}/{model} hit MAX_TOKENS limit!")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "") for p in parts if "text" in p and p.get("text") and not p.get("thought")]
                    full_text = "\n".join(text_parts).strip()
                    clean_text = clean_model_output(full_text)
                    if clean_text:
                        _CACHED_WORKING_MODEL = (api_ver, model)
                        print(f"Gemini API success using {api_ver}/{model} (finish_reason: {finish_reason}, len: {len(clean_text)})")
                        return clean_text
            else:
                print(f"Gemini {api_ver}/{model} returned HTTP {res.status_code}: {res.text[:100]}")
        except Exception as e:
            print(f"Gemini API error with {api_ver}/{model}: {e}")

    # If predefined models failed, query ListModels for active Gemini-specific models
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        l_res = requests.get(list_url, timeout=10)
        if l_res.status_code == 200:
            models_data = l_res.json().get("models", [])
            valid_models = []
            for m in models_data:
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    m_name = m.get("name", "")
                    if m_name.startswith("models/"):
                        m_name = m_name[len("models/"):]
                    # STRICTLY filter to Gemini models (avoid unaligned raw models)
                    if m_name and m_name.startswith("gemini"):
                        valid_models.append(m_name)
            print(f"ListModels discovered {len(valid_models)} Gemini models: {valid_models[:6]}")
            for vm in valid_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{vm}:generateContent?key={api_key}"
                try:
                    res = requests.post(url, headers=headers, json=payload, timeout=25)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            finish_reason = candidates[0].get("finishReason")
                            if finish_reason == "MAX_TOKENS":
                                print(f"WARNING: Discovered Gemini model {vm} hit MAX_TOKENS limit!")
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text_parts = [p.get("text", "") for p in parts if "text" in p and p.get("text") and not p.get("thought")]
                            full_text = "\n".join(text_parts).strip()
                            clean_text = clean_model_output(full_text)
                            if clean_text:
                                _CACHED_WORKING_MODEL = ("v1beta", vm)
                                print(f"Successfully generated response with discovered Gemini model: {vm} (finish_reason: {finish_reason})")
                                return clean_text
                except Exception as ex:
                    print(f"Error querying discovered model {vm}: {ex}")
        else:
            print(f"ListModels returned HTTP {l_res.status_code}: {l_res.text[:120]}")
    except Exception as e:
        print(f"ListModels diagnostic error: {e}")

    return None

def generate_sports_science_fallback_response(user_message: str, snapshot: Dict[str, Any]) -> str:
    """
    Empathetic, highly conversational sports-science coach that directly answers
    the athlete's questions when network calls or quotas are temporarily unavailable.
    """
    msg = user_message.lower().strip()
    ftp = snapshot["athlete"]["ftp_watts"]
    rec = snapshot["whoop_readiness_today"]["recovery_score_pct"]
    rec_zone = snapshot["whoop_readiness_today"]["recovery_zone"]
    hrv = snapshot["whoop_readiness_today"]["hrv_rmssd_ms"]
    today_strain = snapshot["whoop_readiness_today"]["day_strain_today"]
    prescribed = snapshot["today_prescribed_workout"]["title"]
    prescribed_dur = snapshot["today_prescribed_workout"]["duration_minutes"]
    tss = snapshot["today_prescribed_workout"]["estimated_tss"]
    recent = snapshot["training_load_strava"]["recent_rides"]
    last_ride = recent[0] if recent else None

    # 0a. Clear / Cancel upcoming target event
    has_cancel_verb = any(v in msg for v in ["cancel", "clear", "remove", "delete", "drop", "reset"])
    has_plan_noun = any(n in msg for n in ["plan", "upcoming", "event", "target", "ride", "schedule"])
    is_clear = (has_cancel_verb and has_plan_noun) or any(k in msg for k in [
        "no longer doing", "wont be doing", "won't be doing", "not doing"
    ])
    if is_clear:
        return (
            "I've got you covered, Adam. I've staged the cancellation of your upcoming target plan. "
            "Your forward outlook and daily training prescriptions will revert to your standard macrocycle progression. "
            "Tap **Confirm Clear Plan** below to reset your dashboard."
        )

    # 0d. Thursday / Tomorrow rest directive inquiry
    rest_stat = snapshot.get("weekly_rest_directive_status", {})
    if any(k in msg for k in ["tomorrow", "thursday", "next ride", "what should i do", "what's next", "whats next", "recommend"]):
        if rest_stat.get("is_thursday_mandated_rest") and not any(k in msg for k in ["over-under", "over under", "vo2", "sweet spot", "threshold", "hard"]):
            streak_text = rest_stat.get("completed_streak_text", "Sunday, Monday, Tuesday, and Wednesday")
            return (
                f"Taking a close look at your training week, Adam: you've already completed workouts on {streak_text}—"
                f"that's {rest_stat.get('consecutive_streak', 4)} consecutive days on the bike!\n\n"
                f"Your forward directive specifies that **one of Mon/Tue/Wed/Thu should be a rest day**. "
                f"Because you haven't taken a rest day yet this week across Monday through Wednesday, **Thursday is designated as your rest day or an easy day**.\n\n"
                f"- **Recommended Option 1 (Full Rest)**: Take Thursday completely off the bike to clear systemic fatigue and let muscle glycogen stores supercompensate.\n"
                f"- **Recommended Option 2 (Easy Active Flush)**: A gentle 20–30 minute Zone 1 spin (<55% FTP, <{round(ftp * 0.55)}W) to promote lymphatic circulation.\n\n"
                f"Taking Thursday easy ensures you are fresh, recovered, and ready for Friday's 60+ min ride!"
            )

    # 0b. Daily Workout Scheduling Intent (e.g. tomorrow's workout, over-unders, intervals, sweet spot)
    is_workout_schedule = any(k in msg for k in [
        "workout", "intervals", "over-under", "over under", "overunder",
        "sweet spot", "sst", "vo2", "threshold", "spin", "recovery", "tempo"
    ]) and any(k in msg for k in [
        "tomorrow", "schedule", "calendar", "sunday", "saturday", "weekend",
        "next", "friday", "monday", "thursday", "wednesday", "tuesday"
    ])
    if is_workout_schedule:
        dur_match = re.search(r'\b(20|25|30|35|40|45|50|60|75|90)\s*(?:m|min|mins|minutes)?\b', msg)
        dur = int(dur_match.group(1)) if dur_match else 45

        target_day_str = "tomorrow"
        if "tomorrow" in msg:
            target_day_str = "tomorrow"
        else:
            for d in ["sunday", "saturday", "friday", "monday", "tuesday", "wednesday", "thursday"]:
                if d in msg:
                    target_day_str = d.capitalize()
                    break

        if any(k in msg for k in ["over-under", "over under", "overunder", "threshold"]):
            return (
                f"Locked in for {target_day_str}, Adam! I've scheduled your **{dur}-Min Threshold Over-Unders** (~{round(dur * 0.82)} TSS).\n\n"
                f"- **Why Over-Unders**: By oscillating between 105% FTP (Over: ~{round(ftp * 1.05)}W) and 90% FTP (Under: ~{round(ftp * 0.90)}W), your body floods the working muscles with lactate during the surges and trains your oxidative fibers to rapidly clear it during the unders.\n"
                f"- **Structure**: 8-minute progressive warmup, 3-minute threshold primer, then Over-Under blocks (2m @ 105% / 1m @ 90%), wrapping with a 5-minute spin-down.\n"
                f"- **Indoor Trainer / Zwift**: Calibrated as an indoor session (0 elevation, pure power execution).\n\n"
                f"Tap **Sync to Zwift Calendar** below to push this workout directly to Intervals.icu and Zwift for {target_day_str}!"
            )
        elif any(k in msg for k in ["sweet spot", "sst"]):
            return (
                f"Set for {target_day_str}, Adam! I've scheduled your **{dur}-Min Sweet Spot Aerobic Density** (~{round(dur * 0.80)} TSS).\n\n"
                f"- **Focus**: Steady intervals at 88–92% FTP (~{round(ftp * 0.90)}W) for maximum mitochondrial density with low systemic fatigue.\n"
                f"- **Execution**: 8m warmup, repeated 8m blocks at {round(ftp * 0.90)}W, and 5m cooldown.\n\n"
                f"Tap **Sync to Zwift Calendar** below to push this workout to your calendar!"
            )
        elif any(k in msg for k in ["vo2", "microburst", "anaerobic"]):
            return (
                f"Ready for high intensity on {target_day_str}, Adam! I've scheduled your **{dur}-Min VO2 Max High Intensity** session (~{round(dur * 0.95)} TSS).\n\n"
                f"- **Focus**: 3-minute intervals at 115% FTP (~{round(ftp * 1.15)}W) to drive maximal stroke volume and respiratory ceiling.\n\n"
                f"Tap **Sync to Zwift Calendar** below to load it into Zwift!"
            )
        elif any(k in msg for k in ["recovery", "spin", "easy", "flush"]):
            return (
                f"Dialled in for {target_day_str}, Adam! I've scheduled your **{dur}-Min Cadence Flush & Spin** (~{round(dur * 0.40)} TSS).\n\n"
                f"- **Focus**: Gentle Zone 1 spinning (<55% FTP, ~{round(ftp * 0.50)}W) to promote lymphatic circulation without triggering sympathetic fatigue.\n\n"
                f"Tap **Sync to Zwift Calendar** below to sync!"
            )
        else:
            return (
                f"Scheduled for {target_day_str}, Adam! I've set up your **{dur}-Min Zone 2 Aerobic Foundation** session (~{round(dur * 0.60)} TSS).\n\n"
                f"- **Focus**: Smooth cruising at 65–72% FTP (~{round(ftp * 0.70)}W) to build metabolic efficiency.\n\n"
                f"Tap **Sync to Zwift Calendar** below to push to your Zwift calendar!"
            )

    # 0c. Major Target Event scheduling intent (Gran Fondo, Century, 50-mile race, etc.)
    is_major_event = any(k in msg for k in [
        "gran fondo", "century", "century ride", "target event", "target plan", "race", "fondo", "charity ride", "gravel race"
    ]) or (
        bool(re.search(r'\b([2-9]\d|\d{3})\s*[-–—]?\s*(?:miles|mile|mi)\b', msg)) and any(k in msg for k in ["sunday", "saturday", "weekend", "next", "ride", "climb", "doing"])
    )
    if is_major_event:
        from app.services.plan_service import parse_plan_description
        p = parse_plan_description(user_message)
        if p.get("success"):
            title = p["title"]
            dist = p["distance_miles"]
            elev = p["elevation_gain_ft"]
            t_date = p["target_date"]
            tss = p["estimated_tss"]
            intensity = p["intensity_type"]
            return (
                f"Awesome target event, Adam! I've analyzed your upcoming **{title}** on **{t_date}** "
                f"({dist} miles, ~{elev:,} ft climbing, est. **~{tss} TSS**, {intensity} pacing).\n\n"
                f"I've configured your lead-up taper progression:\n"
                f"- **T-2 Days**: Gentle active recovery spin (<55% FTP) to clear metabolic fatigue.\n"
                f"- **T-1 Day**: 30-minute neuromuscular priming spin with 3x 30s cadence openers to wake up motor unit firing while sparing glycogen.\n"
                f"- **Event Day**: Target {intensity} pacing with 60–80g carbs/hr and electrolyte hydration.\n\n"
                f"Tap **Set as Target Event & Activate Taper** below to lock this into your Mission Control banner!"
            )

    # 1. Casual / Greetings / Persona Questions
    if any(k in msg for k in ["hi", "hello", "hey", "how are you", "what's up", "who are you", "good morning", "good evening"]):
        return (
            f"Hey Adam! I'm locked in and ready to coach. "
            f"Looking at your live telemetry, you're at **{rec}% Whoop recovery** ({rec_zone}) with an HRV of **{hrv} ms** today. "
            f"We've got **{prescribed}** ({prescribed_dur} mins, ~{tss} TSS) on deck. "
            f"How are the legs feeling today—ready to roll, or do you want to adjust the plan?"
        )

    # 2. Outdoor vs Indoor / Change Environment
    if any(k in msg for k in ["outside", "outdoor", "road", "weather", "route"]):
        return (
            f"You can definitely take it outside! With your recovery at **{rec}%**, the main key for an outdoor ride is discipline on climbs. "
            f"On the trainer it's easy to hold steady power, but outside it's tempting to surge on hills. "
            f"For today, keep your flat cruising power around **{round(ftp * 0.65)}–{round(ftp * 0.75)}W** (Zone 2) and cap your hill efforts at **{round(ftp * 0.88)}W** to avoid accumulating autonomic fatigue. "
            f"Make sure to load the route into your bike computer and stay smooth on the pedals!"
        )

    # 3. Rest Day / Feeling Tired / Can I Skip
    if any(k in msg for k in ["rest", "tired", "exhausted", "skip", "take off", "sore", "lazy", "can i not"]):
        return (
            f"Listen to your body, Adam. With your Whoop recovery currently at **{rec}%** and HRV at **{hrv} ms**, taking today as an active recovery day or full rest is a 100% smart coaching call.\n\n"
            f"If you still want to spin your legs, do an easy 25-minute recovery spin below **{round(ftp * 0.50)}W** (just spinning the flush out the legs). "
            f"Otherwise, take the full day off, prioritize hydration and sleep tonight, and we'll hit **{prescribed}** fresh tomorrow when your recovery rebounds."
        )

    # 4. Modifying Duration / Shorter or Longer Ride
    if any(k in msg for k in ["30 min", "45 min", "shorter", "short on time", "longer", "more time", "duration"]):
        return (
            f"We can adapt that easily! If you only have 30–45 minutes today, quality and consistency always beat skipping the session entirely.\n\n"
            f"- **Warmup**: 6 minutes spinning up to {round(ftp * 0.65)}W.\n"
            f"- **Main Set**: 2 blocks of 8 minutes at Sweet Spot (**{round(ftp * 0.88)}–{round(ftp * 0.92)}W**), with 3 minutes easy spinning in between.\n"
            f"- **Cooldown**: 5 minutes easy.\n\n"
            f"That gives you a great training impulse (~35 TSS) in just 30 minutes without overloading your current **{rec}% recovery**."
        )

    # 5. Daily Nutrition vs Meal Questions (Dinner, Breakfast, Post-workout)
    if any(k in msg for k in ["dinner", "breakfast", "lunch", "meal", "what to eat", "eat tonight", "food"]):
        return (
            f"For your meals today around your **{rec}% recovery**:\n\n"
            f"- **Prioritize Complex Carbs**: Sweet potatoes, quinoa, rice, or whole grain pasta to replenish glycogen stores.\n"
            f"- **Protein Goal**: Aim for 25–35g of lean protein (chicken, salmon, tofu, or Greek yogurt) to support muscle repair.\n"
            f"- **Electrolytes & Hydration**: Drink a tall glass of water with ~400mg sodium and magnesium before bed to support parasympathetic nervous system recovery and boost tomorrow's HRV."
        )

    # 6. On-the-Bike Fueling & Carbs
    if any(k in msg for k in ["fuel", "gel", "drink", "mix", "carb", "hydration", "bottle"]):
        carb_rate = "60–75g/hr" if "sweet" in prescribed.lower() or "vo2" in prescribed.lower() else "45–60g/hr"
        return (
            f"For today's session (**{prescribed}**, {prescribed_dur} mins):\n\n"
            f"- **Target Carbs**: **{carb_rate}** on the bike. Aim for 1 gel every 30 minutes or a high-carb drink mix in your bottle.\n"
            f"- **Hydration**: Sip **500–700 ml fluid/hour** with electrolytes.\n"
            f"- **Timing**: Because your recovery is at {rec}%, start taking carbs early at minute 15 rather than waiting until you feel fatigued."
        )

    # 7. Yesterday's Ride or Strava History
    if any(k in msg for k in ["yesterday", "recent", "strava", "last ride", "review my ride"]):
        if last_ride:
            return (
                f"Looking back at your recent ride **'{last_ride['name']}'**:\n\n"
                f"- **Duration & Distance**: {last_ride['duration_min']} mins ({last_ride['distance_miles']} miles)\n"
                f"- **Normalized Power**: **{last_ride['normalized_power_watts']}W** ({last_ride['pct_ftp']}% of your {ftp}W FTP)\n"
                f"- **Training Stress**: **{last_ride['tss']} TSS**\n\n"
                f"That was a solid stimulus that contributed to your current **{rec}% recovery**. Your body is adapting well, but that's why keeping today's intensity controlled is crucial."
            )

    # 8. Recovery, HRV, Sleep Details
    if any(k in msg for k in ["recovery", "whoop", "sleep", "hrv", "strain"]):
        return (
            f"Here is how your physiological readiness stands today:\n\n"
            f"- **Whoop Recovery**: **{rec}%** ({rec_zone})\n"
            f"- **HRV**: **{hrv} ms** (Resting HR: {snapshot['whoop_readiness_today']['resting_hr_bpm']} bpm)\n"
            f"- **Sleep Logged**: {snapshot['whoop_readiness_today']['sleep_duration_hours']} hrs ({snapshot['whoop_readiness_today']['sleep_performance_pct']}% sleep score)\n"
            f"- **Daytime Strain Accumulated**: {today_strain}\n\n"
            f"Your autonomic nervous system is showing normal trailing fatigue from recent training blocks. Focus on steady aerobic efforts today rather than all-out maximal sprints."
        )

    # 9. Conversational Default Answer
    target_text = f" aiming toward **{snapshot['active_target_event_plan']['plan_title']}**" if snapshot["active_target_event_plan"]["has_target_plan"] else ""
    return (
        f"Right on, Adam. With your recovery sitting at **{rec}%** and FTP calibrated to **{ftp}W**, "
        f"my focus today is keeping you progressing smoothly{target_text} without overreaching.\n\n"
        f"For today, our scheduled session is **{prescribed}** ({prescribed_dur} mins, ~{tss} TSS). "
        f"Would you like to execute that on Zwift/trainer, swap to an outdoor route, or do an easy recovery spin instead?"
    )

def handle_coach_chat(user_message: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Main entry point for Chat with Coach:
    1. Checks if user pasted an API key -> auto-saves to settings.
    2. Compiles full athlete telemetry snapshot.
    3. Calls Google Gemini (if key configured).
    4. Seamlessly falls back to deep sports-science engine if key is absent.
    """
    history = history or []
    user_message = user_message.strip()

    # 1. Check for athlete preferences learning trigger
    from app.services.preferences_service import extract_and_learn_preferences_from_text
    learned_directive = extract_and_learn_preferences_from_text(user_message)
    learned_notice = ""
    if learned_directive:
        learned_notice = f"🧠 **Saved to Coaching Profile:** *\"{learned_directive}\"*\n\n"

    # 2. Check for inline API key configuration
    detected_key = extract_gemini_key_from_text(user_message)
    key_saved_notice = ""
    if detected_key:
        set_setting("gemini_api_key", detected_key)
        key_saved_notice = "✨ **Google Gemini API Key saved successfully!** Connecting to Gemini Flash...\n\n"

    # 3. Retrieve athlete context snapshot (reflects newly saved preference)
    snapshot = compile_athlete_context()

    # 4. Retrieve API Key
    api_key = get_gemini_api_key()

    if api_key:
        system_prompt = build_system_prompt(snapshot)
        gemini_reply = call_gemini_api(api_key, system_prompt, history, user_message)
        if gemini_reply:
            model_used = _CACHED_WORKING_MODEL[1] if _CACHED_WORKING_MODEL else "gemini"
            clean_reply, proposed_action = extract_action_from_response(gemini_reply)
            if not proposed_action:
                has_action_request = any(k in user_message.lower() for k in [
                    "give me a", "schedule", "create a", "make a", "prescribe", "suggest a workout",
                    "change to", "swap to", "switch to", "put together", "plan a ride", "upcoming ride",
                    "cancel plan", "clear plan", "what workout should i do", "what should i do today"
                ])
                if has_action_request:
                    proposed_action = build_sports_science_action(user_message, snapshot)

            if proposed_action and "intervals" in proposed_action and "duration_minutes" in proposed_action:
                from app.services.zwift_service import reconcile_workout_intervals
                proposed_action["intervals"] = reconcile_workout_intervals(
                    proposed_action["intervals"],
                    int(proposed_action["duration_minutes"]),
                    ftp=snapshot["athlete"]["ftp_watts"]
                )

            # Prepend learned notice if Gemini didn't mention saving it
            reply_text = clean_reply
            if learned_notice and not any(w in clean_reply.lower() for w in ["saved", "remembered", "profile", "coaching directives"]):
                reply_text = learned_notice + reply_text

            return {
                "success": True,
                "reply": key_saved_notice + reply_text,
                "provider": "gemini",
                "model": model_used,
                "gemini_configured": True,
                "proposed_action": proposed_action,
                "athlete_snapshot": {
                    "ftp": snapshot["athlete"]["ftp_watts"],
                    "recovery_score": snapshot["whoop_readiness_today"]["recovery_score_pct"],
                    "hrv": snapshot["whoop_readiness_today"]["hrv_rmssd_ms"],
                    "active_workout": snapshot["today_prescribed_workout"]["title"]
                }
            }
        else:
            print("Gemini API call returned null or failed, using sports science fallback.")

    # 5. Sports-science rule-based fallback
    fallback_reply = generate_sports_science_fallback_response(user_message, snapshot)
    if learned_notice:
        fallback_reply = learned_notice + fallback_reply
    proposed_action = build_sports_science_action(user_message, snapshot)
    if proposed_action and "intervals" in proposed_action and "duration_minutes" in proposed_action:
        from app.services.zwift_service import reconcile_workout_intervals
        proposed_action["intervals"] = reconcile_workout_intervals(
            proposed_action["intervals"],
            int(proposed_action["duration_minutes"]),
            ftp=snapshot["athlete"]["ftp_watts"]
        )

    return {
        "success": True,
        "reply": key_saved_notice + fallback_reply,
        "provider": "sports_science_engine",
        "model": "powersync-coach-v1",
        "gemini_configured": bool(api_key),
        "proposed_action": proposed_action,
        "athlete_snapshot": {
            "ftp": snapshot["athlete"]["ftp_watts"],
            "recovery_score": snapshot["whoop_readiness_today"]["recovery_score_pct"],
            "hrv": snapshot["whoop_readiness_today"]["hrv_rmssd_ms"],
            "active_workout": snapshot["today_prescribed_workout"]["title"]
        }
    }

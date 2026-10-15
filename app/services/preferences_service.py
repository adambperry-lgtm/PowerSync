import datetime
from typing import Dict, Any, List, Optional
from app.database import get_setting, set_setting

DEFAULT_COACHING_PREFERENCES: Dict[str, Any] = {
    "weekly_schedule": {
        "monday": {
            "name": "Monday",
            "preferred_duration_min": 45,
            "min_duration_min": 35,
            "max_duration_min": 45,
            "mode": "indoor_priority",
            "is_rest_candidate": True,
            "notes": "35–45 min indoor session or rest day"
        },
        "tuesday": {
            "name": "Tuesday",
            "preferred_duration_min": 45,
            "min_duration_min": 35,
            "max_duration_min": 45,
            "mode": "indoor_priority",
            "is_rest_candidate": True,
            "notes": "35–45 min indoor efficiency session"
        },
        "wednesday": {
            "name": "Wednesday",
            "preferred_duration_min": 60,
            "min_duration_min": 60,
            "max_duration_min": 90,
            "mode": "outdoor_priority",
            "is_rest_candidate": False,
            "notes": "60+ min (an hour or more), outdoor if weather allows"
        },
        "thursday": {
            "name": "Thursday",
            "preferred_duration_min": 45,
            "min_duration_min": 35,
            "max_duration_min": 45,
            "mode": "indoor_priority",
            "is_rest_candidate": True,
            "notes": "35–45 min indoor session or rest day"
        },
        "friday": {
            "name": "Friday",
            "preferred_duration_min": 60,
            "min_duration_min": 60,
            "max_duration_min": 90,
            "mode": "outdoor_priority",
            "is_rest_candidate": False,
            "notes": "60+ min (an hour or more), outdoor if weather allows"
        },
        "saturday": {
            "name": "Saturday",
            "preferred_duration_min": 0,
            "min_duration_min": 0,
            "max_duration_min": 20,
            "mode": "rest_day",
            "is_rest_candidate": True,
            "is_default_rest": True,
            "notes": "Dedicated weekly rest / recovery day"
        },
        "sunday": {
            "name": "Sunday",
            "preferred_duration_min": 75,
            "min_duration_min": 60,
            "max_duration_min": 120,
            "mode": "outdoor_or_long_indoor",
            "is_rest_candidate": False,
            "notes": "Longer ride (60–90+ min), outdoor if weather allows, or long indoor"
        }
    },
    "warmup_cooldown": {
        "warmup_style": "wattage_ramp",
        "warmup_start_pct": 45,
        "warmup_end_pct": 75,
        "warmup_duration_min": 8,
        "cooldown_style": "wattage_ramp",
        "cooldown_start_pct": 65,
        "cooldown_end_pct": 40,
        "cooldown_duration_min": 5,
        "disallow_flat_z2_warmup": True
    },
    "interval_preferences": {
        "favorite_styles": ["Over/Unders", "Sweet Spot Over-Unders", "Threshold"],
        "disliked_styles": ["Fixed Flat Zone 2 Warmup", "Fixed Flat Cooldown"],
        "prefer_over_unders": True
    },
    "directives": [
        "Monday, Tuesday, Thursday: 35–45 minutes only.",
        "Wednesday & Friday: 60+ minutes (an hour or more), favor outdoor rides when weather permits.",
        "Saturday is a dedicated rest day; plus one of Mon/Tue/Thu as an additional rest day.",
        "Sunday: 60–90+ minutes (outdoor if weather permits, or longer indoor session).",
        "Warmups & Cooldowns: ALWAYS progressive wattage ramps (e.g. 45% -> 75% FTP ramp up, 65% -> 40% FTP ramp down); never flat steady Zone 2 blocks.",
        "Threshold & Sweet Spot: Strongly favor Over/Under blocks over continuous flat grinding."
    ]
}

def get_coaching_preferences() -> Dict[str, Any]:
    """Retrieves athlete coaching preferences from persistent SQLite storage with intelligent defaults."""
    stored = get_setting("coaching_preferences", None)
    if not stored or not isinstance(stored, dict):
        set_setting("coaching_preferences", DEFAULT_COACHING_PREFERENCES)
        return DEFAULT_COACHING_PREFERENCES

    # Ensure all required top-level keys exist
    merged = dict(DEFAULT_COACHING_PREFERENCES)
    for k, v in stored.items():
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged

def save_coaching_preferences(prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Persists updated coaching preferences into SQLite."""
    current = get_coaching_preferences()
    updated = {**current, **prefs}
    if "directives" in updated and isinstance(updated["directives"], list):
        updated["directives"] = [
            d.replace("//", "/").strip() for d in updated["directives"] if d and d.strip()
        ]
    set_setting("coaching_preferences", updated)
    return updated

def add_custom_directive(directive: str) -> List[str]:
    """Appends a new natural-language coaching directive."""
    prefs = get_coaching_preferences()
    directives = list(prefs.get("directives", []))
    cleaned = directive.replace("//", "/").strip()
    if cleaned and cleaned not in directives:
        directives.append(cleaned)
        prefs["directives"] = directives
        save_coaching_preferences(prefs)
    return directives

def remove_custom_directive(index: int) -> List[str]:
    """Removes a coaching directive by zero-based index."""
    prefs = get_coaching_preferences()
    directives = list(prefs.get("directives", []))
    if 0 <= index < len(directives):
        directives.pop(index)
        prefs["directives"] = directives
        save_coaching_preferences(prefs)
    return directives

def get_weekday_rest_quota_and_status(ref_date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Evaluates the athlete's forward directives regarding rest day quotas (e.g.
    'one of Mon/Tue/Wed/Thu should be a rest day') against actual logged workout telemetry
    for the current week (from Monday through Sunday prior).
    Determines if remaining candidate days (e.g. Thursday) are mandated to be rest/easy days.
    """
    import re
    today = ref_date or datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday_prior = monday - datetime.timedelta(days=1)

    prefs = get_coaching_preferences()
    directives = prefs.get("directives", [])

    # 1. Parse rest candidate days from directives (e.g. 'one of Mon/Tue/Wed/Thu as an additional rest day')
    pattern = re.compile(
        r"one of\s+([A-Za-z0-9/,\s&•]+?)\s+(?:as|should be|is|are|to be)\s+(?:an?\s+)?(?:additional\s+)?(?:extra\s+)?rest\s+day",
        re.IGNORECASE
    )
    candidate_days = []
    matched_directive = ""
    for d in directives:
        m = pattern.search(d)
        if m:
            raw = m.group(1).lower().replace("//", "/").replace("&", ",").replace("or", ",")
            for w in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                if w in raw or w[:3] in raw:
                    if w not in candidate_days:
                        candidate_days.append(w)
            if candidate_days:
                matched_directive = d.replace("//", "/")
                break

    if not candidate_days:
        candidate_days = ["monday", "tuesday", "thursday"]
        matched_directive = "Saturday is a dedicated rest day; plus one of Mon/Tue/Thu as an additional rest day."

    # 2. Query activities from Sunday prior through today
    from app.database import get_db_connection, get_setting, get_current_user_id
    strava_tokens = get_setting("strava_tokens", None)
    activities = []
    if strava_tokens:
        uid = get_current_user_id()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, name, start_date, moving_time_sec, suffer_score
            FROM strava_activities
            WHERE user_id = ? AND date(start_date) >= date(?)
            ORDER BY start_date ASC
        """, (uid, sunday_prior.isoformat()))
        activities = [dict(r) for r in c.fetchall()]
        conn.close()
    else:
        from app.services.mock_data import get_mock_strava_activities
        activities = get_mock_strava_activities()

    acts_by_date = {}
    for a in activities:
        d_str = a.get("start_date", "")[:10]
        if d_str:
            acts_by_date.setdefault(d_str, []).append(a)

    weekday_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    day_status = {}
    rest_days_taken_in_candidates = []
    worked_out_in_candidates = []

    for i, w_name in enumerate(weekday_keys):
        d_obj = monday + datetime.timedelta(days=i)
        d_str = d_obj.isoformat()

        has_workout = False
        day_acts = acts_by_date.get(d_str, [])
        if day_acts:
            has_workout = any(a.get("moving_time_sec", 0) >= 600 or a.get("suffer_score", 0) > 0 for a in day_acts)

        is_past_or_today = (d_obj <= today)
        day_status[w_name] = {
            "date": d_str,
            "has_workout": has_workout,
            "is_past_or_today": is_past_or_today,
            "is_candidate": (w_name in candidate_days),
            "activities": [a.get("name", "Ride") for a in day_acts]
        }

        if w_name in candidate_days and is_past_or_today:
            if has_workout:
                worked_out_in_candidates.append(w_name)
            else:
                if d_obj < today:
                    rest_days_taken_in_candidates.append(w_name)

    # Calculate consecutive workout streak leading into tomorrow
    consecutive_streak = 0
    check_day = today
    while True:
        c_str = check_day.isoformat()
        if c_str in acts_by_date and any(a.get("moving_time_sec", 0) >= 600 or a.get("suffer_score", 0) > 0 for a in acts_by_date[c_str]):
            consecutive_streak += 1
            check_day = check_day - datetime.timedelta(days=1)
        else:
            break

    # Sunday prior check
    sun_str = sunday_prior.isoformat()
    had_sunday_prior = (sun_str in acts_by_date and any(a.get("moving_time_sec", 0) >= 600 or a.get("suffer_score", 0) > 0 for a in acts_by_date[sun_str]))

    # Remaining candidate days in current week:
    # A candidate day is still open/pending if it is in the future (> today),
    # or if it is today and the athlete has not logged a workout yet today.
    remaining_candidates = [
        w for w in candidate_days
        if (monday + datetime.timedelta(days=weekday_keys.index(w))) > today
        or ((monday + datetime.timedelta(days=weekday_keys.index(w))) == today and not day_status.get(w, {}).get("has_workout", False))
    ]

    must_rest_days = []
    if len(rest_days_taken_in_candidates) == 0:
        if len(remaining_candidates) == 1:
            must_rest_days = list(remaining_candidates)

    completed_streak_text = (
        f"{', '.join([w.capitalize() for w in worked_out_in_candidates])}"
        f"{' (and prior Sunday, ' + str(consecutive_streak) + '-day streak)' if had_sunday_prior else f' ({consecutive_streak}-day streak)'}"
    )

    rationale = (
        f"Per your forward directive ('{matched_directive}') and having completed workouts on {completed_streak_text}, "
        f"{', '.join([d.capitalize() for d in must_rest_days])} is designated as a rest day or easy day to maintain weekly balance."
        if must_rest_days else ""
    )

    return {
        "matched_directive": matched_directive,
        "candidate_days": candidate_days,
        "worked_out_in_candidates": worked_out_in_candidates,
        "rest_days_taken_in_candidates": rest_days_taken_in_candidates,
        "remaining_candidates": remaining_candidates,
        "consecutive_streak": consecutive_streak,
        "had_sunday_prior": had_sunday_prior,
        "completed_streak_text": completed_streak_text,
        "must_rest_days": must_rest_days,
        "is_thursday_mandated_rest": ("thursday" in must_rest_days),
        "rationale": rationale,
        "day_status": day_status
    }

def get_day_target_config(target_date: Optional[datetime.date] = None, ref_date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Returns the target duration range, mode (indoor vs outdoor), and physiological focus
    for a given date based on the athlete's weekly scheduling preferences.
    """
    d = target_date or datetime.date.today()
    weekday_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    w_key = weekday_keys[d.weekday()]

    prefs = get_coaching_preferences()
    sched = prefs.get("weekly_schedule", {}).get(w_key, DEFAULT_COACHING_PREFERENCES["weekly_schedule"][w_key])
    wc = prefs.get("warmup_cooldown", DEFAULT_COACHING_PREFERENCES["warmup_cooldown"])
    intervals = prefs.get("interval_preferences", DEFAULT_COACHING_PREFERENCES["interval_preferences"])

    # Check weekly rest directive quota from the perspective of today's completed workouts
    eval_date = ref_date or (d if d <= datetime.date.today() else datetime.date.today())
    status = get_weekday_rest_quota_and_status(ref_date=eval_date)
    is_directive_rest = (w_key in status.get("must_rest_days", []))

    if is_directive_rest:
        return {
            "date": d.isoformat(),
            "weekday_key": w_key,
            "day_name": sched.get("name", w_key.capitalize()),
            "preferred_duration_min": 0,
            "min_duration_min": 0,
            "max_duration_min": 30,
            "mode": "rest_or_easy_spin",
            "is_rest_candidate": True,
            "is_default_rest": True,
            "is_directive_rest": True,
            "notes": status.get("rationale") or f"Directive Rest Day: {sched.get('name', w_key.capitalize())} is the required rest day per your weekly directive.",
            "warmup_cooldown": wc,
            "interval_preferences": intervals,
            "directives": prefs.get("directives", [])
        }

    return {
        "date": d.isoformat(),
        "weekday_key": w_key,
        "day_name": sched.get("name", w_key.capitalize()),
        "preferred_duration_min": sched.get("preferred_duration_min", 45),
        "min_duration_min": sched.get("min_duration_min", 35),
        "max_duration_min": sched.get("max_duration_min", 45),
        "mode": sched.get("mode", "indoor_priority"),
        "is_rest_candidate": sched.get("is_rest_candidate", False),
        "is_default_rest": sched.get("is_default_rest", False),
        "is_directive_rest": False,
        "notes": sched.get("notes", ""),
        "warmup_cooldown": wc,
        "interval_preferences": intervals,
        "directives": prefs.get("directives", [])
    }

def extract_and_learn_preferences_from_text(user_message: str) -> Optional[str]:
    """
    Detects if the user is giving a permanent coaching preference or directive in chat,
    and automatically persists it into the SQLite preferences engine.
    """
    msg = user_message.strip()
    msg_lower = msg.lower()

    learning_triggers = [
        "remember that i prefer",
        "remember that i like",
        "remember that i want",
        "remember that i hate",
        "save my preference",
        "save this preference",
        "from now on",
        "my preference is",
        "always remember",
        "note that i prefer"
    ]

    has_trigger = any(t in msg_lower for t in learning_triggers)
    if not has_trigger:
        return None

    # Clean the trigger phrase to form a concise directive
    cleaned_directive = msg
    for trig in learning_triggers:
        if trig in msg_lower:
            idx = msg_lower.find(trig)
            extracted = msg[idx + len(trig):].strip(" :,.-")
            if len(extracted) > 10:
                cleaned_directive = extracted[0].upper() + extracted[1:]
                break

    add_custom_directive(cleaned_directive)
    return cleaned_directive

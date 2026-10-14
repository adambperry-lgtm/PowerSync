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
    set_setting("coaching_preferences", updated)
    return updated

def add_custom_directive(directive: str) -> List[str]:
    """Appends a new natural-language coaching directive."""
    prefs = get_coaching_preferences()
    directives = list(prefs.get("directives", []))
    cleaned = directive.strip()
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

def get_day_target_config(target_date: Optional[datetime.date] = None) -> Dict[str, Any]:
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

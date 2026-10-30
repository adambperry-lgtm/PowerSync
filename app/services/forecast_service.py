"""
Forecast Integration Service
Bridges the 3-day physiological forward outlook with the daily workout selector and AI Coach.
Guarantees that when forecasted recovery and fatigue decay assumptions hold true,
the workout selector honors and prescribes the exact forecasted workout.
"""

import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.database import get_setting, set_setting, get_current_user_id, get_athlete_date

def save_coach_forecast_plan(user_id: Optional[str], outlook_days: List[Dict[str, Any]]) -> None:
    """
    Persists the 3-day forward forecast plan into SQLite storage.
    Keyed by ISO date string (YYYY-MM-DD) for fast retrieval by the workout generator.
    """
    uid = user_id or get_current_user_id()
    current_plan = get_setting("coach_forecast_plan", {}, user_id=uid)
    if not isinstance(current_plan, dict):
        current_plan = {}

    for item in outlook_days:
        date_iso = item.get("date_iso")
        if not date_iso and item.get("target_date"):
            date_iso = item["target_date"].isoformat() if hasattr(item["target_date"], "isoformat") else str(item["target_date"])[:10]
        if not date_iso:
            continue

        current_plan[date_iso] = {
            "date": date_iso,
            "day_offset": item.get("day_offset", 1),
            "title": item.get("title", ""),
            "duration_min": item.get("duration_min", 45),
            "estimated_tss": item.get("estimated_tss", 50),
            "estimated_xss": item.get("estimated_xss", 50),
            "projected_recovery": item.get("projected_recovery", 70),
            "projected_zone": item.get("projected_zone", "green"),
            "focus_area": item.get("focus", item.get("focus_area", "Structured Training")),
            "focus_duration": item.get("focus_duration", ""),
            "intervals": item.get("intervals", []),
            "ai_rationale": item.get("ai_rationale", item.get("description", "")),
            "description": item.get("description", ""),
            "is_directive_rest": item.get("is_directive_rest", False),
            "is_default_rest": item.get("is_default_rest", False),
            "updated_at": datetime.datetime.now().isoformat()
        }

    # Prune historical dates older than 30 days (while keeping newly saved outlook dates)
    today = get_athlete_date()
    cutoff_iso = (today - datetime.timedelta(days=30)).isoformat()
    newly_saved_dates = {item.get("date_iso") or str(item.get("target_date", ""))[:10] for item in outlook_days}
    pruned_plan = {k: v for k, v in current_plan.items() if k >= cutoff_iso or k in newly_saved_dates}

    set_setting("coach_forecast_plan", pruned_plan, user_id=uid)

def get_forecast_for_date(date_str: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the stored forecast for a specific date (YYYY-MM-DD)."""
    uid = user_id or get_current_user_id()
    plan = get_setting("coach_forecast_plan", {}, user_id=uid)
    if isinstance(plan, dict):
        return plan.get(date_str)
    return None

def is_forecast_valid_for_recovery(forecast: Dict[str, Any], actual_recovery: int) -> Tuple[bool, str]:
    """
    Evaluates whether the athlete's actual morning Whoop recovery aligns
    with the physiological assumptions of the forward forecast.
    """
    projected_recovery = int(forecast.get("projected_recovery", 70))
    actual_zone = "green" if actual_recovery > 66 else ("yellow" if actual_recovery >= 34 else "red")
    projected_zone = str(forecast.get("projected_zone") or ("green" if projected_recovery > 66 else ("yellow" if projected_recovery >= 34 else "red"))).lower()

    # 1. Exact zone match
    if actual_zone == projected_zone:
        return True, f"Both in {actual_zone.upper()} zone"

    # 2. Borderline score within tolerance (e.g. 64% vs 68%)
    if abs(actual_recovery - projected_recovery) <= 8:
        return True, f"Recovery within tolerance ({actual_recovery}% actual vs {projected_recovery}% projected)"

    return False, f"Recovery shifted from {projected_zone.upper()} ({projected_recovery}%) to {actual_zone.upper()} ({actual_recovery}%)"

def save_athlete_planned_session(date_iso: str, plan_data: Dict[str, Any], user_id: Optional[str] = None) -> None:
    """
    Saves an athlete's upcoming planned session (communicated via Coach Chat or target plans)
    keyed by date_iso (YYYY-MM-DD) in athlete settings.
    """
    uid = user_id or get_current_user_id()
    plans = get_setting("coach_upcoming_plans", {}, user_id=uid)
    if not isinstance(plans, dict):
        plans = {}

    title_str = str(plan_data.get("title") or "Planned Session").strip()
    is_rest = bool(
        plan_data.get("is_rest") or
        any(k in title_str.lower() for k in ["rest", "day off", "off day", "skip", "take off", "no ride"])
    )
    dur = 0 if is_rest else int(plan_data.get("duration_minutes") or plan_data.get("duration_min") or plan_data.get("estimated_duration_min") or 45)
    tss = 0 if is_rest else int(plan_data.get("estimated_tss") or 50)
    xss = 0 if is_rest else int(plan_data.get("estimated_xss") or tss)

    plans[date_iso] = {
        "date_iso": date_iso,
        "title": "Rest & Recovery" if is_rest else title_str,
        "duration_min": dur,
        "estimated_tss": tss,
        "estimated_xss": xss,
        "focus_area": "Rest & Recovery" if is_rest else (plan_data.get("focus_area") or plan_data.get("intensity_type") or "Structured Training"),
        "focus_duration": "Rest & Recovery" if is_rest else (plan_data.get("focus_duration") or "Coach Chat Plan"),
        "description": plan_data.get("description") or f"Planned in Coach Chat for {date_iso}",
        "intervals": [] if is_rest else (plan_data.get("intervals") or []),
        "distance_miles": 0.0 if is_rest else float(plan_data.get("distance_miles") or 0.0),
        "elevation_gain_ft": 0.0 if is_rest else float(plan_data.get("elevation_gain_ft") or 0.0),
        "is_rest": is_rest,
        "updated_at": datetime.datetime.now().isoformat()
    }
    set_setting("coach_upcoming_plans", plans, user_id=uid)
    if uid == "usr_guest":
        set_setting("coach_upcoming_plans", plans, user_id="usr_default")
    elif uid == "usr_default":
        set_setting("coach_upcoming_plans", plans, user_id="usr_guest")

def get_athlete_planned_sessions(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves all upcoming sessions planned via Coach Chat or target planning."""
    uid = user_id or get_current_user_id()
    plans = get_setting("coach_upcoming_plans", {}, user_id=uid)
    if (not plans or not isinstance(plans, dict)) and uid == "usr_guest":
        plans = get_setting("coach_upcoming_plans", {}, user_id="usr_default")
    return plans if isinstance(plans, dict) else {}

def clear_athlete_planned_session(date_iso: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """Clears a planned session for a specific date, or all plans if date_iso is None."""
    uid = user_id or get_current_user_id()
    if not date_iso:
        set_setting("coach_upcoming_plans", {}, user_id=uid)
        if uid == "usr_guest":
            set_setting("coach_upcoming_plans", {}, user_id="usr_default")
        elif uid == "usr_default":
            set_setting("coach_upcoming_plans", {}, user_id="usr_guest")
        return
    plans = get_athlete_planned_sessions(user_id=uid)
    if isinstance(plans, dict) and date_iso in plans:
        del plans[date_iso]
        set_setting("coach_upcoming_plans", plans, user_id=uid)
        if uid == "usr_guest":
            set_setting("coach_upcoming_plans", plans, user_id="usr_default")
        elif uid == "usr_default":
            set_setting("coach_upcoming_plans", plans, user_id="usr_guest")

def parse_chat_schedule_directives(message: str, today: Optional[datetime.date] = None, ftp: int = 250) -> List[Dict[str, Any]]:
    """
    Intelligently extracts multi-day upcoming workout plans and rest directives
    stated by the athlete in Coach Chat (e.g. '50 miles tomorrow and resting sunday',
    'Saturday 50 miles, Sunday off', 'taking tomorrow off and 40 miles Sunday').
    Returns structured list of plan dictionaries ready to persist to coach_upcoming_plans.
    """
    if not message or not message.strip():
        return []

    import re
    if not today:
        today = get_athlete_date()

    lower = message.strip().lower()

    # Strip complaint / bug report tails like 'but it still has rest tomorrow...'
    complaint_match = re.search(r'\b(?:but\s+(?:it\s+still|it\s+shows|it\s+has)|why\s+does\s+it|it\s+still\s+shows|it\s+still\s+has)\b.*$', lower, re.IGNORECASE)
    working_text = lower[:complaint_match.start()].strip() if complaint_match else lower

    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }

    # Split into clauses by common conjunctions or punctuation
    parts = re.split(r'[,;]|\band\b|\bthen\b|\bbut\b', working_text)
    assigned_dates = {}

    for part in parts:
        part_str = part.strip()
        if not part_str:
            continue

        target_date = None
        day_label = ""

        # Check relative days
        if "tomorrow" in part_str or "tmrw" in part_str:
            target_date = today + datetime.timedelta(days=1)
            day_label = "Tomorrow"
        elif "day after tomorrow" in part_str:
            target_date = today + datetime.timedelta(days=2)
            day_label = "Day After Tomorrow"
        elif "today" in part_str:
            target_date = today
            day_label = "Today"
        else:
            # Check weekday names
            for w_name, w_idx in weekdays.items():
                if re.search(rf'\b{w_name}\b', part_str):
                    days_ahead = (w_idx - today.weekday()) % 7
                    if days_ahead == 0 and ("next" in part_str or w_idx != today.weekday()):
                        days_ahead = 7
                    target_date = today + datetime.timedelta(days=days_ahead)
                    day_label = w_name.capitalize()
                    break

        if not target_date:
            continue

        date_iso = target_date.isoformat()
        weekday_name = target_date.strftime("%A")

        # Check for rest intent
        is_rest = any(k in part_str for k in ["rest", "resting", "off", "day off", "take off", "skip", "no ride", "passive"])
        dist_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–—]?\s*(?:miles|mile|mi)\b', part_str)
        dur_match = re.search(r'\b(20|25|30|35|40|45|50|60|75|90|120|150|180)\s*(?:m|min|mins|minutes)?\b', part_str)

        if is_rest and not dist_match:
            assigned_dates[date_iso] = {
                "date_iso": date_iso,
                "target_date": date_iso,
                "title": "Rest & Recovery",
                "duration_min": 0,
                "duration_minutes": 0,
                "estimated_tss": 0,
                "estimated_xss": 0,
                "focus_area": "Rest & Recovery",
                "focus_duration": "Rest & Recovery",
                "is_rest": True,
                "description": f"Scheduled rest day for {day_label or weekday_name}."
            }
        elif dist_match:
            dist = float(dist_match.group(1))
            dur = max(60, min(360, int((dist / 17.5) * 60)))
            tss = max(40, int(dist * 2.1))
            assigned_dates[date_iso] = {
                "date_iso": date_iso,
                "target_date": date_iso,
                "title": f"{int(dist)}-Mile {weekday_name} Ride",
                "duration_min": dur,
                "duration_minutes": dur,
                "distance_miles": dist,
                "elevation_gain_ft": round(dist * 50),
                "estimated_tss": tss,
                "estimated_xss": tss,
                "focus_area": "Endurance",
                "focus_duration": "Endurance / Century (>1h Focus)",
                "is_rest": False,
                "description": f"Planned {int(dist)}-mile {weekday_name} endurance ride (~{dur}m, ~{tss} TSS)."
            }
        elif dur_match or any(k in part_str for k in ["interval", "sweet spot", "threshold", "tempo", "vo2", "over-under", "spin", "ride"]):
            dur = int(dur_match.group(1)) if dur_match else 45
            focus = "Sweet Spot" if "sweet spot" in part_str else ("Threshold" if "threshold" in part_str or "over" in part_str else "Aerobic Base")
            assigned_dates[date_iso] = {
                "date_iso": date_iso,
                "target_date": date_iso,
                "title": f"{dur}-Min {focus} Session",
                "duration_min": dur,
                "duration_minutes": dur,
                "distance_miles": 0.0,
                "elevation_gain_ft": 0.0,
                "estimated_tss": round(dur * 1.1),
                "estimated_xss": round(dur * 1.1),
                "focus_area": focus,
                "focus_duration": f"{focus} Focus",
                "is_rest": False,
                "description": f"Planned {dur}-minute {focus} session for {weekday_name}."
            }

    return list(assigned_dates.values())


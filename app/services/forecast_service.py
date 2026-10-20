"""
Forecast Integration Service
Bridges the 3-day physiological forward outlook with the daily workout selector and AI Coach.
Guarantees that when forecasted recovery and fatigue decay assumptions hold true,
the workout selector honors and prescribes the exact forecasted workout.
"""

import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.database import get_setting, set_setting, get_current_user_id

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

    # Prune past dates older than 7 days
    today = datetime.date.today()
    cutoff_iso = (today - datetime.timedelta(days=7)).isoformat()
    pruned_plan = {k: v for k, v in current_plan.items() if k >= cutoff_iso}

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

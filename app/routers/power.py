from fastapi import APIRouter, Query, Body, HTTPException
from typing import Optional, Dict, Any
from app.services.power_profile_service import (
    get_power_spiderweb_profile,
    calculate_spiderweb_target_changes,
    get_active_spiderweb_goal,
    set_active_spiderweb_goal,
    clear_active_spiderweb_goal
)
from app.database import get_current_user_id

router = APIRouter(prefix="/api/power", tags=["power"])

@router.get("/spiderweb")
def get_spiderweb_endpoint(timeframe: Optional[str] = Query("30d")):
    """
    Returns the athlete's multi-axis Power Spiderweb Profile (Radar chart),
    comparing the selected timeframe against previous baseline periods,
    including the active training goal polygon and historical progress over time.
    """
    uid = get_current_user_id()
    return get_power_spiderweb_profile(user_id=uid, timeframe=timeframe or "30d")

@router.get("/spiderweb/target-analysis")
def get_spiderweb_target_analysis_endpoint(timeframe: Optional[str] = Query("30d")):
    """
    Computes required target changes, wattage progressions, and training stimulus
    for improving individual duration categories (5s, 1m, 5m, 20m, 60m)
    or transforming athlete phenotype into targeted rider types.
    """
    uid = get_current_user_id()
    return calculate_spiderweb_target_changes(user_id=uid, timeframe=timeframe or "30d")

@router.get("/spiderweb/goal")
def get_spiderweb_goal_endpoint():
    """Returns the athlete's active spiderweb training goal and current progress."""
    uid = get_current_user_id()
    goal = get_active_spiderweb_goal(user_id=uid)
    return {"has_active_goal": bool(goal), "goal": goal}

@router.post("/spiderweb/goal")
def set_spiderweb_goal_endpoint(payload: Dict[str, Any] = Body(...)):
    """
    Sets the athlete's active training goal based on a specific duration achievement
    (e.g. 20m Threshold 260W) or a rider type transformation (e.g. Puncheur),
    and synchronizes the Long-Term Fitness Goal & Program (Xert Alternative).
    """
    uid = get_current_user_id()
    if not payload:
        raise HTTPException(status_code=400, detail="Missing goal payload")
    goal = set_active_spiderweb_goal(payload=payload, user_id=uid)
    profile = get_power_spiderweb_profile(user_id=uid, timeframe="30d")
    from app.services.program_service import get_current_program
    program = get_current_program()
    return {
        "success": True,
        "goal": goal,
        "profile": profile,
        "program": program,
        "message": f"Active training goal updated to: {goal.get('target_title')}"
    }

@router.delete("/spiderweb/goal")
def delete_spiderweb_goal_endpoint():
    """Clears the athlete's active spiderweb training goal."""
    uid = get_current_user_id()
    clear_active_spiderweb_goal(user_id=uid)
    profile = get_power_spiderweb_profile(user_id=uid, timeframe="30d")
    from app.services.program_service import get_current_program
    program = get_current_program()
    return {
        "success": True,
        "profile": profile,
        "program": program,
        "message": "Active spiderweb training goal cleared"
    }

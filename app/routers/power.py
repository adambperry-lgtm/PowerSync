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
    if uid == "usr_guest":
        return {
            "success": True,
            "is_guest": True,
            "timeframe": timeframe or "30d",
            "categories": [],
            "baseline_categories": [],
            "active_goal": None
        }
    return get_power_spiderweb_profile(user_id=uid, timeframe=timeframe or "30d")

@router.get("/spiderweb/target-analysis")
def get_spiderweb_target_analysis_endpoint(timeframe: Optional[str] = Query("30d")):
    """
    Computes required target changes, wattage progressions, and training stimulus
    for improving individual duration categories (5s, 1m, 5m, 20m, 60m)
    or transforming athlete phenotype into targeted rider types.
    """
    uid = get_current_user_id()
    if uid == "usr_guest":
        return {"success": True, "is_guest": True, "target_changes": []}
    return calculate_spiderweb_target_changes(user_id=uid, timeframe=timeframe or "30d")

@router.get("/spiderweb/goal")
def get_spiderweb_goal_endpoint(timeframe: Optional[str] = Query("30d")):
    """Returns the athlete's active spiderweb training goal and current progress."""
    uid = get_current_user_id()
    if uid == "usr_guest":
        return {"has_active_goal": False, "goal": None}
    profile = get_power_spiderweb_profile(user_id=uid, timeframe=timeframe or "30d")
    goal = profile.get("active_goal")
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
    program = get_current_program(user_id=uid)
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
    program = get_current_program(user_id=uid)
    return {
        "success": True,
        "profile": profile,
        "program": program,
        "message": "Active spiderweb training goal cleared"
    }

@router.post("/program/reset-block")
def reset_program_block_endpoint(payload: Optional[Dict[str, Any]] = None):
    """
    Resets the athlete's periodization macrocycle block to Week 1 starting today.
    """
    uid = get_current_user_id()
    block_weeks = int((payload or {}).get("block_weeks", 8))
    from app.services.program_service import reset_program_block
    program = reset_program_block(user_id=uid, block_weeks=block_weeks)
    profile = get_power_spiderweb_profile(user_id=uid, timeframe="30d")
    return {
        "success": True,
        "program": program,
        "profile": profile,
        "message": f"Macrocycle block reset to Week 1 (Base Phase, {block_weeks} weeks)."
    }


@router.get("/ftp-test-readiness")
def get_ftp_test_readiness_endpoint():
    """
    Analyzes training progress, FTP staleness, eFTP breakthroughs, Whoop readiness,
    and acute fatigue clearance to recommend when and how to perform an FTP test.
    """
    uid = get_current_user_id()
    if uid == "usr_guest":
        return {"success": True, "is_guest": True, "readiness": None}
    from app.services.ftp_test_service import evaluate_ftp_test_readiness
    readiness = evaluate_ftp_test_readiness(user_id=uid)
    return {"success": True, "readiness": readiness}


@router.post("/ftp-test-record")
def record_ftp_test_endpoint(payload: Dict[str, Any] = Body(...)):
    """
    Records a completed FTP test result, updates athlete_ftp and ftp_last_tested_date,
    and returns refreshed FTP test readiness and program state.
    """
    uid = get_current_user_id()
    if uid == "usr_guest":
        raise HTTPException(status_code=401, detail="Authentication required")
    if not payload or payload.get("new_ftp") is None:
        raise HTTPException(status_code=400, detail="new_ftp is required")
    try:
        new_ftp = int(payload["new_ftp"])
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="new_ftp must be an integer")
    if new_ftp < 80 or new_ftp > 600:
        raise HTTPException(status_code=400, detail="new_ftp must be between 80 and 600 watts")

    from app.services.ftp_test_service import record_ftp_test_result, evaluate_ftp_test_readiness
    from app.services.program_service import get_current_program
    result = record_ftp_test_result(
        new_ftp=new_ftp,
        protocol=str(payload.get("protocol") or "20m_coggan"),
        test_date=payload.get("test_date"),
        user_id=uid,
    )
    readiness = evaluate_ftp_test_readiness(user_id=uid)
    program = get_current_program(user_id=uid)
    return {
        "success": True,
        "result": result,
        "readiness": readiness,
        "program": program,
    }



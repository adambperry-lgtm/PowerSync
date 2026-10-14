from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import datetime

from app.database import (
    save_target_plan as db_save_target_plan,
    get_active_target_plan as db_get_active_target_plan,
    get_all_target_plans as db_get_all_target_plans,
    delete_target_plan as db_delete_target_plan,
    clear_active_target_plans as db_clear_active_target_plans,
    get_setting
)
from app.services.plan_service import (
    parse_plan_description,
    parse_gpx_content,
    get_strava_route_candidates,
    compute_taper_leadup_schedule
)

router = APIRouter(prefix="/api/plans", tags=["plans"])

class TargetPlanRequest(BaseModel):
    id: Optional[str] = None
    title: str
    target_date: str
    description: Optional[str] = ""
    distance_miles: Optional[float] = 0.0
    elevation_gain_ft: Optional[float] = 0.0
    estimated_duration_min: Optional[int] = 0
    estimated_tss: Optional[int] = 0
    intensity_type: Optional[str] = "Endurance"
    route_source: Optional[str] = "manual"
    strava_id: Optional[str] = ""
    summary_polyline: Optional[str] = ""
    svg_path: Optional[str] = ""
    is_active: Optional[int] = 1

class ParseDescriptionRequest(BaseModel):
    text: str
    default_date: Optional[str] = None

class UploadGpxPayload(BaseModel):
    gpx_content: str
    filename: Optional[str] = "Uploaded Route.gpx"

class ClearPlanRequest(BaseModel):
    plan_id: Optional[str] = None

@router.get("/active")
def get_active_plan():
    """Returns current active upcoming target plan and lead-up taper roadmap."""
    plan = db_get_active_target_plan()
    if not plan:
        return {"has_active_plan": False, "plan": None, "schedule": []}
        
    ftp = int(get_setting("athlete_ftp", 250))
    schedule = compute_taper_leadup_schedule(plan, current_ftp=ftp)
    
    return {
        "has_active_plan": True,
        "plan": plan,
        "schedule": schedule
    }

@router.post("")
def save_plan(req: TargetPlanRequest):
    """Saves or updates an upcoming target plan and activates schedule adaptation."""
    plan_dict = req.dict()
    # Calculate estimated duration and TSS if missing
    dist = float(plan_dict.get("distance_miles") or 0.0)
    if dist > 0 and not plan_dict.get("estimated_duration_min"):
        plan_dict["estimated_duration_min"] = max(30, round(dist / 17.0 * 60))
    if not plan_dict.get("estimated_tss") and plan_dict.get("estimated_duration_min"):
        plan_dict["estimated_tss"] = max(20, round(plan_dict["estimated_duration_min"] * 0.60))

    plan_id = db_save_target_plan(plan_dict)
    active = db_get_active_target_plan()
    ftp = int(get_setting("athlete_ftp", 250))
    schedule = compute_taper_leadup_schedule(active, current_ftp=ftp) if active else []

    return {
        "success": True,
        "message": f"Upcoming target plan '{plan_dict.get('title')}' activated! Training schedule adjusted.",
        "plan": active,
        "schedule": schedule
    }

@router.post("/parse-description")
def parse_description(req: ParseDescriptionRequest):
    """
    Parses unstructured text like 'a 50 mile ride on Sunday'
    and returns structured target plan attributes.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Description text is required.")
    
    parsed = parse_plan_description(req.text, default_date=req.default_date)
    return parsed

@router.get("/strava-candidates")
def get_strava_candidates():
    """Returns candidate routes from synced Strava activities and mock data."""
    candidates = get_strava_route_candidates()
    return {
        "success": True,
        "candidates": candidates
    }

@router.post("/upload-gpx")
def upload_gpx(payload: UploadGpxPayload):
    """Parses an uploaded .gpx route file and extracts distance, elevation, and SVG path."""
    parsed = parse_gpx_content(payload.gpx_content, filename=payload.filename or "Uploaded Route")
    if not parsed.get("success"):
        raise HTTPException(status_code=400, detail=parsed.get("error", "Failed to parse GPX"))
    return parsed

@router.post("/clear")
def clear_active_plan(req: Optional[ClearPlanRequest] = None):
    """Deactivates active target plans and returns default training progression."""
    db_clear_active_target_plans()
    return {
        "success": True,
        "message": "Upcoming target plan cleared. Training schedule reverted to standard progression."
    }

@router.delete("/{plan_id}")
def delete_plan(plan_id: str):
    """Deletes a target plan by ID."""
    deleted = db_delete_target_plan(plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Target plan not found.")
    return {
        "success": True,
        "message": f"Target plan {plan_id} deleted."
    }

@router.get("/history")
def get_plan_history():
    """Returns all past and upcoming target plans."""
    plans = db_get_all_target_plans()
    return {
        "plans": plans
    }

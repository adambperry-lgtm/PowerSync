from fastapi import APIRouter, Query
from typing import Optional, Dict, Any
from app.services.power_profile_service import get_power_spiderweb_profile
from app.database import get_current_user_id

router = APIRouter(prefix="/api/power", tags=["power"])

@router.get("/spiderweb")
def get_spiderweb_endpoint(timeframe: Optional[str] = Query("30d")):
    """
    Returns the athlete's multi-axis Power Spiderweb Profile (Radar chart),
    comparing the selected timeframe against previous baseline periods and
    tracking historical progress over time (Strava and Xert model).
    """
    uid = get_current_user_id()
    return get_power_spiderweb_profile(user_id=uid, timeframe=timeframe or "30d")

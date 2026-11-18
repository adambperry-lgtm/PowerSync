from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.database import get_current_user_id
from app.services.ride_history_service import (
    get_ride_history_analytics,
    get_single_ride_detail,
)

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/analytics")
def get_history_analytics_endpoint(
    range: Optional[str] = Query("90d"),
    env: Optional[str] = Query("all"),
):
    """
    Returns historical ride analytics for the Ride History tab:
    KPIs, volume breakdown, geographic heatmap polylines, CTL/ATL/TSB PMC curve,
    Recovery x Performance correlation matrix, MMP power curve, Year in Sport recap,
    and searchable ride log.
    """
    uid = get_current_user_id()
    return get_ride_history_analytics(
        user_id=uid,
        range_key=range or "90d",
        env_filter=env or "all",
    )


@router.get("/ride/{ride_id}")
def get_single_ride_detail_endpoint(ride_id: str):
    """Returns detailed telemetry, Whoop morning context, 3-tier strain, and similar rides."""
    uid = get_current_user_id()
    detail = get_single_ride_detail(ride_id=ride_id, user_id=uid)
    if not detail:
        raise HTTPException(status_code=404, detail="Ride not found")
    return detail

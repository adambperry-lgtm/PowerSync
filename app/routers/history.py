from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.database import get_current_user_id
from app.services.ride_history_service import (
    get_ride_history_analytics,
    get_single_ride_detail,
)
from app.services.strava_service import fetch_recent_strava_activities
from app.services.whoop_service import fetch_latest_whoop_metrics

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/analytics")
def get_history_analytics_endpoint(
    range: Optional[str] = Query("90d"),
    env: Optional[str] = Query("all"),
    sync: bool = Query(False),
):
    """
    Returns historical ride analytics for the Ride History tab.
    When sync=true, incrementally fetches newer Strava activities and Whoop
    recovery metrics before computing the updated analytics payload.
    """
    uid = get_current_user_id()
    synced_new = False
    if sync and uid and uid != "usr_guest":
        try:
            fetch_recent_strava_activities(limit=30, user_id=uid)
            synced_new = True
        except Exception as e:
            print(f"Incremental Strava sync skipped during history refresh: {e}")
        try:
            fetch_latest_whoop_metrics(user_id=uid)
            synced_new = True
        except Exception as e:
            print(f"Incremental Whoop sync skipped during history refresh: {e}")

    res = get_ride_history_analytics(
        user_id=uid,
        range_key=range or "90d",
        env_filter=env or "all",
    )
    res["synced_incremental"] = synced_new
    return res


@router.get("/ride/{ride_id}")
def get_single_ride_detail_endpoint(ride_id: str):
    """Returns detailed telemetry, Whoop morning context, 3-tier strain, and similar rides."""
    uid = get_current_user_id()
    detail = get_single_ride_detail(ride_id=ride_id, user_id=uid)
    if not detail:
        raise HTTPException(status_code=404, detail="Ride not found")
    return detail

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.database import get_current_user_id
from app.services.review_coach import generate_ai_review_and_outlook
from app.services.forecast_backtest_service import run_recovery_forecast_backtest

router = APIRouter(prefix="/api/review", tags=["review"])

class RegenerateReviewRequest(BaseModel):
    user_note: Optional[str] = ""

@router.get("/daily-debrief")
def get_daily_debrief():
    """Returns today's workout review + 3-day forward outlook."""
    uid = get_current_user_id()
    if uid == "usr_guest":
        return {
            "success": True,
            "headline": "Sign in to view your daily debrief & coaching outlook",
            "coach_notes": "Your training review and personalized forecast are private and only viewable when signed in.",
            "today_review": None,
            "forward_outlook": []
        }
    return generate_ai_review_and_outlook()

@router.post("/regenerate")
def regenerate_daily_debrief(req: RegenerateReviewRequest):
    """Regenerates debrief with optional custom athlete note."""
    uid = get_current_user_id()
    if uid == "usr_guest":
        return {
            "success": True,
            "headline": "Sign in to view your daily debrief & coaching outlook",
            "coach_notes": "Your training review and personalized forecast are private and only viewable when signed in.",
            "today_review": None,
            "forward_outlook": []
        }
    return generate_ai_review_and_outlook(custom_prompt=req.user_note or "", force_refresh=True)

@router.get("/forecast-accuracy")
def get_forecast_accuracy_backtest(
    days: int = Query(default=90, ge=7, le=365),
    sync_whoop: bool = Query(default=False),
) -> Dict[str, Any]:
    """
    Runs a walk-forward historical backtest of the 3-day WHOOP recovery heuristic
    against the signed-in athlete's stored WHOOP and Strava history.
    """
    uid = get_current_user_id()
    if uid == "usr_guest":
        return {
            "success": True,
            "requires_auth": True,
            "message": "Sign in to run a personal WHOOP forecast accuracy backtest.",
            "data_coverage": {
                "whoop_days_in_window": 0,
                "origin_days_evaluated": 0,
                "day_1_pairs": 0,
                "total_prediction_pairs": 0,
                "sufficient_data": False,
            },
            "insights": [],
            "timeline": [],
        }

    sync_meta = None
    if sync_whoop:
        from app.services.whoop_service import backfill_whoop_history
        sync_meta = backfill_whoop_history(days=min(180, days), user_id=uid)

    result = run_recovery_forecast_backtest(user_id=uid, days=days)
    if sync_meta is not None:
        result["whoop_sync"] = sync_meta
    return result


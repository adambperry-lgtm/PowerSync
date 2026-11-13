from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.database import get_current_user_id
from app.services.review_coach import generate_ai_review_and_outlook

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
    return generate_ai_review_and_outlook(custom_prompt=req.user_note or "")

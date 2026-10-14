from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.review_coach import generate_ai_review_and_outlook

router = APIRouter(prefix="/api/review", tags=["review"])

class RegenerateReviewRequest(BaseModel):
    user_note: Optional[str] = ""

@router.get("/daily-debrief")
def get_daily_debrief():
    """Returns today's workout review + 3-day forward outlook."""
    return generate_ai_review_and_outlook()

@router.post("/regenerate")
def regenerate_daily_debrief(req: RegenerateReviewRequest):
    """Regenerates debrief with optional custom athlete note."""
    return generate_ai_review_and_outlook(custom_prompt=req.user_note or "")

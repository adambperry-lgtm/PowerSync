from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel
from typing import Any, Dict, Optional
from app.database import get_current_user_id, set_setting, GUEST_USER_ID
from app.routers.settings import require_authenticated_user
from app.routers.auth import get_app_base_url
from app.services.apple_health_service import (
    get_or_create_apple_health_token,
    resolve_user_by_apple_health_token,
    ingest_apple_health_payload,
    get_apple_health_summary,
)

router = APIRouter(prefix="/api/apple-health", tags=["apple-health"])


class ManualAppleHealthPayload(BaseModel):
    date: Optional[str] = None
    resting_heart_rate: Optional[int] = None
    hrv_sdnn: Optional[float] = None
    sleep_duration_hours: Optional[float] = None
    sleep_deep_hours: Optional[float] = None
    sleep_rem_hours: Optional[float] = None
    weight_lbs: Optional[float] = None
    weight_kg: Optional[float] = None
    body_fat_pct: Optional[float] = None
    vo2_max: Optional[float] = None
    active_energy_kcal: Optional[float] = None
    recovery_score: Optional[int] = None


def _extract_webhook_token(request: Request) -> Optional[str]:
    x_tok = request.headers.get("x-apple-health-token")
    if x_tok and x_tok.strip():
        return x_tok.strip()
    auth_hdr = request.headers.get("authorization", "")
    if auth_hdr.lower().startswith("bearer "):
        bt = auth_hdr[7:].strip()
        if bt:
            return bt
    q_tok = request.query_params.get("token")
    if q_tok and q_tok.strip():
        return q_tok.strip()
    return None


@router.get("/status")
def apple_health_status(request: Request, uid: str = Depends(require_authenticated_user)):
    """Returns the user's Apple Health webhook URL, personal API token, and latest synced data."""
    token = get_or_create_apple_health_token(user_id=uid)
    base_url = get_app_base_url(request)
    webhook_url = f"{base_url}/api/apple-health/ingest"
    summary = get_apple_health_summary(user_id=uid, limit=14)
    return {
        "success": True,
        "webhook_url": webhook_url,
        "token": token,
        **summary,
    }


@router.post("/token/regenerate")
def apple_health_regenerate_token(request: Request, uid: str = Depends(require_authenticated_user)):
    """Rotates the user's personal Apple Health webhook token."""
    token = get_or_create_apple_health_token(user_id=uid, regenerate=True)
    base_url = get_app_base_url(request)
    return {
        "success": True,
        "token": token,
        "webhook_url": f"{base_url}/api/apple-health/ingest",
    }


@router.post("/ingest")
def apple_health_ingest(request: Request, payload: Any = Body(...)):
    """
    Webhook endpoint for Health Auto Export (iOS) and Apple Shortcuts.
    Authenticates via personal Apple Health token (Authorization: Bearer <token>,
    X-Apple-Health-Token: <token>, or ?token=<token>) or an active session.
    """
    uid: Optional[str] = None
    tok = _extract_webhook_token(request)
    if tok:
        uid = resolve_user_by_apple_health_token(tok)

    if not uid:
        user = getattr(request.state, "user", None)
        curr_uid = get_current_user_id()
        if user and not user.get("is_guest", False) and curr_uid != GUEST_USER_ID:
            uid = curr_uid

    if not uid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Apple Health webhook token.",
        )

    res = ingest_apple_health_payload(payload, user_id=uid, source="webhook")
    return res


@router.post("/manual")
def apple_health_manual_entry(
    payload: ManualAppleHealthPayload,
    uid: str = Depends(require_authenticated_user),
):
    """Saves a manual Apple Health biometric / readiness entry for the authenticated user."""
    data = payload.model_dump(exclude_none=True)
    has_metric = any(
        k in data
        for k in (
            "resting_heart_rate",
            "hrv_sdnn",
            "sleep_duration_hours",
            "weight_lbs",
            "weight_kg",
            "body_fat_pct",
            "vo2_max",
            "active_energy_kcal",
            "recovery_score",
        )
    )
    if not has_metric:
        raise HTTPException(status_code=400, detail="Please enter at least one metric to save.")

    res = ingest_apple_health_payload(data, user_id=uid, source="manual")
    return res


@router.post("/disconnect")
def apple_health_disconnect(uid: str = Depends(require_authenticated_user)):
    """Revokes the user's Apple Health webhook token."""
    set_setting("apple_health_webhook_token", "", user_id=uid)
    return {"success": True, "message": "Apple Health webhook token revoked."}

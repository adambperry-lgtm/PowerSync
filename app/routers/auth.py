import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from typing import Dict, Any, Optional

from app.services.strava_service import get_strava_auth_url, exchange_strava_code, fetch_recent_strava_activities
from app.services.whoop_service import get_whoop_auth_url, exchange_whoop_code, fetch_latest_whoop_metrics
from app.database import set_setting, get_setting

router = APIRouter(prefix="/api/auth", tags=["auth"])

def get_app_base_url(request: Request) -> str:
    """
    Returns the public base URL of the application.
    Prioritizes explicit APP_BASE_URL, otherwise derives the exact hostname
    from incoming request headers (Host or X-Forwarded-Host) so it always matches
    the domain currently visited in the athlete's browser.
    """
    if os.environ.get("APP_BASE_URL"):
        override = os.environ["APP_BASE_URL"].rstrip("/")
        if not override.startswith("http://") and not override.startswith("https://"):
            override = f"https://{override}"
        return override

    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        host = str(request.base_url.netloc)

    # In production/cloud environments (non-localhost), enforce https and strip internal container ports
    if "localhost" not in host and "127.0.0.1" not in host:
        if ":" in host:
            host = host.split(":")[0]
        return f"https://{host}"

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    return f"{proto}://{host}"

@router.get("/strava/login")
def strava_login(request: Request, client_id: Optional[str] = None, client_secret: Optional[str] = None):
    if client_id:
        set_setting("strava_client_id", client_id)
    if client_secret:
        set_setting("strava_client_secret", client_secret)

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/strava/callback"
    url = get_strava_auth_url(redirect_uri)
    return RedirectResponse(url)

@router.get("/strava/callback")
def strava_callback(code: str):
    res = exchange_strava_code(code)
    if res.get("success"):
        # Auto-fetch initial activities
        fetch_recent_strava_activities(20)
        return RedirectResponse("/?strava_connected=1")
    return {"error": res.get("error", "Failed to authenticate with Strava")}

@router.get("/whoop/login")
def whoop_login(request: Request, client_id: Optional[str] = None, client_secret: Optional[str] = None):
    if client_id:
        set_setting("whoop_client_id", client_id)
    if client_secret:
        set_setting("whoop_client_secret", client_secret)

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/whoop/callback"
    url = get_whoop_auth_url(redirect_uri)
    return RedirectResponse(url)

@router.get("/whoop/callback")
def whoop_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    state: Optional[str] = None
):
    if error:
        return {"error": f"Whoop authorization error: {error} - {error_description}"}
    if not code:
        return {"error": "No authorization code received from Whoop"}

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/whoop/callback"
    res = exchange_whoop_code(code, redirect_uri)
    if res.get("success"):
        # Auto-fetch latest metrics
        fetch_latest_whoop_metrics()
        return RedirectResponse("/?whoop_connected=1")
    return {"error": res.get("error", "Failed to authenticate with Whoop")}

@router.post("/sync/strava")
def sync_strava():
    tokens = get_setting("strava_tokens", {})
    if not tokens or not tokens.get("access_token"):
        return {"success": False, "error": "Strava is not connected. Please connect in Settings.", "count": 0}
        
    acts = fetch_recent_strava_activities(20)
    if not acts:
        curr_tokens = get_setting("strava_tokens", {})
        import time
        if time.time() > curr_tokens.get("expires_at", 0):
            return {"success": False, "error": "Strava authorization expired and token refresh failed. Please check your Strava Client Secret in Settings.", "count": 0, "auth_expired": True}
        return {"success": True, "count": 0, "message": "No new activities found."}
        
    return {"success": True, "count": len(acts)}

@router.post("/sync/whoop")
def sync_whoop():
    metrics = fetch_latest_whoop_metrics()
    if metrics.get("error"):
        return {"success": False, "error": metrics.get("error"), "auth_expired": metrics.get("auth_expired", False)}
    return {"success": True, "metrics": metrics}

@router.post("/disconnect/{service}")
def disconnect_service(service: str):
    if service == "strava":
        set_setting("strava_tokens", None)
    elif service == "whoop":
        set_setting("whoop_tokens", None)
    return {"success": True}

import os
import requests
import secrets
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.services.strava_service import get_strava_auth_url, exchange_strava_code, fetch_recent_strava_activities
from app.services.whoop_service import get_whoop_auth_url, exchange_whoop_code, fetch_latest_whoop_metrics
from app.database import (
    set_setting, get_setting, get_db_connection, get_current_user_id,
    create_or_get_google_user, create_or_get_email_user, create_or_get_dev_user, get_user_by_id,
    create_session, get_user_by_session, delete_session,
    save_oauth_state, verify_and_consume_oauth_state, get_default_or_guest_user,
    get_guest_user, get_default_athlete_user,
    get_primary_owner_email, set_primary_owner_email,
    DEFAULT_USER_ID, GUEST_USER_ID
)

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

def is_production_req(request: Request) -> bool:
    base = get_app_base_url(request)
    return "powersync.up.railway.app" in base or (base.startswith("https://") and "localhost" not in base)

@router.get("/me")
def get_current_user_profile(request: Request):
    """Returns the authenticated athlete profile, session validity, and account connection status."""
    user = getattr(request.state, "user", None)
    if not user:
        candidate_tokens = []
        if "authorization" in request.headers:
            auth_val = request.headers["authorization"]
            if auth_val.startswith("Bearer "):
                bt = auth_val[7:].strip()
                if bt:
                    candidate_tokens.append(bt)
        cookie_tok = request.cookies.get("powersync_session")
        if cookie_tok and cookie_tok not in candidate_tokens:
            candidate_tokens.append(cookie_tok)
        for tok in candidate_tokens:
            user = get_user_by_session(tok)
            if user:
                break
        if not user:
            user = get_guest_user()

    uid = user.get("id", GUEST_USER_ID)
    is_guest = (uid == GUEST_USER_ID or user.get("is_guest", False))
    
    user_payload = {
        "id": uid,
        "email": user.get("email", ""),
        "name": user.get("name", "Guest" if is_guest else "Athlete"),
        "picture": user.get("picture", ""),
        "google_linked": bool(user.get("google_id")),
        "created_at": user.get("created_at"),
        "is_guest": is_guest
    }

    return {
        "authenticated": not is_guest,
        "is_guest": is_guest,
        "id": uid,
        "email": user.get("email", ""),
        "name": user.get("name", "Guest" if is_guest else "Athlete"),
        "picture": user.get("picture", ""),
        "google_linked": bool(user.get("google_id")),
        "created_at": user.get("created_at"),
        "user": user_payload
    }

# ==========================================
# Google Sign-In & OAuth 2.0 Engine
# ==========================================

@router.get("/google/status")
def google_auth_status():
    """Returns whether Google Sign-In client credentials are configured."""
    client_id = str(get_setting("google_client_id", "") or "").strip()
    client_secret = str(get_setting("google_client_secret", "") or "").strip()
    return {
        "configured": bool(client_id and client_secret and "•" not in client_secret),
        "client_id": client_id if client_id else None
    }

@router.get("/google/login")
def google_login(request: Request):
    """Initiates Google OAuth 2.0 OpenID Connect authorization."""
    client_id = str(get_setting("google_client_id", "") or "").strip()
    if not client_id:
        return RedirectResponse("/?auth_error=Google%20Sign-In%20client%20ID%20is%20not%20configured%20yet.%20Please%20set%20GOOGLE_CLIENT_ID%20in%20Settings%20or%20Railway.", status_code=302)

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/google/callback"
    state = secrets.token_urlsafe(16)
    
    # Save state with current user context if logged in, or None if starting fresh
    current_uid = get_current_user_id()
    save_oauth_state(state, current_uid if current_uid != DEFAULT_USER_ID else None, "google")

    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile&"
        f"access_type=offline&"
        f"prompt=select_account&"
        f"state={state}"
    )
    return RedirectResponse(google_auth_url, status_code=302)

@router.get("/google/callback")
def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    """Handles Google OAuth callback, verifies state, retrieves userinfo, and sets persistent session."""
    if error:
        return RedirectResponse(f"/?auth_error=Google%20Sign-In%20cancelled:%20{error}", status_code=302)
    if not code:
        return RedirectResponse("/?auth_error=No%20authorization%20code%20received%20from%20Google", status_code=302)

    client_id = str(get_setting("google_client_id", "") or "").strip()
    client_secret = str(get_setting("google_client_secret", "") or "").strip()
    if not client_id or not client_secret:
        return RedirectResponse("/?auth_error=Google%20OAuth%20client%20credentials%20are%20missing%20on%20the%20server.", status_code=302)

    # Verify and consume state
    verify_and_consume_oauth_state(state, "google")

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/google/callback"

    token_payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    try:
        token_res = requests.post("https://oauth2.googleapis.com/token", data=token_payload, timeout=10)
        if token_res.status_code != 200:
            return RedirectResponse(f"/?auth_error=Google%20token%20exchange%20failed:%20HTTP%20{token_res.status_code}", status_code=302)
        
        token_json = token_res.json()
        access_token = token_json.get("access_token")

        userinfo_res = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        if userinfo_res.status_code != 200:
            return RedirectResponse("/?auth_error=Could%20not%20retrieve%20Google%20profile%20data", status_code=302)

        profile = userinfo_res.json()
        google_id = profile.get("sub")
        email = profile.get("email")
        name = profile.get("name") or email.split("@")[0]
        picture = profile.get("picture", "")

        user = create_or_get_google_user(email=email, name=name, picture=picture, google_id=google_id)
        session_token = create_session(user["id"], days_valid=30)

        response = RedirectResponse(f"/?login_success=1&session_token={session_token}", status_code=302)
        response.set_cookie(
            key="powersync_session",
            value=session_token,
            max_age=30 * 86400,
            httponly=True,
            samesite="lax",
            secure=is_production_req(request),
            path="/"
        )
        return response
    except Exception as e:
        return RedirectResponse(f"/?auth_error=Google%20sign-in%20network%20error:%20{str(e)}", status_code=302)

class EmailLoginPayload(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    claim_primary: Optional[bool] = False

DevLoginPayload = EmailLoginPayload

@router.get("/owner-status")
def get_owner_status():
    """Returns whether the primary athlete account has been locked to an exclusive email address."""
    locked_owner = get_primary_owner_email()
    return {
        "is_locked": bool(locked_owner),
        "owner_email": locked_owner
    }

class LockOwnerPayload(BaseModel):
    email: str

@router.post("/lock-owner")
def lock_owner_email(payload: LockOwnerPayload, request: Request):
    """Locks the primary athlete account exclusively to this email address."""
    clean_email = payload.email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        raise HTTPException(status_code=400, detail="Valid email address is required.")
        
    current_uid = get_current_user_id()
    locked_owner = get_primary_owner_email()
    if locked_owner and locked_owner != clean_email and current_uid != DEFAULT_USER_ID:
        raise HTTPException(status_code=403, detail=f"Primary account is already locked to {locked_owner}.")

    set_primary_owner_email(clean_email)
    return {"success": True, "message": f"Primary athlete account locked to {clean_email}.", "owner_email": clean_email}

@router.post("/primary-login")
def primary_login(request: Request):
    """
    Direct login as the primary athlete account owner holding all historical directives and intervals credentials.
    If an owner email is locked, anonymous access is rejected.
    """
    locked_owner = get_primary_owner_email()
    current_uid = get_current_user_id()
    if locked_owner and current_uid != DEFAULT_USER_ID:
        raise HTTPException(
            status_code=403,
            detail=f"Primary athlete account is locked to {locked_owner}. Please enter your email to sign in."
        )

    user = get_default_athlete_user()
    session_token = create_session(user["id"], days_valid=30)

    res = JSONResponse({
        "success": True,
        "message": f"Successfully authenticated as {user['name']} (Owner)",
        "session_token": session_token,
        "user": user
    })
    res.set_cookie(
        key="powersync_session",
        value=session_token,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=is_production_req(request),
        path="/"
    )
    return res

@router.post("/email-login")
@router.post("/dev-login")
def email_login(request: Request, payload: EmailLoginPayload):
    """
    Direct Email Login: allows any athlete to sign in with their email address.
    Completely isolated data without requiring Google Cloud Console or third-party OAuth setup.
    If claim_primary is True, links the email to the primary owner profile (preserving intervals.icu credentials).
    """
    clean_email = payload.email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
        
    name = payload.name or clean_email.split("@")[0].replace(".", " ").title()
    user = create_or_get_email_user(
        email=clean_email,
        name=name,
        picture=payload.picture,
        claim_primary=bool(payload.claim_primary)
    )
    session_token = create_session(user["id"], days_valid=30)

    res = JSONResponse({
        "success": True,
        "message": f"Successfully authenticated as {user['name']}",
        "session_token": session_token,
        "user": user
    })
    res.set_cookie(
        key="powersync_session",
        value=session_token,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=is_production_req(request),
        path="/"
    )
    return res

@router.post("/logout")
def logout(request: Request):
    """Revokes active session tokens (cookie and Bearer) and clears the authentication cookie."""
    cookie_token = request.cookies.get("powersync_session")
    if cookie_token:
        delete_session(cookie_token)
    if "authorization" in request.headers:
        auth_val = request.headers["authorization"]
        if auth_val.startswith("Bearer "):
            bearer_token = auth_val[7:].strip()
            if bearer_token and bearer_token != cookie_token:
                delete_session(bearer_token)
    res = JSONResponse({"success": True, "message": "Signed out successfully"})
    res.delete_cookie(key="powersync_session", path="/")
    return res

@router.post("/claim-default-data")
def claim_default_data(request: Request):
    """
    Imports all settings, directives, biometrics, activities, and target plans
    from usr_default into the currently authenticated athlete account.
    """
    from app.database import claim_or_copy_default_data_to_user, get_current_user_id
    uid = get_current_user_id()
    if uid == GUEST_USER_ID:
        raise HTTPException(status_code=401, detail="Please sign in before importing athlete settings.")
    locked_owner = get_primary_owner_email()
    user = getattr(request.state, "user", None) or get_user_by_id(uid) or {}
    if locked_owner and uid != DEFAULT_USER_ID and str(user.get("email", "")).strip().lower() != locked_owner:
        raise HTTPException(status_code=403, detail=f"Default athlete data is restricted to the primary account owner ({locked_owner}).")
    res = claim_or_copy_default_data_to_user(uid)
    return res

# ==========================================
# Diagnostic Telemetry
# ==========================================

@router.get("/debug-headers")
def debug_headers(request: Request):
    from app.database import DB_PATH, get_db_path
    
    mount_lines = []
    if os.path.exists("/proc/mounts"):
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    if any(term in line.lower() for term in ["data", "volume", "railway", "app"]):
                        mount_lines.append(line.strip())
        except Exception as e:
            mount_lines.append(f"Error reading mounts: {e}")

    vol_raw = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")
    vol_strip = vol_raw.strip()
    
    dir_info = {}
    for p in ["/app/data", vol_raw, vol_strip]:
        if p and repr(p) not in dir_info:
            dir_info[repr(p)] = {
                "exists": os.path.exists(p),
                "isdir": os.path.isdir(p),
                "ismount": os.path.ismount(p) if os.path.exists(p) else False,
                "files": os.listdir(p) if os.path.isdir(p) else []
            }

    current_db = get_db_path()
    uid = get_current_user_id()

    conn = get_db_connection()
    user_count = conn.cursor().execute("SELECT count(*) FROM users").fetchone()[0] if os.path.exists(current_db) else 0
    session_count = conn.cursor().execute("SELECT count(*) FROM sessions").fetchone()[0] if os.path.exists(current_db) else 0
    user_keys = [r[0] for r in conn.cursor().execute("SELECT key FROM settings WHERE user_id = ?", (uid,)).fetchall()] if os.path.exists(current_db) else []
    conn.close()

    return {
        "headers": dict(request.headers),
        "base_url": str(request.base_url),
        "calculated_base_url": get_app_base_url(request),
        "active_user_context": uid,
        "database": {
            "resolved_path": current_db,
            "static_DB_PATH": DB_PATH,
            "exists": os.path.exists(current_db),
            "size_bytes": os.path.getsize(current_db) if os.path.exists(current_db) else 0,
            "parent_dir_writable": os.access(os.path.dirname(current_db), os.W_OK) if os.path.exists(os.path.dirname(current_db)) else False,
            "railway_volume_mount_path": os.environ.get("RAILWAY_VOLUME_MOUNT_PATH"),
            "railway_volume_name": os.environ.get("RAILWAY_VOLUME_NAME")
        },
        "mount_inspection": {
            "matching_mounts": mount_lines,
            "directories": dir_info
        },
        "env_configured": {
            "gemini_api_key": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("gemini_api_key")),
            "google_client_id": bool(os.environ.get("GOOGLE_CLIENT_ID") or get_setting("google_client_id")),
            "google_client_secret": bool(os.environ.get("GOOGLE_CLIENT_SECRET") or get_setting("google_client_secret")),
            "strava_client_id": bool(os.environ.get("STRAVA_CLIENT_ID") or os.environ.get("strava_client_id")),
            "strava_client_secret": bool(os.environ.get("STRAVA_CLIENT_SECRET") or os.environ.get("strava_client_secret")),
            "whoop_client_id": bool(os.environ.get("WHOOP_CLIENT_ID") or os.environ.get("whoop_client_id")),
            "whoop_client_secret": bool(os.environ.get("WHOOP_CLIENT_SECRET") or os.environ.get("whoop_client_secret")),
            "intervals_icu_api_key": bool(os.environ.get("INTERVALS_ICU_API_KEY") or os.environ.get("INTERVALS_API_KEY")),
        },
        "multi_user_stats": {
            "total_users": user_count,
            "active_sessions": session_count,
            "active_user_settings_keys": user_keys
        },
        "tokens_connected": {
            "strava_tokens_present": bool(get_setting("strava_tokens", user_id=uid)),
            "whoop_tokens_present": bool(get_setting("whoop_tokens", user_id=uid))
        }
    }

# ==========================================
# Strava & Whoop Integrations (User-Scoped)
# ==========================================

@router.get("/strava/login")
def strava_login(request: Request, client_id: Optional[str] = None, client_secret: Optional[str] = None):
    uid = get_current_user_id()
    if client_id:
        set_setting("strava_client_id", str(client_id).strip(), user_id=uid)
    if client_secret:
        set_setting("strava_client_secret", str(client_secret).strip(), user_id=uid)

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/strava/callback"
    
    # Track OAuth state tied to active user ID
    state = secrets.token_urlsafe(16)
    save_oauth_state(state, uid, "strava")

    url = get_strava_auth_url(redirect_uri, state=state)
    return RedirectResponse(url)

@router.get("/strava/callback")
def strava_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        return {"error": f"Strava authorization was cancelled or denied: {error}"}
    if not code:
        return {"error": "No authorization code received from Strava"}

    uid = verify_and_consume_oauth_state(state, "strava") if state else None
    uid = uid or get_current_user_id()

    res = exchange_strava_code(code, user_id=uid)
    if res.get("success"):
        try:
            fetch_recent_strava_activities(20, user_id=uid)
        except Exception as e:
            print(f"[PowerSync] Note: Background Strava pre-fetch error: {e}")
        session_token = create_session(uid, days_valid=30)
        response = RedirectResponse(f"/?strava_connected=1&session_token={session_token}", status_code=302)
        response.set_cookie(
            key="powersync_session",
            value=session_token,
            max_age=30 * 86400,
            httponly=True,
            samesite="lax",
            secure=is_production_req(request),
            path="/"
        )
        return response
    return {"error": res.get("error", "Failed to authenticate with Strava")}

@router.get("/whoop/login")
def whoop_login(request: Request, client_id: Optional[str] = None, client_secret: Optional[str] = None):
    uid = get_current_user_id()
    if client_id:
        set_setting("whoop_client_id", str(client_id).strip(), user_id=uid)
    if client_secret:
        set_setting("whoop_client_secret", str(client_secret).strip(), user_id=uid)

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/whoop/callback"
    
    # Track OAuth state tied to active user ID
    state = secrets.token_urlsafe(16)
    save_oauth_state(state, uid, "whoop")

    url = get_whoop_auth_url(redirect_uri, state=state, user_id=uid)
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

    uid = verify_and_consume_oauth_state(state, "whoop") if state else None
    uid = uid or get_current_user_id()

    base_url = get_app_base_url(request)
    redirect_uri = f"{base_url}/api/auth/whoop/callback"
    res = exchange_whoop_code(code, redirect_uri, user_id=uid)
    if res.get("success"):
        try:
            fetch_latest_whoop_metrics(user_id=uid)
        except Exception as e:
            print(f"[PowerSync] Note: Background Whoop pre-fetch error: {e}")
        session_token = create_session(uid, days_valid=30)
        response = RedirectResponse(f"/?whoop_connected=1&session_token={session_token}", status_code=302)
        response.set_cookie(
            key="powersync_session",
            value=session_token,
            max_age=30 * 86400,
            httponly=True,
            samesite="lax",
            secure=is_production_req(request),
            path="/"
        )
        return response
    return {"error": res.get("error", "Failed to authenticate with Whoop")}

@router.post("/sync/strava")
def sync_strava():
    uid = get_current_user_id()
    tokens = get_setting("strava_tokens", {}, user_id=uid)
    if (not tokens or not tokens.get("access_token")) and uid == "usr_guest":
        tokens = get_setting("strava_tokens", {}, user_id="usr_default")
    if not tokens or not tokens.get("access_token"):
        return {"success": False, "error": "Strava is not connected for this account. Please connect in Settings.", "count": 0}
        
    try:
        acts = fetch_recent_strava_activities(20, user_id=uid)
    except Exception as e:
        return {"success": False, "error": f"Error syncing Strava activities: {str(e)}", "count": 0}
    if not acts:
        curr_tokens = get_setting("strava_tokens", {}, user_id=uid)
        import time
        if time.time() > curr_tokens.get("expires_at", 0):
            return {"success": False, "error": "Strava authorization expired and token refresh failed.", "count": 0, "auth_expired": True}
        return {"success": True, "count": 0, "message": "No new activities found."}
        
    return {"success": True, "count": len(acts)}

@router.post("/sync/whoop")
def sync_whoop():
    uid = get_current_user_id()
    metrics = fetch_latest_whoop_metrics(user_id=uid)
    if metrics.get("error"):
        return {"success": False, "error": metrics.get("error"), "auth_expired": metrics.get("auth_expired", False)}
    import time
    now_ts = time.time()
    set_setting("last_whoop_sync_timestamp", now_ts, user_id=uid)
    if uid == "usr_guest":
        set_setting("last_whoop_sync_timestamp", now_ts, user_id="usr_default")
    return {"success": True, "metrics": metrics}

@router.post("/disconnect/{service}")
def disconnect_service(service: str):
    uid = get_current_user_id()
    if service == "strava":
        set_setting("strava_tokens", None, user_id=uid)
    elif service == "whoop":
        set_setting("whoop_tokens", None, user_id=uid)
    return {"success": True}

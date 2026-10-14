from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.database import get_setting, set_setting, get_all_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

class SettingsUpdate(BaseModel):
    athlete_ftp: Optional[int] = None
    athlete_max_hr: Optional[int] = None
    athlete_w_prime_kj: Optional[float] = None
    athlete_peak_power_watts: Optional[int] = None
    demo_mode: Optional[bool] = None
    gemini_api_key: Optional[str] = None
    intervals_athlete_id: Optional[str] = None
    intervals_icu_api_key: Optional[str] = None
    strava_client_id: Optional[str] = None
    strava_client_secret: Optional[str] = None
    whoop_client_id: Optional[str] = None
    whoop_client_secret: Optional[str] = None
    program_goal: Optional[str] = None
    program_target_ftp: Optional[int] = None
    program_target_date: Optional[str] = None
    program_weekly_tss_target: Optional[int] = None
    program_weekly_xss_target: Optional[int] = None
    google_maps_api_key: Optional[str] = None
    preferred_map_layer: Optional[str] = None
    theme_mode: Optional[str] = None

def is_valid_secret(secret: Optional[str]) -> bool:
    if not secret or not secret.strip():
        return False
    v = secret.strip()
    # Masked values containing bullet characters must never be treated as valid plaintext secrets
    if "•" in v or "\u2022" in v:
        return False
    return True

def mask_secret(secret: Optional[str]) -> str:
    if not is_valid_secret(secret):
        return ""
    s = secret.strip()
    if len(s) <= 6:
        return "••••••"
    return s[:3] + "••••••••" + s[-3:]

@router.get("")
def get_settings_endpoint():
    all_s = get_all_settings()
    
    intervals_key = all_s.get("intervals_icu_api_key", "")
    gemini_key = all_s.get("gemini_api_key", "")
    google_maps_key = all_s.get("google_maps_api_key", "")
    strava_secret = all_s.get("strava_client_secret", "")
    whoop_secret = all_s.get("whoop_client_secret", "")

    return {
        "athlete_ftp": int(all_s.get("athlete_ftp", 250)),
        "athlete_max_hr": int(all_s.get("athlete_max_hr", 185)),
        "athlete_w_prime_kj": float(all_s.get("athlete_w_prime_kj", 20.0)),
        "athlete_peak_power_watts": int(all_s.get("athlete_peak_power_watts", 1050)),
        "demo_mode": bool(all_s.get("demo_mode", True)),
        "gemini_api_key_set": is_valid_secret(gemini_key),
        "gemini_api_key_masked": mask_secret(gemini_key),
        "google_maps_api_key_set": is_valid_secret(google_maps_key),
        "google_maps_api_key_masked": mask_secret(google_maps_key),
        "preferred_map_layer": all_s.get("preferred_map_layer", "google_roads"),
        "intervals_athlete_id": all_s.get("intervals_athlete_id", ""),
        "intervals_icu_api_key_set": is_valid_secret(intervals_key),
        "intervals_icu_api_key_masked": mask_secret(intervals_key),
        "strava_client_id": all_s.get("strava_client_id", ""),
        "strava_client_secret_set": is_valid_secret(strava_secret),
        "strava_connected": bool(all_s.get("strava_tokens")),
        "whoop_client_id": all_s.get("whoop_client_id", ""),
        "whoop_client_secret_set": is_valid_secret(whoop_secret),
        "whoop_connected": bool(all_s.get("whoop_tokens")),
        "program_goal": all_s.get("program_goal", "FTP_BUILD"),
        "program_target_ftp": int(all_s.get("program_target_ftp", 265)),
        "program_target_date": all_s.get("program_target_date", ""),
        "program_weekly_tss_target": int(all_s.get("program_weekly_tss_target", 360)),
        "program_weekly_xss_target": int(all_s.get("program_weekly_xss_target", all_s.get("program_weekly_tss_target", 360))),
        "theme_mode": all_s.get("theme_mode", "system")
    }

@router.post("")
def update_settings_endpoint(payload: SettingsUpdate):
    if payload.theme_mode is not None and payload.theme_mode.strip() in ("dark", "light", "system"):
        set_setting("theme_mode", payload.theme_mode.strip())
    if payload.athlete_ftp is not None:
        set_setting("athlete_ftp", payload.athlete_ftp)
    if payload.athlete_max_hr is not None:
        set_setting("athlete_max_hr", payload.athlete_max_hr)
    if payload.athlete_w_prime_kj is not None:
        set_setting("athlete_w_prime_kj", payload.athlete_w_prime_kj)
    if payload.athlete_peak_power_watts is not None:
        set_setting("athlete_peak_power_watts", payload.athlete_peak_power_watts)
    if payload.demo_mode is not None:
        set_setting("demo_mode", payload.demo_mode)
    if is_valid_secret(payload.gemini_api_key):
        set_setting("gemini_api_key", payload.gemini_api_key.strip())
    if is_valid_secret(payload.google_maps_api_key):
        set_setting("google_maps_api_key", payload.google_maps_api_key.strip())
    if payload.preferred_map_layer is not None:
        set_setting("preferred_map_layer", payload.preferred_map_layer.strip())
    if payload.intervals_athlete_id is not None:
        set_setting("intervals_athlete_id", payload.intervals_athlete_id.strip())
    if is_valid_secret(payload.intervals_icu_api_key):
        set_setting("intervals_icu_api_key", payload.intervals_icu_api_key.strip())
    if payload.strava_client_id is not None and payload.strava_client_id.strip():
        set_setting("strava_client_id", payload.strava_client_id.strip())
    if is_valid_secret(payload.strava_client_secret):
        set_setting("strava_client_secret", payload.strava_client_secret.strip())
    if payload.whoop_client_id is not None and payload.whoop_client_id.strip():
        set_setting("whoop_client_id", payload.whoop_client_id.strip())
    if is_valid_secret(payload.whoop_client_secret):
        set_setting("whoop_client_secret", payload.whoop_client_secret.strip())
    if payload.program_goal is not None:
        set_setting("program_goal", payload.program_goal)
    if payload.program_target_ftp is not None:
        set_setting("program_target_ftp", payload.program_target_ftp)
    if payload.program_target_date is not None:
        set_setting("program_target_date", payload.program_target_date)
    if payload.program_weekly_tss_target is not None:
        set_setting("program_weekly_tss_target", payload.program_weekly_tss_target)
    if payload.program_weekly_xss_target is not None:
        set_setting("program_weekly_xss_target", payload.program_weekly_xss_target)

    return {"success": True, "message": "Settings updated successfully"}

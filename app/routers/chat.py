from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.database import get_setting, set_setting, get_current_user_id
from app.services.coach_chat_service import handle_coach_chat, compile_athlete_context, get_gemini_api_key

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatMessagePayload(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []

class SaveApiKeyPayload(BaseModel):
    api_key: str

@router.post("")
def chat_with_coach_endpoint(payload: ChatMessagePayload):
    """
    Interactive chat with PowerSync AI Coach:
    Injects full athlete telemetry into Google Gemini or the sports-science engine.
    """
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
        
    try:
        result = handle_coach_chat(payload.message.strip(), payload.history or [])
        return result
    except Exception as e:
        print(f"Error handling coach chat: {e}")
        raise HTTPException(status_code=500, detail=f"Coach chatbot error: {str(e)}")

@router.get("/status")
def get_chat_status():
    """Returns Gemini readiness, athlete snapshot summary, and suggested starter questions."""
    key = get_gemini_api_key()
    snapshot = compile_athlete_context()
    rec = snapshot["whoop_readiness_today"]["recovery_score_pct"]
    dur = snapshot["today_prescribed_workout"]["duration_minutes"]
    workout = snapshot["today_prescribed_workout"]["title"]

    from app.services.coach_chat_service import _CACHED_WORKING_MODEL
    model_name = _CACHED_WORKING_MODEL[1] if _CACHED_WORKING_MODEL else "gemini-3-flash-preview"

    suggested = [
        f"🎯 How should I tackle today's {workout} with my {rec}% recovery?",
        "📅 I have a 50-mile ride this Sunday with 3,000 ft climbing",
        "🥪 What is my ideal carbohydrate & hydration fueling plan?",
        "🔮 Analyze my weekly TSS & XSS pacing toward my goal"
    ]

    return {
        "success": True,
        "gemini_configured": bool(key),
        "gemini_model": model_name if key else None,
        "gemini_status_text": f"Connected ({model_name})" if key else "Not connected",
        "athlete_ftp": snapshot["athlete"]["ftp_watts"],
        "recovery_score": rec,
        "active_workout": workout,
        "suggested_questions": suggested
    }

class TestConnectionPayload(BaseModel):
    api_key: Optional[str] = None

@router.post("/test-connection")
def test_gemini_connection_endpoint(payload: Optional[TestConnectionPayload] = None):
    """Live-tests the Google Gemini API connection using the provided or saved key."""
    key = (payload.api_key.strip() if payload and payload.api_key else "") or get_gemini_api_key()
    if not key or "•" in key:
        return {"success": False, "message": "No valid Gemini API key found to test."}

    from app.services.coach_chat_service import call_gemini_api
    reply = call_gemini_api(key, "You are a cycling coach.", [], "Ping test")
    if reply:
        from app.services.coach_chat_service import _CACHED_WORKING_MODEL
        model = _CACHED_WORKING_MODEL[1] if _CACHED_WORKING_MODEL else "gemini-3-flash-preview"
        return {
            "success": True,
            "model": model,
            "message": f"Successfully connected to Google Gemini ({model})!"
        }
    return {
        "success": False,
        "message": "Could not connect to Gemini API. Please check your key or network connection."
    }

@router.post("/save-key")
def save_gemini_key_endpoint(payload: SaveApiKeyPayload):
    """Allows athlete to save or update Gemini API key directly from the chat interface."""
    key = payload.api_key.strip()
    if not key or len(key) < 20:
        raise HTTPException(status_code=400, detail="Invalid Gemini API key provided.")
    set_setting("gemini_api_key", key)
    return {
        "success": True,
        "message": "Google Gemini API key saved! AI Coach is now fully powered by Gemini."
    }

def _clean_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return int(val)
    import re
    match = re.search(r'\d+', str(val))
    if match:
        try:
            return int(match.group(0))
        except (ValueError, TypeError):
            return default
    return default

def _clean_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    import re
    match = re.search(r'[\d.]+', str(val))
    if match:
        try:
            return float(match.group(0))
        except (ValueError, TypeError):
            return default
    return default

class ApplyChatActionPayload(BaseModel):
    action_type: str  # "apply_today_workout" | "schedule_upcoming_plan"
    action_data: Dict[str, Any]

@router.post("/apply-action")
def apply_chat_action_endpoint(payload: ApplyChatActionPayload):
    """
    Applies a workout or target plan proposed in coach chat directly to the dashboard.
    """
    try:
        action_type = payload.action_type
        data = payload.action_data or {}
        import datetime

        if action_type == "apply_today_workout":
            from app.routers.workouts import get_current_workout_cache, get_current_options_cache
            from app.services.zwift_service import generate_zwo_xml, generate_intervals_icu_text, reconcile_workout_intervals
            from app.services.fueling_service import generate_fueling_plan
            from app.database import get_db_connection
            from app.services.strava_service import get_strava_trailing_stats

            ftp = _clean_int(get_setting("athlete_ftp", 250), 250)
            title = data.get("title") or "Coach Tailored Workout"
            duration = _clean_int(data.get("duration_minutes"), 45)
            focus = data.get("focus_area") or data.get("intensity_type") or "Adaptive Training"
            tss = _clean_int(data.get("estimated_tss"), round(duration * 0.75))
            raw_intervals = data.get("intervals") or [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Warmup"},
                {"type": "SteadyState", "duration_sec": max(300, (duration * 60) - 600), "power_pct": 75, "cadence": 90, "name": "Main Set"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 55, "power_high_pct": 40, "cadence": 80, "name": "Cooldown"}
            ]
            intervals = reconcile_workout_intervals(raw_intervals, duration, ftp=ftp)

            workout_obj = {
                "id": "workout_coach_prescribed",
                "option_type": "coach_chat",
                "badge": "💬 Coach Custom",
                "badge_color": "cyan",
                "title": title,
                "description": data.get("description") or f"Collaborative session crafted with AI Coach ({duration}m, ~{tss} TSS).",
                "focus_area": focus,
                "duration_minutes": duration,
                "estimated_tss": tss,
                "ai_rationale": "Prescribed directly from your coach consultation. Calibrated for your current recovery and training phase.",
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)

            workout_cache = get_current_workout_cache()
            options_cache = get_current_options_cache()
            workout_cache.clear()
            workout_cache.update(workout_obj)
            options_cache["workout_coach_prescribed"] = workout_obj

            # Calculate fueling plan
            uid = get_current_user_id()
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (uid,))
            whoop_row = c.fetchone()
            conn.close()
            rec_score = int(whoop_row["recovery_score"]) if whoop_row else 50
            from app.services.whoop_service import get_trailing_whoop_stats
            whoop_trailing = get_trailing_whoop_stats(days=7)
            strava_trailing = get_strava_trailing_stats(days=7)
            trailing_strain = float(whoop_trailing.get("trailing_7d_strain_avg") or strava_trailing.get("trailing_7d_strain_avg") or 11.0)
            yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))

            fueling = generate_fueling_plan(
                duration_min=duration,
                distance_miles=float(data.get("distance_miles") or 0.0),
                avg_power_watts=round(ftp * 0.70),
                ftp=ftp,
                intensity_type=focus,
                ride_title=title,
                athlete_weight_kg=70.0,
                temp_f=74,
                humidity_pct=50,
                is_outdoor=bool(data.get("distance_miles")),
                recovery_score=rec_score,
                trailing_strain_avg=trailing_strain,
                yesterday_tss=yesterday_tss
            )

            return {
                "success": True,
                "action_type": "apply_today_workout",
                "message": f"Applied '{title}' as today's workout!",
                "active_workout": workout_obj,
                "options": list(options_cache.values()),
                "fueling_plan": fueling
            }

        elif action_type == "schedule_workout":
            from app.services.zwift_service import generate_zwo_xml, generate_intervals_icu_text, push_to_intervals_icu, reconcile_workout_intervals

            target_date = data.get("target_date")
            if not target_date or target_date == "tomorrow":
                target_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

            ftp = _clean_int(get_setting("athlete_ftp", 250), 250)
            title = data.get("title") or "Scheduled Workout"
            duration = _clean_int(data.get("duration_minutes"), 45)
            focus = data.get("focus_area") or data.get("intensity_type") or "Adaptive Training"
            tss = _clean_int(data.get("estimated_tss"), round(duration * 0.75))
            raw_intervals = data.get("intervals") or [
                {"type": "Warmup", "duration_sec": 300, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Warmup"},
                {"type": "SteadyState", "duration_sec": max(300, (duration * 60) - 600), "power_pct": 75, "cadence": 90, "name": "Main Set"},
                {"type": "Cooldown", "duration_sec": 300, "power_low_pct": 55, "power_high_pct": 40, "cadence": 80, "name": "Cooldown"}
            ]
            intervals = reconcile_workout_intervals(raw_intervals, duration, ftp=ftp)

            workout_obj = {
                "id": f"workout_scheduled_{target_date.replace('-', '')}",
                "option_type": "coach_scheduled",
                "badge": "📅 Scheduled",
                "badge_color": "blue",
                "title": title,
                "target_date": target_date,
                "description": data.get("description") or f"Scheduled {focus} session for {target_date} ({duration}m, ~{tss} TSS).",
                "focus_area": focus,
                "duration_minutes": duration,
                "estimated_tss": tss,
                "distance_miles": 0.0,
                "elevation_gain_ft": 0.0,
                "ai_rationale": f"Scheduled for {target_date} via AI Coach chat. Calibrated to your {ftp}W FTP.",
                "intervals": intervals
            }
            workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
            workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)

            from app.database import save_scheduled_workout
            save_scheduled_workout(workout_obj, target_date)

            athlete_id = get_setting("intervals_athlete_id", "")
            api_key = get_setting("intervals_icu_api_key", "")
            sync_result = None
            if athlete_id and api_key and "•" not in api_key and "\u2022" not in api_key:
                try:
                    sync_result = push_to_intervals_icu(athlete_id, api_key, workout_obj, target_date, ftp=ftp)
                except Exception as e:
                    print("Error pushing scheduled workout to Intervals.icu:", e)

            synced_zwift = bool(sync_result and sync_result.get("success"))
            sync_msg = " & synced to Zwift calendar" if synced_zwift else " (ready to sync to Zwift)"
            return {
                "success": True,
                "action_type": "schedule_workout",
                "message": f"'{title}' scheduled for {target_date}{sync_msg}! 🚀",
                "workout": workout_obj,
                "target_date": target_date,
                "synced_to_zwift": synced_zwift
            }

        elif action_type == "schedule_upcoming_plan":
            from app.database import save_target_plan, get_active_target_plan
            from app.services.plan_service import compute_taper_leadup_schedule

            target_date = data.get("target_date")
            if not target_date:
                target_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

            plan_dict = {
                "title": data.get("title") or "Planned Ride",
                "target_date": target_date,
                "distance_miles": _clean_float(data.get("distance_miles"), 40.0),
                "elevation_gain_ft": _clean_float(data.get("elevation_gain_ft"), 1500.0),
                "intensity_type": data.get("intensity_type") or data.get("focus_area") or "Endurance",
                "estimated_duration_min": _clean_int(data.get("duration_minutes") or data.get("estimated_duration_min"), 120),
                "estimated_tss": _clean_int(data.get("estimated_tss"), 100),
                "description": data.get("description") or "Scheduled via AI Coach chat consultation"
            }
            plan_id = save_target_plan(plan_dict)
            active = get_active_target_plan()
            ftp = _clean_int(get_setting("athlete_ftp", 250), 250)
            schedule = compute_taper_leadup_schedule(active, current_ftp=ftp) if active else []

            return {
                "success": True,
                "action_type": "schedule_upcoming_plan",
                "message": f"Scheduled '{plan_dict['title']}' for {plan_dict['target_date']}! Lead-up taper active.",
                "plan": active,
                "schedule": schedule
            }

        elif action_type == "clear_upcoming_plan":
            from app.database import clear_active_target_plans
            clear_active_target_plans()
            return {
                "success": True,
                "action_type": "clear_upcoming_plan",
                "message": "Upcoming target plan cleared! Reverted to standard progression."
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action type: {action_type}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error applying workout action: {str(e)}"
        }

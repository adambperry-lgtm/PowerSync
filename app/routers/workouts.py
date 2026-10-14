from fastapi import APIRouter, Response, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import uuid
import datetime
import re

from app.database import get_setting, get_db_connection, set_setting
from app.services.ai_coach import build_workout_bundle
from app.services.program_service import get_current_program
from app.services.zwift_service import generate_zwo_xml, generate_intervals_icu_text, push_to_intervals_icu
from app.services.mock_data import get_mock_whoop_data, get_mock_weekly_stats, get_mock_strava_activities
from app.services.fueling_service import generate_fueling_plan
from app.services.strava_service import get_strava_trailing_stats

router = APIRouter(prefix="/api/workouts", tags=["workouts"])

def is_planned_custom_ride_description(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    has_dist = bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:miles?|mi|km|k)\b', lower))
    has_intent = any(k in lower for k in [
        "plan", "planning", "ride", "doing", "custom", "replace",
        "gravel", "outdoor", "route", "road", "fondo", "century"
    ])
    return has_dist and has_intent

class WorkoutGenerateRequest(BaseModel):
    duration_min: Optional[int] = None
    intensity_adjust: Optional[int] = 0
    user_note: Optional[str] = ""
    temp_f: Optional[int] = 74
    humidity_pct: Optional[int] = 50
    gpx_content: Optional[str] = None
    gpx_filename: Optional[str] = None

class WorkoutSelectRequest(BaseModel):
    option_id: str

class OutdoorRecommendRequest(BaseModel):
    duration_min: int = 60
    user_note: Optional[str] = ""

class OutdoorSelectRequest(BaseModel):
    ride_id: str

class IntervalsPushRequest(BaseModel):
    target_date: Optional[str] = None

class ReplaceCustomRideRequest(BaseModel):
    description: Optional[str] = ""
    title: Optional[str] = ""
    distance_miles: Optional[float] = 0.0
    elevation_gain_ft: Optional[float] = 0.0
    duration_min: Optional[int] = 0
    intensity_type: Optional[str] = "Endurance"
    route_source: Optional[str] = "manual"
    summary_polyline: Optional[str] = ""
    svg_path: Optional[str] = ""
    map_points: Optional[list] = None
    temp_f: Optional[int] = 74
    humidity_pct: Optional[int] = 50
    is_outdoor: Optional[bool] = True

class FuelingPlanRequest(BaseModel):
    duration_min: Optional[int] = 60
    distance_miles: Optional[float] = 0.0
    avg_power_watts: Optional[int] = 0
    ftp: Optional[int] = 250
    intensity_type: Optional[str] = "Endurance"
    ride_title: Optional[str] = "Selected Ride"
    temp_f: Optional[int] = 74
    humidity_pct: Optional[int] = 50
    is_outdoor: Optional[bool] = True

# In-memory caches for active selection
CURRENT_OPTIONS_CACHE: Dict[str, Dict[str, Any]] = {}
CURRENT_WORKOUT_CACHE: Dict[str, Any] = {}
CURRENT_OUTDOOR_OPTIONS: Dict[str, Dict[str, Any]] = {}
CURRENT_OUTDOOR_CACHE: Dict[str, Any] = {}

@router.post("/generate")
def generate_workout(req: WorkoutGenerateRequest):
    demo_mode = get_setting("demo_mode", False)
    ftp = int(get_setting("athlete_ftp", 250))
    whoop_tokens = get_setting("whoop_tokens", None)
    
    # Retrieve latest recovery metrics
    today_strain = 0.0
    if whoop_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            whoop = {
                "recovery_score": int(row["recovery_score"]),
                "hrv_rmssd": float(row["hrv_rmssd"]),
                "sleep_performance": int(row["sleep_performance"] or 85),
                "day_strain": float(row["day_strain"] or 0.0)
            }
            today_strain = float(row["day_strain"] or 0.0)
        else:
            whoop = get_mock_whoop_data()
            today_strain = float(whoop.get("day_strain", 0.0))
    else:
        whoop = get_mock_whoop_data()
        today_strain = float(whoop.get("day_strain", 0.0))

    # Strava metrics
    strava_tokens = get_setting("strava_tokens", None)
    if strava_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM strava_activities ORDER BY start_date DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        recent_acts = [dict(r) for r in rows] if rows else get_mock_strava_activities()
    else:
        recent_acts = get_mock_strava_activities()

    rec_score = whoop.get("recovery_score", 50)
    hrv = whoop.get("hrv_rmssd", 35.0)
    sleep = whoop.get("sleep_performance", 85)
    
    total_sec = sum(a.get("moving_time_sec", 0) for a in recent_acts)
    vol_hours = round(total_sec / 3600.0, 1)

    # Detect activities completed today
    today_iso = datetime.date.today().isoformat()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_activities = []
    for a in recent_acts:
        start_str = a.get("start_date", "")
        if start_str.startswith(today_iso):
            today_activities.append(a)
        else:
            try:
                clean_ts = start_str.replace("Z", "+00:00")
                act_dt = datetime.datetime.fromisoformat(clean_ts)
                if (now_utc - act_dt).total_seconds() < 20 * 3600:
                    today_activities.append(a)
            except Exception:
                pass

    # Check recent intensity
    recent_high_intensity = False
    for a in recent_acts[:3]:
        if a.get("suffer_score", 0) > 70 or a.get("weighted_average_watts", 0) > (ftp * 0.88):
            recent_high_intensity = True

    # Retrieve trailing Strava stats (with recency decay)
    from app.services.strava_service import get_strava_trailing_stats
    strava_trailing = get_strava_trailing_stats(activities=recent_acts, days=7)
    vol_hours = float(strava_trailing.get("total_hours", vol_hours))
    total_tss = int(strava_trailing.get("total_tss", 0))
    acute_weighted_tss = int(strava_trailing.get("acute_weighted_tss", total_tss))
    yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))
    load_profile = strava_trailing.get("load_profile", "Evenly Distributed")

    # Retrieve trailing Whoop strain stats
    if whoop_tokens:
        from app.services.whoop_service import get_trailing_whoop_stats
        trailing_stats = get_trailing_whoop_stats(days=7)
        trailing_7d_strain_avg = float(trailing_stats.get("trailing_7d_strain_avg", 0.0))
        recent_weighted_strain = float(trailing_stats.get("recent_weighted_strain", 0.0))
        yesterday_strain = float(trailing_stats.get("yesterday_strain", 0.0))
        strain_profile = trailing_stats.get("strain_profile", "Evenly Distributed")
        trailing_7d_high_strain_count = int(trailing_stats.get("trailing_7d_high_strain_count", 0))
    else:
        trailing_7d_strain_avg = float(whoop.get("trailing_7d_strain_avg", 11.4))
        recent_weighted_strain = float(whoop.get("recent_weighted_strain", 12.1))
        yesterday_strain = float(whoop.get("yesterday_strain", 14.2))
        strain_profile = whoop.get("strain_profile", "Recent Surge (Yesterday Heavy)")
        trailing_7d_high_strain_count = int(whoop.get("trailing_7d_high_strain_days", 2))

    # Retrieve current program phase
    prog = get_current_program(strava_weekly_tss=acute_weighted_tss or total_tss or 300)
    phase_str = prog.get("phase", "Build Phase")

    # Retrieve athlete day target duration preferences
    from app.services.preferences_service import get_day_target_config
    day_cfg = get_day_target_config()
    target_dur = day_cfg.get("preferred_duration_min", 45) if req.duration_min is None else req.duration_min

    # Generate bundle (Primary + 2 Alternatives) with dual-load modeling
    bundle = build_workout_bundle(
        recovery_score=rec_score,
        hrv_rmssd=hrv,
        sleep_score=sleep,
        recent_volume_hours=vol_hours,
        recent_high_intensity=recent_high_intensity,
        target_duration_min=target_dur,
        ftp=ftp,
        user_note=req.user_note,
        program_phase=phase_str,
        today_strain=today_strain,
        today_activities=today_activities,
        trailing_7d_strain_avg=trailing_7d_strain_avg,
        trailing_7d_high_strain_count=trailing_7d_high_strain_count,
        recent_weighted_strain=recent_weighted_strain,
        yesterday_strain=yesterday_strain,
        total_tss=total_tss,
        acute_weighted_tss=acute_weighted_tss,
        yesterday_tss=yesterday_tss,
        load_profile=load_profile,
        strain_profile=strain_profile
    )

    # Apply intensity adjustment if requested
    if req.intensity_adjust and req.intensity_adjust != 0:
        multiplier = 1.0 + (req.intensity_adjust / 100.0)
        for w in bundle["all_options"]:
            for interval in w.get("intervals", []):
                if "power_pct" in interval:
                    interval["power_pct"] = max(40, int(interval["power_pct"] * multiplier))
                if "on_power_pct" in interval:
                    interval["on_power_pct"] = max(45, int(interval["on_power_pct"] * multiplier))
                if "power_low_pct" in interval:
                    interval["power_low_pct"] = max(35, int(interval["power_low_pct"] * multiplier))
                if "power_high_pct" in interval:
                    interval["power_high_pct"] = max(45, int(interval["power_high_pct"] * multiplier))
            if w.get("estimated_tss", 0) > 0:
                base_tss = w.get("base_estimated_tss") or w["estimated_tss"]
                w["base_estimated_tss"] = base_tss
                # TSS scales with normalized power squared: TSS' = TSS * (multiplier ** 2)
                w["estimated_tss"] = max(5, round(base_tss * (multiplier ** 2)))
            w["ai_rationale"] += f" [Intensity scaled by {req.intensity_adjust:+d}%]"
            w["zwo_content"] = generate_zwo_xml(w, ftp)
            w["intervals_icu_text"] = generate_intervals_icu_text(w)

    # Check if a workout was scheduled with the coach for today
    from app.database import get_scheduled_workout_for_date
    scheduled_today = get_scheduled_workout_for_date(today_iso)
    if scheduled_today:
        scheduled_today["badge"] = "💬 Coach Scheduled"
        scheduled_today["badge_color"] = "cyan"
        if not scheduled_today.get("zwo_content"):
            scheduled_today["zwo_content"] = generate_zwo_xml(scheduled_today, ftp)
        if not scheduled_today.get("intervals_icu_text"):
            scheduled_today["intervals_icu_text"] = generate_intervals_icu_text(scheduled_today)
        bundle["primary"] = scheduled_today
        bundle["all_options"] = [scheduled_today] + [o for o in bundle["all_options"] if o["id"] != scheduled_today["id"]]

    CURRENT_OPTIONS_CACHE.clear()
    for opt in bundle["all_options"]:
        CURRENT_OPTIONS_CACHE[opt["id"]] = opt

    primary_workout = bundle["primary"]
    CURRENT_WORKOUT_CACHE.clear()
    CURRENT_WORKOUT_CACHE.update(primary_workout)

    # Check if user describes planning a custom ride or uploaded a route
    if req.gpx_content or (req.user_note and is_planned_custom_ride_description(req.user_note)):
        custom_req = ReplaceCustomRideRequest(
            description=req.user_note or "",
            temp_f=req.temp_f or 74,
            humidity_pct=req.humidity_pct or 50,
            is_outdoor=True
        )
        if req.gpx_content:
            from app.services.plan_service import parse_gpx_content
            parsed_gpx = parse_gpx_content(req.gpx_content, req.gpx_filename or "Uploaded Route.gpx")
            if parsed_gpx.get("success"):
                custom_req.distance_miles = parsed_gpx.get("distance_miles")
                custom_req.elevation_gain_ft = parsed_gpx.get("elevation_gain_ft")
                custom_req.duration_min = parsed_gpx.get("estimated_duration_min")
                custom_req.title = parsed_gpx.get("title")
                custom_req.svg_path = parsed_gpx.get("svg_path")
                custom_req.map_points = parsed_gpx.get("map_points")
                custom_req.route_source = "gpx_upload"

        replaced = replace_with_custom_ride(custom_req)
        return {
            "active_workout": replaced["active_workout"],
            "options": [replaced["active_workout"]] + [o for o in bundle["all_options"] if o["id"] != replaced["active_workout"]["id"]],
            "fueling_plan": replaced["fueling_plan"],
            "is_custom_replaced": True
        }

    return {
        "active_workout": primary_workout,
        "options": bundle["all_options"]
    }

@router.post("/select")
def select_workout_option(req: WorkoutSelectRequest):
    if req.option_id in CURRENT_OPTIONS_CACHE:
        selected = CURRENT_OPTIONS_CACHE[req.option_id]
        CURRENT_WORKOUT_CACHE.clear()
        CURRENT_WORKOUT_CACHE.update(selected)

        ftp = int(get_setting("athlete_ftp", 250))
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
        whoop_row = c.fetchone()
        conn.close()
        rec_score = int(whoop_row["recovery_score"]) if whoop_row else 50
        strava_trailing = get_strava_trailing_stats(days=7)
        trailing_strain = float(strava_trailing.get("trailing_7d_strain_avg", 11.0))
        yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))

        fueling = generate_fueling_plan(
            duration_min=int(selected.get("duration_minutes") or 60),
            distance_miles=float(selected.get("distance_miles") or 0.0),
            avg_power_watts=round(ftp * 0.68),
            ftp=ftp,
            intensity_type=selected.get("focus_area", "Endurance"),
            ride_title=selected.get("title", "Selected Workout"),
            athlete_weight_kg=70.0,
            temp_f=74,
            humidity_pct=50,
            is_outdoor=False,
            recovery_score=rec_score,
            trailing_strain_avg=trailing_strain,
            yesterday_tss=yesterday_tss
        )

        return {
            "success": True,
            "active_workout": selected,
            "options": list(CURRENT_OPTIONS_CACHE.values()),
            "fueling_plan": fueling
        }
    raise HTTPException(status_code=404, detail="Option not found in current session")

@router.get("/current")
def get_current_workout():
    today_iso = datetime.date.today().isoformat()
    from app.database import get_scheduled_workout_for_date
    scheduled = get_scheduled_workout_for_date(today_iso)
    if scheduled and (not CURRENT_WORKOUT_CACHE or CURRENT_WORKOUT_CACHE.get("id") != scheduled.get("id")):
        return generate_workout(WorkoutGenerateRequest(duration_min=scheduled.get("duration_minutes", 60)))

    if CURRENT_WORKOUT_CACHE:
        return {
            "active_workout": CURRENT_WORKOUT_CACHE,
            "options": list(CURRENT_OPTIONS_CACHE.values())
        }
    return generate_workout(WorkoutGenerateRequest(duration_min=60))

@router.get("/scheduled")
def get_scheduled_workouts_endpoint():
    """Returns all workouts scheduled for today and upcoming dates."""
    from app.database import get_upcoming_scheduled_workouts
    today_iso = datetime.date.today().isoformat()
    workouts = get_upcoming_scheduled_workouts(today_iso)
    return {
        "success": True,
        "scheduled_workouts": workouts
    }

@router.post("/replace-custom")
def replace_with_custom_ride(req: ReplaceCustomRideRequest):
    """
    Replaces the daily prescribed ride/workout with a custom ride,
    either from natural description or uploaded route, and generates its fueling plan.
    """
    ftp = int(get_setting("athlete_ftp", 250))
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
    whoop_row = c.fetchone()
    conn.close()
    
    if whoop_row:
        rec_score = int(whoop_row["recovery_score"])
    else:
        whoop = get_mock_whoop_data()
        rec_score = int(whoop.get("recovery_score", 50))
        
    strava_trailing = get_strava_trailing_stats(days=7)
    trailing_strain = float(strava_trailing.get("trailing_7d_strain_avg", 11.0))
    yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))

    desc = req.description or ""
    dist = float(req.distance_miles or 0.0)
    elev = float(req.elevation_gain_ft or 0.0)
    dur = int(req.duration_min or 0)
    title = req.title or ""
    intensity = req.intensity_type or "Endurance"

    if desc and dist <= 0:
        from app.services.plan_service import parse_plan_description
        parsed = parse_plan_description(desc)
        dist = float(parsed.get("distance_miles") or 40.0)
        elev = float(parsed.get("elevation_gain_ft") or 2000.0)
        dur = int(parsed.get("estimated_duration_min") or round(dist / 17.5 * 60))
        title = title or parsed.get("title") or f"Custom {dist:.0f}-Mile Planned Ride"
        intensity = intensity or parsed.get("intensity_type") or "Endurance"

    if dist <= 0:
        dist = 40.0
    if dur <= 0:
        dur = max(30, round(dist / 17.5 * 60))
    if not title:
        title = f"Custom {dist:.0f}-Mile Planned Ride"

    est_tss = max(20, round(dur * 0.65))

    # Calculate physiological target power based on Whoop recovery
    if rec_score < 40:
        base_pct = 62 # Zone 2 strictly, glycogen sparing
        pacing_label = f"Zone 2 Aerobic Base (Glycogen Protection, {round(ftp * 0.62)}W)"
    elif rec_score >= 67 and ("tempo" in intensity.lower() or "group" in intensity.lower()):
        base_pct = 72
        pacing_label = f"Tempo Pacing ({round(ftp * 0.72)}W)"
    else:
        base_pct = 67
        pacing_label = f"Endurance Simulation ({round(ftp * 0.67)}W)"

    warmup_s = 480
    cd_s = 300
    rem_s = max(300, (dur * 60) - warmup_s - cd_s)

    if dur >= 75 and rec_score >= 40:
        part1 = round(rem_s * 0.40)
        part2 = round(rem_s * 0.35)
        part3 = rem_s - part1 - part2
        tempo_pct = 78 if rec_score >= 67 else 72
        intervals = [
            {"type": "Warmup", "duration_sec": warmup_s, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Dynamic Warmup"},
            {"type": "SteadyState", "duration_sec": part1, "power_pct": base_pct, "cadence": 90, "name": f"Aerobic Base ({dist * 0.4:.1f} mi)"},
            {"type": "SteadyState", "duration_sec": part2, "power_pct": tempo_pct, "cadence": 92, "name": f"Rolling Terrain Block ({dist * 0.35:.1f} mi)"},
            {"type": "SteadyState", "duration_sec": part3, "power_pct": base_pct, "cadence": 88, "name": f"Sustained Cruise ({dist * 0.25:.1f} mi)"},
            {"type": "Cooldown", "duration_sec": cd_s, "power_low_pct": 60, "power_high_pct": 45, "cadence": 82, "name": "Cooldown Spin"}
        ]
    else:
        intervals = [
            {"type": "Warmup", "duration_sec": warmup_s, "power_low_pct": 50, "power_high_pct": 65, "cadence": 88, "name": "Dynamic Warmup"},
            {"type": "SteadyState", "duration_sec": rem_s, "power_pct": base_pct, "cadence": 90, "name": f"{pacing_label} ({dist:.1f} mi)"},
            {"type": "Cooldown", "duration_sec": cd_s, "power_low_pct": 60, "power_high_pct": 45, "cadence": 82, "name": "Cooldown Spin"}
        ]

    fueling = generate_fueling_plan(
        duration_min=dur,
        distance_miles=dist,
        avg_power_watts=round(ftp * (base_pct / 100.0)),
        ftp=ftp,
        intensity_type=intensity,
        ride_title=title,
        athlete_weight_kg=70.0,
        temp_f=int(req.temp_f or 74),
        humidity_pct=int(req.humidity_pct or 50),
        is_outdoor=req.is_outdoor,
        recovery_score=rec_score,
        trailing_strain_avg=trailing_strain,
        yesterday_tss=yesterday_tss
    )

    rationale_parts = [
        f"Custom Planned Ride: Replaced today's prescription with '{title}' ({dist:.1f} mi, est. {dur} min, {est_tss} TSS)."
    ]
    if rec_score < 40:
        rationale_parts.append(
            f"Whoop Recovery Alert ({rec_score}%): Autonomic readiness is low. "
            f"Pacing is capped strictly in Zone 2 ({round(ftp * (base_pct / 100.0))}W) to protect fatigued muscles, "
            f"and target fueling is boosted to {fueling['target_rates']['carbs_per_hour_g']}g/hr carbs to spare depleted glycogen reserves."
        )
    elif rec_score >= 67:
        rationale_parts.append(
            f"Whoop Recovery ({rec_score}%): High physiological readiness. Pacing calibrated at {round(ftp * (base_pct / 100.0))}W with optimal carb oxidation."
        )
    else:
        rationale_parts.append(
            f"Whoop Recovery ({rec_score}%): Moderate readiness. Steady aerobic endurance pacing recommended."
        )

    if trailing_strain >= 13.5 or yesterday_tss >= 80:
        rationale_parts.append(
            f"Trailing Load Impact: 7-day strain average ({trailing_strain:.1f}) and yesterday's TSS ({yesterday_tss}) indicate acute residual fatigue. "
            f"Pre-ride meal target increased to {fueling['pre_ride']['target_carbs_g']}g carbs."
        )

    if req.is_outdoor and (int(req.temp_f or 74) >= 78 or int(req.humidity_pct or 50) >= 55):
        rationale_parts.append(
            f"Weather Calibration: Outdoor conditions ({req.temp_f}°F, {req.humidity_pct}% humidity) elevate sweat rate. "
            f"Fluid intake scaled to {fueling['target_rates']['fluid_ml_per_hour']} ml/hr with {fueling['target_rates']['sodium_mg_per_hour']} mg/hr sodium."
        )

    ai_rationale = " ".join(rationale_parts)

    custom_workout = {
        "id": "workout_custom_replaced",
        "option_type": "custom",
        "badge": "✨ Custom Replaced Ride",
        "badge_color": "cyan",
        "title": title,
        "description": f"Custom {dist:.1f}-mile planned ride ({dur} min, {elev:.0f} ft climbing)",
        "focus_area": f"{dist:.1f} Miles • {intensity}",
        "duration_minutes": dur,
        "distance_miles": dist,
        "elevation_gain_ft": elev,
        "estimated_tss": est_tss,
        "summary_polyline": req.summary_polyline or "",
        "svg_path": req.svg_path or "",
        "map_points": req.map_points or [],
        "route_source": req.route_source or "manual",
        "ai_rationale": ai_rationale,
        "intervals": intervals
    }
    custom_workout["zwo_content"] = generate_zwo_xml(custom_workout, ftp)
    custom_workout["intervals_icu_text"] = generate_intervals_icu_text(custom_workout)

    CURRENT_WORKOUT_CACHE.clear()
    CURRENT_WORKOUT_CACHE.update(custom_workout)
    CURRENT_OUTDOOR_CACHE.clear()
    CURRENT_OUTDOOR_CACHE.update(custom_workout)
    CURRENT_OPTIONS_CACHE["workout_custom_replaced"] = custom_workout

    return {
        "success": True,
        "message": f"Ride replaced with '{title}' ({dist:.1f} mi). Fueling plan generated!",
        "active_workout": custom_workout,
        "fueling_plan": fueling
    }

@router.post("/fueling-plan")
def get_custom_fueling_plan(req: FuelingPlanRequest):
    """Generates sports-science fueling strategy for specific ride and environmental conditions."""
    ftp = int(get_setting("athlete_ftp", req.ftp or 250))
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
    whoop_row = c.fetchone()
    conn.close()
    
    rec_score = int(whoop_row["recovery_score"]) if whoop_row else 50
    strava_trailing = get_strava_trailing_stats(days=7)
    trailing_strain = float(strava_trailing.get("trailing_7d_strain_avg", 11.0))
    yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))

    plan = generate_fueling_plan(
        duration_min=req.duration_min or 60,
        distance_miles=req.distance_miles,
        avg_power_watts=req.avg_power_watts,
        ftp=ftp,
        intensity_type=req.intensity_type or "Endurance",
        ride_title=req.ride_title or "Selected Ride",
        athlete_weight_kg=70.0,
        temp_f=int(req.temp_f or 74),
        humidity_pct=int(req.humidity_pct or 50),
        is_outdoor=req.is_outdoor if req.is_outdoor is not None else True,
        recovery_score=rec_score,
        trailing_strain_avg=trailing_strain,
        yesterday_tss=yesterday_tss
    )
    return plan

@router.get("/fueling-plan")
def get_active_fueling_plan(temp_f: int = 74, humidity_pct: int = 50, is_outdoor: bool = True):
    """Returns fueling plan for current active workout/ride."""
    workout = CURRENT_WORKOUT_CACHE or CURRENT_OUTDOOR_CACHE or CURRENT_OPTIONS_CACHE.get("workout_primary")
    if not workout:
        gen = generate_workout(WorkoutGenerateRequest(duration_min=60))
        workout = gen["active_workout"]
        
    dur = int(workout.get("duration_minutes") or workout.get("moving_time_min") or (workout.get("moving_time_sec", 3600) // 60) or 60)
    dist = float(workout.get("distance_miles") or (round(workout.get("distance_km", 0.0) * 0.621371, 1) if workout.get("distance_km") else 0.0))
    title = workout.get("title") or workout.get("name") or "Selected Ride"
    intensity = workout.get("focus_area") or workout.get("target_zone") or "Endurance"
    ftp = int(get_setting("athlete_ftp", 250))

    return get_custom_fueling_plan(FuelingPlanRequest(
        duration_min=dur,
        distance_miles=dist,
        ride_title=title,
        intensity_type=intensity,
        temp_f=temp_f,
        humidity_pct=humidity_pct,
        is_outdoor=is_outdoor,
        ftp=ftp
    ))

@router.get("/download-zwo")
def download_zwo_file():
    workout = CURRENT_WORKOUT_CACHE or CURRENT_OPTIONS_CACHE.get("workout_primary")
    if not workout:
        gen = generate_workout(WorkoutGenerateRequest(duration_min=60))
        workout = gen["active_workout"]
        
    zwo_content = workout.get("zwo_content", "")
    title = workout.get("title", "PowerSync_Workout").replace(" ", "_")
    filename = f"{title}.zwo"
    
    return Response(
        content=zwo_content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.post("/push-intervals-icu")
def push_to_zwift_via_intervals(req: IntervalsPushRequest):
    athlete_id = get_setting("intervals_athlete_id", "")
    api_key = get_setting("intervals_icu_api_key", "")
    
    if not athlete_id or not api_key or "•" in api_key or "\u2022" in api_key:
        return {
            "success": False,
            "error": "Intervals.icu API Key is unconfigured or needs to be re-entered. Please open Settings (⚙️) and enter your Intervals.icu API Key to enable direct Zwift sync."
        }
        
    workout = CURRENT_WORKOUT_CACHE or CURRENT_OPTIONS_CACHE.get("workout_primary")
    if not workout:
        gen = generate_workout(WorkoutGenerateRequest(duration_min=60))
        workout = gen["active_workout"]
        
    target_date = req.target_date or datetime.date.today().isoformat()
    ftp = int(get_setting("athlete_ftp", 250))
    result = push_to_intervals_icu(athlete_id, api_key, workout, target_date, ftp=ftp)
    return result

@router.post("/outdoor-recommendation")
def generate_outdoor_recommendation(req: OutdoorRecommendRequest):
    ftp = int(get_setting("athlete_ftp", 250))
    whoop_tokens = get_setting("whoop_tokens", None)
    
    today_strain = 0.0
    if whoop_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            whoop = {
                "recovery_score": int(row["recovery_score"]),
                "hrv_rmssd": float(row["hrv_rmssd"]),
                "sleep_performance": int(row["sleep_performance"] or 85),
                "day_strain": float(row["day_strain"] or 0.0)
            }
            today_strain = float(row["day_strain"] or 0.0)
        else:
            whoop = get_mock_whoop_data()
            today_strain = float(whoop.get("day_strain", 0.0))
    else:
        whoop = get_mock_whoop_data()
        today_strain = float(whoop.get("day_strain", 0.0))

    strava_tokens = get_setting("strava_tokens", None)
    if strava_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM strava_activities ORDER BY start_date DESC LIMIT 15")
        rows = c.fetchall()
        conn.close()
        recent_acts = [dict(r) for r in rows] if rows else get_mock_strava_activities()
    else:
        recent_acts = get_mock_strava_activities()

    rec_score = whoop.get("recovery_score", 50)
    hrv = whoop.get("hrv_rmssd", 35.0)
    sleep = whoop.get("sleep_performance", 85)
    
    total_sec = sum(a.get("moving_time_sec", 0) for a in recent_acts)
    vol_hours = round(total_sec / 3600.0, 1)

    today_iso = datetime.date.today().isoformat()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_activities = []
    for a in recent_acts:
        start_str = a.get("start_date", "")
        if start_str.startswith(today_iso):
            today_activities.append(a)
        else:
            try:
                clean_ts = start_str.replace("Z", "+00:00")
                act_dt = datetime.datetime.fromisoformat(clean_ts)
                if (now_utc - act_dt).total_seconds() < 20 * 3600:
                    today_activities.append(a)
            except Exception:
                pass

    recent_high_intensity = False
    for a in recent_acts[:3]:
        if a.get("suffer_score", 0) > 70 or a.get("weighted_average_watts", 0) > (ftp * 0.88):
            recent_high_intensity = True

    # Retrieve trailing Strava stats (with recency decay)
    from app.services.strava_service import get_strava_trailing_stats
    strava_trailing = get_strava_trailing_stats(activities=recent_acts, days=7)
    vol_hours = float(strava_trailing.get("total_hours", vol_hours))
    total_tss = int(strava_trailing.get("total_tss", 0))
    acute_weighted_tss = int(strava_trailing.get("acute_weighted_tss", total_tss))
    yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))
    load_profile = strava_trailing.get("load_profile", "Evenly Distributed")

    if whoop_tokens:
        from app.services.whoop_service import get_trailing_whoop_stats
        trailing_stats = get_trailing_whoop_stats(days=7)
        trailing_7d_strain_avg = float(trailing_stats.get("trailing_7d_strain_avg", 0.0))
        recent_weighted_strain = float(trailing_stats.get("recent_weighted_strain", 0.0))
        yesterday_strain = float(trailing_stats.get("yesterday_strain", 0.0))
        strain_profile = trailing_stats.get("strain_profile", "Evenly Distributed")
        trailing_7d_high_strain_count = int(trailing_stats.get("trailing_7d_high_strain_count", 0))
    else:
        trailing_7d_strain_avg = float(whoop.get("trailing_7d_strain_avg", 11.4))
        recent_weighted_strain = float(whoop.get("recent_weighted_strain", 12.1))
        yesterday_strain = float(whoop.get("yesterday_strain", 14.2))
        strain_profile = whoop.get("strain_profile", "Recent Surge (Yesterday Heavy)")
        trailing_7d_high_strain_count = int(whoop.get("trailing_7d_high_strain_days", 2))

    from app.services.outdoor_coach import build_outdoor_ride_recommendation
    outdoor_bundle = build_outdoor_ride_recommendation(
        recovery_score=rec_score,
        hrv_rmssd=hrv,
        sleep_score=sleep,
        recent_volume_hours=vol_hours,
        recent_high_intensity=recent_high_intensity,
        today_strain=today_strain,
        trailing_7d_strain_avg=trailing_7d_strain_avg,
        trailing_7d_high_strain_count=trailing_7d_high_strain_count,
        recent_weighted_strain=recent_weighted_strain,
        yesterday_strain=yesterday_strain,
        total_tss=total_tss,
        acute_weighted_tss=acute_weighted_tss,
        yesterday_tss=yesterday_tss,
        load_profile=load_profile,
        strain_profile=strain_profile,
        target_duration_min=req.duration_min,
        ftp=ftp,
        user_note=req.user_note or "",
        today_activities=today_activities
    )

    CURRENT_OUTDOOR_OPTIONS.clear()
    for opt in outdoor_bundle["all_options"]:
        CURRENT_OUTDOOR_OPTIONS[opt["id"]] = opt

    primary_ride = outdoor_bundle["primary"]
    CURRENT_OUTDOOR_CACHE.clear()
    CURRENT_OUTDOOR_CACHE.update(primary_ride)

    ftp = int(get_setting("athlete_ftp", 250))
    outdoor_fueling = generate_fueling_plan(
        duration_min=int(primary_ride.get("moving_time_min") or (primary_ride.get("moving_time_sec", 3600) // 60) or 60),
        distance_miles=float(primary_ride.get("distance_miles") or (round(primary_ride.get("distance_km", 0.0) * 0.621371, 1) if primary_ride.get("distance_km") else 25.0)),
        avg_power_watts=int(primary_ride.get("average_watts") or round(ftp * 0.68)),
        ftp=ftp,
        intensity_type=primary_ride.get("target_zone") or primary_ride.get("zone") or "Zone 2 Aerobic Base",
        ride_title=primary_ride.get("name", "Recommended Outdoor Route"),
        athlete_weight_kg=70.0,
        temp_f=78,
        humidity_pct=60,
        is_outdoor=True,
        recovery_score=rec_score,
        trailing_strain_avg=trailing_7d_strain_avg,
        yesterday_tss=yesterday_tss
    )

    return {
        "success": True,
        "active_ride": primary_ride,
        "options": outdoor_bundle["all_options"],
        "all_routes": outdoor_bundle["all_routes"],
        "telemetry": outdoor_bundle["telemetry"],
        "fueling_plan": outdoor_fueling
    }

@router.get("/outdoor-recommendation")
def get_outdoor_recommendation(duration_min: int = 60, user_note: str = ""):
    return generate_outdoor_recommendation(OutdoorRecommendRequest(duration_min=duration_min, user_note=user_note))

@router.post("/select-outdoor")
def select_outdoor_option(req: OutdoorSelectRequest):
    target_id = str(req.ride_id).strip("'\"")
    
    ftp = int(get_setting("athlete_ftp", 250))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
    whoop_row = c.fetchone()
    conn.close()
    rec_score = int(whoop_row["recovery_score"]) if whoop_row else 50
    strava_trailing = get_strava_trailing_stats(days=7)
    trailing_strain = float(strava_trailing.get("trailing_7d_strain_avg", 11.0))
    yesterday_tss = int(strava_trailing.get("yesterday_tss", 0))

    def make_fueling(ride_dict):
        return generate_fueling_plan(
            duration_min=int(ride_dict.get("moving_time_min") or (ride_dict.get("moving_time_sec", 3600) // 60) or 60),
            distance_miles=float(ride_dict.get("distance_miles") or (round(ride_dict.get("distance_km", 0.0) * 0.621371, 1) if ride_dict.get("distance_km") else 25.0)),
            avg_power_watts=int(ride_dict.get("average_watts") or round(ftp * 0.68)),
            ftp=ftp,
            intensity_type=ride_dict.get("target_zone") or ride_dict.get("zone") or "Zone 2 Aerobic Base",
            ride_title=ride_dict.get("name", "Selected Outdoor Route"),
            athlete_weight_kg=70.0,
            temp_f=78,
            humidity_pct=60,
            is_outdoor=True,
            recovery_score=rec_score,
            trailing_strain_avg=trailing_strain,
            yesterday_tss=yesterday_tss
        )

    # 1. Check in CURRENT_OUTDOOR_OPTIONS with flexible key matching
    for k, v in list(CURRENT_OUTDOOR_OPTIONS.items()):
        if str(k).strip("'\"") == target_id or str(v.get("id")).strip("'\"") == target_id:
            CURRENT_OUTDOOR_CACHE.clear()
            CURRENT_OUTDOOR_CACHE.update(v)
            return {
                "success": True,
                "active_ride": v,
                "options": list(CURRENT_OUTDOOR_OPTIONS.values()),
                "fueling_plan": make_fueling(v)
            }

    # 2. Cache might have cleared (e.g. server auto-reload) -> Regenerate
    rec = generate_outdoor_recommendation(OutdoorRecommendRequest(duration_min=60))
    for k, v in list(CURRENT_OUTDOOR_OPTIONS.items()):
        if str(k).strip("'\"") == target_id or str(v.get("id")).strip("'\"") == target_id:
            CURRENT_OUTDOOR_CACHE.clear()
            CURRENT_OUTDOOR_CACHE.update(v)
            return {
                "success": True,
                "active_ride": v,
                "options": list(CURRENT_OUTDOOR_OPTIONS.values()),
                "fueling_plan": make_fueling(v)
            }

    # 3. Search in all_routes fallback
    for r in rec.get("all_routes", []):
        if str(r.get("id")).strip("'\"") == target_id:
            CURRENT_OUTDOOR_CACHE.clear()
            CURRENT_OUTDOOR_CACHE.update(r)
            return {
                "success": True,
                "active_ride": r,
                "options": rec.get("options", []),
                "fueling_plan": make_fueling(r)
            }

    raise HTTPException(status_code=404, detail=f"Outdoor ride option {target_id} not found")


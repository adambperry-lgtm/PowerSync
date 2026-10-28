from fastapi import APIRouter, Request
import datetime
from app.database import get_setting, get_db_connection, get_current_user_id, get_user_by_id, get_athlete_date
from app.services.mock_data import get_mock_whoop_data, get_mock_strava_activities, get_mock_weekly_stats
from app.services.program_service import get_current_program

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("")
def get_dashboard_data(request: Request = None):
    uid = get_current_user_id()
    current_user = None
    if request and hasattr(request, "state"):
        current_user = getattr(request.state, "user", None)
    if not current_user:
        current_user = get_user_by_id(uid) or {}
    
    whoop_tokens = get_setting("whoop_tokens", None, user_id=uid)
    strava_tokens = get_setting("strava_tokens", None, user_id=uid)
    
    # If athlete has connected real tokens, demo_mode is always False
    demo_mode_setting = get_setting("demo_mode", False, user_id=uid)
    demo_mode = False if (whoop_tokens or strava_tokens) else bool(demo_mode_setting)
    
    ftp = get_setting("athlete_ftp", 250, user_id=uid)
    max_hr = get_setting("athlete_max_hr", 185, user_id=uid)
    gemini_key = get_setting("gemini_api_key", "", user_id=uid)
    intervals_icu_key = get_setting("intervals_icu_api_key", "", user_id=uid)
    intervals_athlete_id = get_setting("intervals_athlete_id", "", user_id=uid)
    
    # Whoop Data: prioritize athlete's private whoop_metrics table records
    today_iso = get_athlete_date().isoformat()
    whoop_auth_expired = False
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (uid,))
    row = c.fetchone()
    if not row and uid == "usr_guest":
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = 'usr_default' ORDER BY date DESC LIMIT 1")
        row = c.fetchone()
    conn.close()

    whoop_tokens = get_setting("whoop_tokens", {}, user_id=uid)
    if not whoop_tokens and uid == "usr_guest":
        whoop_tokens = get_setting("whoop_tokens", {}, user_id="usr_default")

    # Auto-sync live Whoop metrics if:
    # 1. Athlete has connected Whoop tokens AND:
    # 2. No record exists for today OR today's recovery is unfinalized (missing/0) OR
    # 3. More than 15 minutes have elapsed since last sync
    last_whoop_sync_key = "last_whoop_sync_timestamp"
    last_whoop_sync_time = float(get_setting(last_whoop_sync_key, 0.0, user_id=uid) or 0.0)
    if not last_whoop_sync_time and uid == "usr_guest":
        last_whoop_sync_time = float(get_setting(last_whoop_sync_key, 0.0, user_id="usr_default") or 0.0)
    now_ts = datetime.datetime.now().timestamp()

    needs_whoop_sync = False
    if whoop_tokens:
        if not row or row["date"] != today_iso:
            needs_whoop_sync = True
        elif not row["recovery_score"] or row["recovery_score"] <= 0:
            needs_whoop_sync = True
        elif (now_ts - last_whoop_sync_time) > 120:  # 2 minutes auto-sync window
            needs_whoop_sync = True

    if needs_whoop_sync:
        try:
            from app.services.whoop_service import fetch_latest_whoop_metrics
            sync_res = fetch_latest_whoop_metrics(user_id=uid)
            if sync_res.get("success"):
                set_setting(last_whoop_sync_key, now_ts, user_id=uid)
                if uid == "usr_guest":
                    set_setting(last_whoop_sync_key, now_ts, user_id="usr_default")
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (uid,))
                row = c.fetchone()
                if not row and uid == "usr_guest":
                    c.execute("SELECT * FROM whoop_metrics WHERE user_id = 'usr_default' ORDER BY date DESC LIMIT 1")
                    row = c.fetchone()
                conn.close()
            elif sync_res.get("auth_expired"):
                whoop_auth_expired = True
        except Exception as e:
            print(f"[PowerSync] Whoop auto-sync error in dashboard: {e}")

    if row:
        from app.services.whoop_service import get_trailing_whoop_stats
        trailing_stats = get_trailing_whoop_stats(days=7, user_id=uid)
        is_today = (row["date"] == today_iso)
        whoop_data = {
            "date": row["date"],
            "is_today": is_today,
            "auth_expired": whoop_auth_expired,
            "recovery_score": int(row["recovery_score"]),
            "recovery_zone": "green" if row["recovery_score"] > 66 else ("yellow" if row["recovery_score"] >= 34 else "red"),
            "hrv_rmssd": round(float(row["hrv_rmssd"]), 1) if row["hrv_rmssd"] is not None else 40.0,
            "resting_heart_rate": int(row["resting_heart_rate"]) if row["resting_heart_rate"] is not None else 60,
            "sleep_performance": int(row["sleep_performance"] or 85),
            "sleep_duration_hours": round(float(row["sleep_duration_hours"] or 7.5), 1),
            "day_strain": round(float(row["day_strain"] or 0.0), 1),
            "trailing_7d_strain_avg": trailing_stats.get("trailing_7d_strain_avg", 0.0),
            "recent_weighted_strain": trailing_stats.get("recent_weighted_strain", 0.0),
            "yesterday_strain": trailing_stats.get("yesterday_strain", 0.0),
            "strain_profile": trailing_stats.get("strain_profile", "Evenly Distributed"),
            "trailing_7d_high_strain_days": trailing_stats.get("trailing_7d_high_strain_count", 0),
            "trailing_strains": trailing_stats.get("trailing_strains", []),
            "trends": {
                "hrv_vs_baseline": f"{round(float(row['hrv_rmssd']), 1)} ms" if row["hrv_rmssd"] is not None else "--",
                "rhr_vs_baseline": f"{int(row['resting_heart_rate'])} bpm" if row["resting_heart_rate"] is not None else "--",
                "sleep_consistency": "Synced Today" if is_today else f"Last: {row['date']}"
            }
        }
        whoop_connected = bool(whoop_tokens)
    else:
        whoop_data = get_mock_whoop_data()
        whoop_data["auth_expired"] = whoop_auth_expired
        whoop_connected = bool(whoop_tokens)

    # Strava Data: prioritize athlete's private strava_activities table records
    from app.services.strava_service import get_strava_trailing_stats, fetch_recent_strava_activities
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 30", (uid,))
    rows = c.fetchall()
    if not rows and uid == "usr_guest":
        c.execute("SELECT * FROM strava_activities WHERE user_id = 'usr_default' ORDER BY start_date DESC LIMIT 30")
        rows = c.fetchall()
    conn.close()

    strava_tokens = get_setting("strava_tokens", {}, user_id=uid)
    if not strava_tokens and uid == "usr_guest":
        strava_tokens = get_setting("strava_tokens", {}, user_id="usr_default")

    # Auto-sync live Strava activities if athlete has connected tokens and no activity today (or 10m elapsed)
    if strava_tokens:
        has_today = any(dict(r).get("start_date", "").startswith(today_iso) for r in rows)
        last_sync_key = "last_strava_sync_timestamp"
        last_sync_time = float(get_setting(last_sync_key, 0.0, user_id=uid))
        now_ts = datetime.datetime.now().timestamp()
        if (not has_today) or (now_ts - last_sync_time > 600):
            try:
                synced = fetch_recent_strava_activities(limit=15, user_id=uid)
                if synced:
                    set_setting(last_sync_key, now_ts, user_id=uid)
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 30", (uid,))
                    rows = c.fetchall()
                    if not rows and uid == "usr_guest":
                        c.execute("SELECT * FROM strava_activities WHERE user_id = 'usr_default' ORDER BY start_date DESC LIMIT 30")
                        rows = c.fetchall()
                    conn.close()
            except Exception:
                pass

    if rows:
        activities = [dict(r) for r in rows]
    else:
        activities = get_mock_strava_activities()
    weekly_stats = get_strava_trailing_stats(activities=activities, days=7, user_id=uid)
    strava_connected = bool(strava_tokens)

    from app.services.strain_model_service import calculate_trailing_strain_systems, calculate_activity_strain
    w_prime_kj = float(get_setting("athlete_w_prime_kj", 20.0))
    peak_power = int(get_setting("athlete_peak_power_watts", 1050))
    strain_systems = calculate_trailing_strain_systems(activities=activities, days=7, ftp=ftp)

    # Enrich all activities with 3-tier physiological strain and battery depletion
    enriched_activities = []
    from app.services.strava_service import resolve_strava_local_start
    for act in activities:
        act_copy = dict(act)
        local_start = resolve_strava_local_start(act_copy, user_id=uid)
        if local_start:
            act_copy["start_date"] = local_start
        act_strain = calculate_activity_strain(act_copy, ftp=ftp)
        act_copy["total_xss"] = act_strain.get("total_xss", 0.0)
        act_copy["low_xss"] = act_strain.get("low_xss", 0.0)
        act_copy["high_xss"] = act_strain.get("high_xss", 0.0)
        act_copy["peak_xss"] = act_strain.get("peak_xss", 0.0)
        act_copy["focus_duration"] = act_strain.get("focus_duration", "Endurance / Century (>1h Focus)")
        act_copy["battery_depleted_pct"] = act_strain.get("battery_depleted_pct", 0.0)
        act_copy["min_w_bal_pct"] = act_strain.get("min_w_bal_pct", 100.0)
        act_copy["strain_data"] = act_strain
        enriched_activities.append(act_copy)

    strava_weekly_tss = int(weekly_stats.get("total_tss", 0))
    strava_weekly_xss = int(strain_systems.get("total_xss") or strain_systems.get("trailing_7d", {}).get("total_xss", 0.0))
    
    # Mirror XSS in weekly_stats
    weekly_stats["total_xss"] = strava_weekly_xss
    weekly_stats["low_xss"] = int(strain_systems.get("low_xss") or strain_systems.get("trailing_7d", {}).get("low_xss", 0.0))
    weekly_stats["high_xss"] = int(strain_systems.get("high_xss") or strain_systems.get("trailing_7d", {}).get("high_xss", 0.0))
    weekly_stats["peak_xss"] = int(strain_systems.get("peak_xss") or strain_systems.get("trailing_7d", {}).get("peak_xss", 0.0))

    program_data = get_current_program(
        strava_weekly_tss=strava_weekly_tss,
        strava_weekly_xss=strava_weekly_xss,
        strain_systems=strain_systems
    )

    from app.services.preferences_service import get_coaching_preferences, get_day_target_config
    coaching_prefs = get_coaching_preferences()
    day_config = get_day_target_config()

    is_guest = (uid == "usr_guest" or current_user.get("is_guest", False))

    return {
        "user": {
            "id": uid,
            "email": current_user.get("email", "athlete@powersync.local"),
            "name": current_user.get("name", "Primary Athlete"),
            "picture": current_user.get("picture", ""),
            "is_guest": is_guest,
            "google_linked": bool(current_user.get("google_id"))
        },
        "demo_mode": demo_mode,
        "athlete": {
            "ftp": ftp,
            "max_hr": max_hr,
            "w_prime_kj": w_prime_kj,
            "peak_power_watts": peak_power
        },
        "integrations": {
            "whoop": {"connected": whoop_connected, "auth_expired": whoop_auth_expired},
            "strava": {"connected": strava_connected},
            "gemini": {"configured": bool(gemini_key and "•" not in gemini_key)},
            "intervals_icu": {"configured": bool(intervals_icu_key and "•" not in intervals_icu_key and intervals_athlete_id)}
        },
        "program": program_data,
        "whoop": whoop_data,
        "day_config": day_config,
        "coaching_preferences": coaching_prefs,
        "strava": {
            "weekly_stats": weekly_stats,
            "strain_systems": strain_systems,
            "recent_activities": enriched_activities[:5]
        }
    }

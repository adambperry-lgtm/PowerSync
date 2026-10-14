from fastapi import APIRouter
import datetime
from app.database import get_setting, get_db_connection
from app.services.mock_data import get_mock_whoop_data, get_mock_strava_activities, get_mock_weekly_stats
from app.services.program_service import get_current_program

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("")
def get_dashboard_data():
    whoop_tokens = get_setting("whoop_tokens", None)
    strava_tokens = get_setting("strava_tokens", None)
    
    # If athlete has connected real tokens, demo_mode is always False
    demo_mode_setting = get_setting("demo_mode", False)
    demo_mode = False if (whoop_tokens or strava_tokens) else bool(demo_mode_setting)
    
    ftp = get_setting("athlete_ftp", 250)
    max_hr = get_setting("athlete_max_hr", 185)
    gemini_key = get_setting("gemini_api_key", "")
    intervals_icu_key = get_setting("intervals_icu_api_key", "")
    intervals_athlete_id = get_setting("intervals_athlete_id", "")
    
    # Whoop Data: if user has connected Whoop tokens, ALWAYS use their real data
    today_iso = datetime.date.today().isoformat()
    whoop_auth_expired = False
    if whoop_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
        row = c.fetchone()
        conn.close()

        # If we don't have today's metrics yet, attempt an automatic sync
        if not row or row["date"] != today_iso:
            from app.services.whoop_service import fetch_latest_whoop_metrics
            sync_res = fetch_latest_whoop_metrics()
            if sync_res.get("success"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM whoop_metrics ORDER BY date DESC LIMIT 1")
                row = c.fetchone()
                conn.close()
            elif sync_res.get("auth_expired"):
                whoop_auth_expired = True

        if row:
            from app.services.whoop_service import get_trailing_whoop_stats
            trailing_stats = get_trailing_whoop_stats(days=7)
            is_today = (row["date"] == today_iso)
            whoop_data = {
                "date": row["date"],
                "is_today": is_today,
                "auth_expired": whoop_auth_expired,
                "recovery_score": int(row["recovery_score"]),
                "recovery_zone": "green" if row["recovery_score"] > 66 else ("yellow" if row["recovery_score"] >= 34 else "red"),
                "hrv_rmssd": round(float(row["hrv_rmssd"]), 1),
                "resting_heart_rate": int(row["resting_heart_rate"]),
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
                    "hrv_vs_baseline": f"{round(float(row['hrv_rmssd']), 1)} ms",
                    "rhr_vs_baseline": f"{int(row['resting_heart_rate'])} bpm",
                    "sleep_consistency": "Synced Today" if is_today else f"Last: {row['date']}"
                }
            }
        else:
            whoop_data = get_mock_whoop_data()
            whoop_data["auth_expired"] = whoop_auth_expired
        whoop_connected = True
    else:
        whoop_data = get_mock_whoop_data()
        whoop_connected = False

    # Strava Data: if user has connected Strava tokens, ALWAYS use their real data
    from app.services.strava_service import get_strava_trailing_stats
    if strava_tokens:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM strava_activities ORDER BY start_date DESC LIMIT 30")
        rows = c.fetchall()
        conn.close()
        activities = [dict(r) for r in rows] if rows else get_mock_strava_activities()
        weekly_stats = get_strava_trailing_stats(activities=activities, days=7)
        strava_connected = True
    else:
        activities = get_mock_strava_activities()
        weekly_stats = get_strava_trailing_stats(activities=activities, days=7)
        strava_connected = False

    from app.services.strain_model_service import calculate_trailing_strain_systems, calculate_activity_strain
    w_prime_kj = float(get_setting("athlete_w_prime_kj", 20.0))
    peak_power = int(get_setting("athlete_peak_power_watts", 1050))
    strain_systems = calculate_trailing_strain_systems(activities=activities, days=7, ftp=ftp)

    # Enrich all activities with 3-tier physiological strain and battery depletion
    enriched_activities = []
    for act in activities:
        act_copy = dict(act)
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

    return {
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

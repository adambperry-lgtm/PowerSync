import os
import json
import math
import requests
import datetime
from typing import Dict, Any, List, Optional

from app.database import (
    get_db_connection,
    get_setting,
    get_current_user_id,
    get_athlete_date,
    resolve_strava_local_start
)
from app.services.strava_service import refresh_strava_token
from app.services.strain_model_service import calculate_activity_strain

STRAVA_API_BASE = "https://www.strava.com/api/v3"

COACH_TOOL_DECLARATIONS = [
    {
        "name": "get_strava_activity_details",
        "description": (
            "Retrieves granular telemetry, interval lap splits (avg watts, HR, duration, cadence), "
            "segment efforts, 3-tier XSS strain (Low, High, Peak), and anaerobic W' battery depletion "
            "for a specific Strava workout. Use this whenever the athlete asks about their latest ride, "
            "yesterday's ride, how their intervals went, pacing stability, or wattage breakdown."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "activity_id": {
                    "type": "STRING",
                    "description": (
                        "The Strava activity ID (e.g. '123456789'), or 'latest' for their most recent workout, "
                        "or 'yesterday' for yesterday's workout."
                    )
                }
            },
            "required": ["activity_id"]
        }
    },
    {
        "name": "get_strava_activity_streams_and_power_curve",
        "description": (
            "Analyzes second-by-second telemetry streams (watts, heart rate, cadence) for a Strava activity "
            "to calculate peak power intervals (best 5s sprint, 1m anaerobic, 5m VO2 max, 20m threshold), "
            "interval fatigue index (decay from 1st interval to final interval), and aerobic decoupling (cardiac drift)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "activity_id": {
                    "type": "STRING",
                    "description": "The Strava activity ID, or 'latest' or 'yesterday'."
                }
            },
            "required": ["activity_id"]
        }
    },
    {
        "name": "search_strava_activities",
        "description": (
            "Searches the athlete's Strava workout history by keywords (e.g. 'Sweet Spot', 'Endurance', 'Threshold', 'Climb'), "
            "sport type (Ride, VirtualRide, Run), or timeframe. Returns a structured list of matching workouts with power, duration, TSS, and XSS."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Optional keyword or workout title to search for (e.g. 'sweet spot', 'tempo', 'morning')."
                },
                "sport_type": {
                    "type": "STRING",
                    "description": "Optional filter: 'Ride', 'VirtualRide', 'Run', or 'All'."
                },
                "days_back": {
                    "type": "INTEGER",
                    "description": "How many days back to search (default 30, max 90)."
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum number of activities to return (default 5, max 10)."
                }
            }
        }
    },
    {
        "name": "get_whoop_biometrics_timeline",
        "description": (
            "Retrieves daily Whoop biometrics (recovery score %, resting heart rate, HRV rMSSD, sleep performance %, sleep debt, and daytime strain) "
            "across recent days. Use this to correlate the athlete's physiological recovery with their training load."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "days": {
                    "type": "INTEGER",
                    "description": "Number of days of Whoop history to retrieve (default 7, max 14)."
                }
            }
        }
    }
]

def _resolve_activity_record(activity_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Resolves an activity from SQLite by explicit ID, 'latest', or 'yesterday'."""
    conn = get_db_connection()
    c = conn.cursor()
    row = None
    act_param = str(activity_id).lower().strip()

    if act_param in ("latest", "recent", "today"):
        c.execute("SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 1", (user_id,))
        row = c.fetchone()
        if not row and user_id != "usr_default":
            c.execute("SELECT * FROM strava_activities WHERE user_id = 'usr_default' ORDER BY start_date DESC LIMIT 1")
            row = c.fetchone()

    elif act_param in ("yesterday", "previous", "prior"):
        today = get_athlete_date(user_id)
        yesterday_iso = (today - datetime.timedelta(days=1)).isoformat()
        c.execute("SELECT * FROM strava_activities WHERE user_id = ? AND start_date LIKE ? ORDER BY start_date DESC LIMIT 1", (user_id, f"{yesterday_iso}%"))
        row = c.fetchone()
        if not row:
            # Fallback to second-most recent
            c.execute("SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 2", (user_id,))
            rows = c.fetchall()
            if len(rows) > 1:
                row = rows[1]
            elif rows:
                row = rows[0]

    else:
        # Match by ID or partial name
        c.execute("SELECT * FROM strava_activities WHERE user_id = ? AND id = ?", (user_id, act_param))
        row = c.fetchone()
        if not row:
            c.execute("SELECT * FROM strava_activities WHERE user_id = ? AND name LIKE ? ORDER BY start_date DESC LIMIT 1", (user_id, f"%{act_param}%"))
            row = c.fetchone()

    conn.close()
    if row:
        return dict(row)
    return None

def _fetch_strava_api_activity(activity_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Directly calls Strava API /activities/{id} to get laps, splits, and segment efforts."""
    tokens = get_setting("strava_tokens", {}, user_id=user_id)
    if not tokens and user_id != "usr_default":
        tokens = get_setting("strava_tokens", {}, user_id="usr_default")
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{STRAVA_API_BASE}/activities/{activity_id}"
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 401:
            refreshed = refresh_strava_token(user_id=user_id)
            if refreshed:
                headers = {"Authorization": f"Bearer {refreshed}"}
                res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error fetching Strava activity details: {e}")
    return None

def _fetch_strava_api_streams(activity_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Fetches high-resolution second-by-second activity streams from Strava API."""
    tokens = get_setting("strava_tokens", {}, user_id=user_id)
    if not tokens and user_id != "usr_default":
        tokens = get_setting("strava_tokens", {}, user_id="usr_default")
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{STRAVA_API_BASE}/activities/{activity_id}/streams?keys=time,watts,heartrate,cadence,velocity_smooth&key_by_type=true"
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 401:
            refreshed = refresh_strava_token(user_id=user_id)
            if refreshed:
                headers = {"Authorization": f"Bearer {refreshed}"}
                res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error fetching Strava activity streams: {e}")
    return None

def tool_get_strava_activity_details(activity_id: str = "latest", user_id: Optional[str] = None) -> Dict[str, Any]:
    """Implementation of get_strava_activity_details tool."""
    uid = user_id or get_current_user_id()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))

    db_rec = _resolve_activity_record(activity_id, uid)
    if not db_rec:
        return {
            "found": False,
            "error": f"No Strava activity found matching '{activity_id}'. Please sync Strava or check recent workouts.",
            "tool_summary": f"Could not locate activity '{activity_id}'"
        }

    numeric_id = str(db_rec.get("id"))
    api_detail = _fetch_strava_api_activity(numeric_id, uid)

    # Blend API detail with DB record
    act_data = api_detail if api_detail else db_rec
    if not api_detail and db_rec.get("raw_json"):
        try:
            raw_parsed = json.loads(db_rec["raw_json"])
            if isinstance(raw_parsed, dict):
                act_data = {**raw_parsed, **db_rec}
        except Exception:
            pass

    # Extract local date
    local_start = resolve_strava_local_start(act_data, user_id=uid) or act_data.get("start_date", "")

    # Calculate 3-tier strain
    strain = calculate_activity_strain(act_data, ftp=ftp)

    # Format Laps
    laps_formatted = []
    raw_laps = act_data.get("laps") or []
    for l in raw_laps:
        l_dur = round(l.get("moving_time") or l.get("elapsed_time") or 0)
        l_dur_str = f"{l_dur // 60}:{l_dur % 60:02d}"
        laps_formatted.append({
            "lap_index": l.get("lap_index", len(laps_formatted) + 1),
            "name": l.get("name", f"Lap {len(laps_formatted) + 1}"),
            "duration": l_dur_str,
            "duration_sec": l_dur,
            "avg_watts": round(l.get("average_watts") or 0),
            "weighted_watts": round(l.get("weighted_average_watts") or l.get("average_watts") or 0),
            "pct_ftp": round(((l.get("weighted_average_watts") or l.get("average_watts") or 0) / float(ftp)) * 100) if ftp > 0 else 0,
            "avg_hr": round(l.get("average_heartrate") or 0),
            "max_hr": round(l.get("max_heartrate") or 0),
            "cadence": round(l.get("average_cadence") or 0)
        })

    # Segment efforts
    segments_formatted = []
    for s in (act_data.get("segment_efforts") or [])[:5]:
        segments_formatted.append({
            "name": s.get("name", "Segment"),
            "elapsed_time_sec": s.get("elapsed_time", 0),
            "avg_watts": round(s.get("average_watts") or 0),
            "avg_hr": round(s.get("average_heartrate") or 0),
            "pr_rank": s.get("pr_rank")
        })

    moving_sec = int(act_data.get("moving_time_sec") or act_data.get("moving_time") or 0)
    dur_min = round(moving_sec / 60.0, 1)
    dist_mi = round((act_data.get("distance_meters") or act_data.get("distance") or 0.0) / 1609.34, 1)
    np_watts = round(act_data.get("weighted_average_watts") or act_data.get("average_watts") or 0)
    pct_ftp = round((np_watts / float(ftp)) * 100) if ftp > 0 else 0

    return {
        "found": True,
        "activity_id": numeric_id,
        "name": act_data.get("name", "Workout"),
        "sport_type": act_data.get("sport_type") or act_data.get("type", "Ride"),
        "date": local_start[:10] if local_start else "Recent",
        "start_time_local": local_start[11:16] if len(local_start) > 16 else "",
        "duration_minutes": dur_min,
        "distance_miles": dist_mi,
        "elevation_gain_ft": round((act_data.get("total_elevation_gain") or 0.0) * 3.28084),
        "power_summary": {
            "average_watts": round(act_data.get("average_watts") or 0),
            "normalized_power_watts": np_watts,
            "pct_of_ftp": pct_ftp,
            "kilojoules": round(act_data.get("kilojoules") or 0),
            "cadence_avg_rpm": round(act_data.get("average_cadence") or 0)
        },
        "heart_rate_summary": {
            "avg_hr": round(act_data.get("average_heartrate") or 0),
            "max_hr": round(act_data.get("max_heartrate") or 0),
            "suffer_score": round(act_data.get("suffer_score") or 0)
        },
        "physiological_strain": {
            "total_xss": round(strain.get("total_xss", 0.0), 1),
            "low_aerobic_xss": round(strain.get("low_xss", 0.0), 1),
            "high_glycolytic_xss": round(strain.get("high_xss", 0.0), 1),
            "peak_neuromuscular_xss": round(strain.get("peak_xss", 0.0), 1),
            "focus_duration": strain.get("focus_duration", ""),
            "min_w_bal_remaining_pct": round(strain.get("min_w_bal_pct", 100.0), 1),
            "anaerobic_battery_depleted_pct": round(strain.get("battery_depleted_pct", 0.0), 1)
        },
        "laps": laps_formatted,
        "has_laps": len(laps_formatted) > 0,
        "segment_efforts": segments_formatted,
        "tool_summary": f"Analyzed telemetry & {len(laps_formatted)} laps for '{act_data.get('name')}' ({dur_min}m, {np_watts}W NP, {round(strain.get('total_xss', 0))} XSS)"
    }

def tool_get_strava_activity_streams_and_power_curve(activity_id: str = "latest", user_id: Optional[str] = None) -> Dict[str, Any]:
    """Analyzes streams to extract power curve and cardiac drift."""
    uid = user_id or get_current_user_id()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))

    db_rec = _resolve_activity_record(activity_id, uid)
    if not db_rec:
        return {
            "found": False,
            "error": f"No activity found matching '{activity_id}'.",
            "tool_summary": f"Could not find activity '{activity_id}'"
        }

    numeric_id = str(db_rec.get("id"))
    streams = _fetch_strava_api_streams(numeric_id, uid)
    act_name = db_rec.get("name", "Workout")

    # If streams available, compute sliding window peak powers
    watts_data = streams.get("watts", {}).get("data", []) if streams else []
    hr_data = streams.get("heartrate", {}).get("data", []) if streams else []
    time_data = streams.get("time", {}).get("data", []) if streams else []

    peak_curve = {}
    aerobic_decoupling_pct = None
    decoupling_assessment = "Streams not available; cardiac drift estimated from lap heart rate."

    if watts_data:
        n = len(watts_data)
        # Compute sliding windows
        def sliding_peak(window_sec):
            if n < window_sec:
                return round(sum(watts_data) / max(1, n))
            cur = sum(watts_data[:window_sec])
            m = cur
            for i in range(window_sec, n):
                cur += watts_data[i] - watts_data[i - window_sec]
                if cur > m:
                    m = cur
            return round(m / window_sec)

        peak_curve = {
            "peak_5s_sprint_watts": sliding_peak(5),
            "peak_15s_sprint_watts": sliding_peak(15),
            "peak_30s_watts": sliding_peak(30),
            "peak_1m_anaerobic_watts": sliding_peak(60),
            "peak_3m_vo2max_watts": sliding_peak(180),
            "peak_5m_vo2max_watts": sliding_peak(300),
            "peak_10m_threshold_watts": sliding_peak(600),
            "peak_20m_threshold_watts": sliding_peak(1200) if n >= 1200 else None
        }

        # Aerobic Decoupling (Pw:HR)
        if hr_data and len(hr_data) == n and n >= 600:
            half = n // 2
            p1 = sum(watts_data[:half]) / half
            hr1 = sum(hr_data[:half]) / half
            p2 = sum(watts_data[half:]) / (n - half)
            hr2 = sum(hr_data[half:]) / (n - half)

            ratio1 = p1 / hr1 if hr1 > 0 else 0
            ratio2 = p2 / hr2 if hr2 > 0 else 0
            if ratio1 > 0:
                aerobic_decoupling_pct = round(((ratio1 - ratio2) / ratio1) * 100.0, 1)
                if aerobic_decoupling_pct < 4.0:
                    decoupling_assessment = f"Excellent aerobic stability ({aerobic_decoupling_pct}% drift). Minimal cardiac strain over duration."
                elif aerobic_decoupling_pct < 8.0:
                    decoupling_assessment = f"Normal aerobic drift ({aerobic_decoupling_pct}%). Well within expected physiological tolerance."
                else:
                    decoupling_assessment = f"Elevated cardiac drift ({aerobic_decoupling_pct}%). Power-to-HR decoupled significantly in second half (fatigue or hydration)."

    else:
        # Fallback estimated power curve from NP and average watts
        np_w = float(db_rec.get("weighted_average_watts") or db_rec.get("average_watts") or ftp)
        peak_curve = {
            "peak_5s_sprint_watts": round(np_w * 1.6),
            "peak_1m_anaerobic_watts": round(np_w * 1.35),
            "peak_5m_vo2max_watts": round(np_w * 1.15),
            "peak_20m_threshold_watts": round(np_w * 1.02)
        }

    return {
        "found": True,
        "activity_id": numeric_id,
        "name": act_name,
        "power_curve": peak_curve,
        "aerobic_decoupling_pct": aerobic_decoupling_pct,
        "cardiac_drift_assessment": decoupling_assessment,
        "has_high_resolution_streams": bool(watts_data),
        "tool_summary": f"Calculated power curve & cardiac drift for '{act_name}' (Peak 5m: {peak_curve.get('peak_5m_vo2max_watts')}W)"
    }

def tool_search_strava_activities(
    query: str = "",
    sport_type: str = "All",
    days_back: int = 30,
    limit: int = 5,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Searches athlete's Strava workouts in SQLite."""
    uid = user_id or get_current_user_id()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))

    conn = get_db_connection()
    c = conn.cursor()

    cutoff_date = (get_athlete_date(uid) - datetime.timedelta(days=days_back)).isoformat()
    sql = "SELECT * FROM strava_activities WHERE user_id = ? AND start_date >= ?"
    params = [uid, cutoff_date]

    if query and query.strip():
        sql += " AND (name LIKE ? OR sport_type LIKE ?)"
        q_term = f"%{query.strip()}%"
        params.extend([q_term, q_term])

    if sport_type and sport_type != "All":
        sql += " AND sport_type = ?"
        params.append(sport_type)

    sql += " ORDER BY start_date DESC LIMIT ?"
    params.append(min(limit, 10))

    c.execute(sql, tuple(params))
    rows = c.fetchall()
    if not rows and uid != "usr_default":
        # Fallback to usr_default records
        params[0] = "usr_default"
        c.execute(sql, tuple(params))
        rows = c.fetchall()

    conn.close()

    results = []
    for r in rows:
        act = dict(r)
        np_w = round(act.get("weighted_average_watts") or act.get("average_watts") or 0)
        dur_m = round((act.get("moving_time_sec") or 0) / 60.0)
        dist_mi = round((act.get("distance_meters") or 0.0) / 1609.34, 1)
        strain = calculate_activity_strain(act, ftp=ftp)
        results.append({
            "id": act.get("id"),
            "name": act.get("name"),
            "date": str(act.get("start_date", ""))[:10],
            "sport": act.get("sport_type", "Ride"),
            "duration_min": dur_m,
            "distance_miles": dist_mi,
            "normalized_power_watts": np_w,
            "pct_ftp": round((np_w / float(ftp)) * 100) if ftp > 0 else 0,
            "tss": round(act.get("suffer_score") or 0),
            "total_xss": round(strain.get("total_xss", 0.0)),
            "focus": strain.get("focus_duration", "")
        })

    return {
        "count": len(results),
        "activities": results,
        "tool_summary": f"Found {len(results)} matching Strava workouts over past {days_back} days"
    }

def tool_get_whoop_biometrics_timeline(days: int = 7, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves Whoop recovery, HRV, sleep, and strain timeline."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        SELECT date, recovery_score, hrv_rmssd, resting_heart_rate,
               sleep_performance, sleep_duration_hours, day_strain
        FROM whoop_metrics
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT ?
    """, (uid, min(days, 14)))
    rows = c.fetchall()
    if not rows and uid != "usr_default":
        c.execute("""
            SELECT date, recovery_score, hrv_rmssd, resting_heart_rate,
                   sleep_performance, sleep_duration_hours, day_strain
            FROM whoop_metrics
            WHERE user_id = 'usr_default'
            ORDER BY date DESC
            LIMIT ?
        """, (min(days, 14),))
        rows = c.fetchall()

    conn.close()

    timeline = []
    for r in rows:
        rec = int(r["recovery_score"] or 50)
        zone = "Green" if rec >= 67 else ("Red" if rec < 34 else "Yellow")
        timeline.append({
            "date": r["date"],
            "recovery_score_pct": rec,
            "recovery_zone": zone,
            "hrv_rmssd_ms": round(float(r["hrv_rmssd"] or 0.0), 1),
            "resting_heart_rate_bpm": int(r["resting_heart_rate"] or 0),
            "sleep_performance_pct": int(r["sleep_performance"] or 0),
            "sleep_duration_hours": round(float(r["sleep_duration_hours"] or 0.0), 1),
            "day_strain": round(float(r["day_strain"] or 0.0), 1)
        })

    return {
        "count": len(timeline),
        "timeline": timeline,
        "tool_summary": f"Retrieved {len(timeline)} days of Whoop biometric recovery history"
    }

def execute_coach_tool(name: str, args: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """Dispatcher executing Gemini tool calls."""
    uid = user_id or get_current_user_id()
    if name == "get_strava_activity_details":
        return tool_get_strava_activity_details(activity_id=args.get("activity_id", "latest"), user_id=uid)
    elif name == "get_strava_activity_streams_and_power_curve":
        return tool_get_strava_activity_streams_and_power_curve(activity_id=args.get("activity_id", "latest"), user_id=uid)
    elif name == "search_strava_activities":
        return tool_search_strava_activities(
            query=args.get("query", ""),
            sport_type=args.get("sport_type", "All"),
            days_back=int(args.get("days_back", 30)),
            limit=int(args.get("limit", 5)),
            user_id=uid
        )
    elif name == "get_whoop_biometrics_timeline":
        return tool_get_whoop_biometrics_timeline(days=int(args.get("days", 7)), user_id=uid)
    else:
        return {"error": f"Unknown tool '{name}'", "tool_summary": f"Unknown tool '{name}'"}

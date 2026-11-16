import json
import time
import threading
import requests
import datetime
from typing import Dict, Any, List, Optional
from app.database import get_setting, set_setting, get_db_connection, get_current_user_id, get_athlete_date, resolve_strava_local_start

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

def get_strava_auth_url(redirect_uri: str, state: Optional[str] = None) -> str:
    client_id = get_setting("strava_client_id", "")
    scope = "read,activity:read_all"
    state_param = f"&state={state}" if state else ""
    return f"{STRAVA_AUTH_URL}?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&approval_prompt=auto&scope={scope}{state_param}"

def exchange_strava_code(code: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    client_id = str(get_setting("strava_client_id", "", user_id=uid)).strip()
    client_secret = str(get_setting("strava_client_secret", "", user_id=uid)).strip()
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code.strip(),
        "grant_type": "authorization_code"
    }
    
    try:
        res = requests.post(STRAVA_TOKEN_URL, data=data, timeout=10)
        if res.status_code == 200:
            token_info = res.json()
            set_setting("strava_tokens", token_info, user_id=uid)
            return {"success": True, "token_info": token_info}
        return {"success": False, "error": f"Strava returned HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"success": False, "error": f"Network error connecting to Strava: {str(e)}"}

def refresh_strava_token(user_id: Optional[str] = None) -> Optional[str]:
    uid = user_id or get_current_user_id()
    tokens = get_setting("strava_tokens", {}, user_id=uid)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None
        
    client_id = str(get_setting("strava_client_id", "", user_id=uid)).strip()
    client_secret = str(get_setting("strava_client_secret", "", user_id=uid)).strip()
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    res = requests.post(STRAVA_TOKEN_URL, data=data, timeout=10)
    if res.status_code == 200:
        new_tokens = res.json()
        set_setting("strava_tokens", new_tokens, user_id=uid)
        return new_tokens.get("access_token")
    return None

def _upsert_strava_activities(activities: List[Dict[str, Any]], uid: str) -> List[Dict[str, Any]]:
    """Upserts a batch of Strava API activity payloads into strava_activities scoped by user_id."""
    if not activities:
        return []

    conn = get_db_connection()
    c = conn.cursor()
    saved = []

    # Auto-calibrate athlete timezone from Strava activity if not yet explicitly customized
    current_saved_tz = get_setting("athlete_timezone", default=None, user_id=uid)
    if not current_saved_tz:
        for act in activities:
            raw_tz = act.get("timezone")
            if raw_tz and isinstance(raw_tz, str) and ")" in raw_tz:
                tz_candidate = raw_tz.split(")")[-1].strip()
                try:
                    import zoneinfo
                    zoneinfo.ZoneInfo(tz_candidate)
                    set_setting("athlete_timezone", tz_candidate, user_id=uid)
                    if uid == "usr_guest":
                        set_setting("athlete_timezone", tz_candidate, user_id="usr_default")
                    break
                except Exception:
                    pass

    for a in activities:
        act_id = str(a.get("id"))
        name = a.get("name", "Activity")
        sport = a.get("sport_type") or a.get("type", "Ride")
        start_date = resolve_strava_local_start(a, user_id=uid) or a.get("start_date", "")
        moving_time = a.get("moving_time", 0)
        dist = a.get("distance", 0.0)
        elev = a.get("total_elevation_gain", 0.0)
        watts = a.get("average_watts", 0.0)
        w_watts = a.get("weighted_average_watts", 0.0)
        hr = a.get("average_heartrate", 0.0)
        max_hr = a.get("max_heartrate", 0.0)
        suffer = a.get("suffer_score", 0.0)
        kj = a.get("kilojoules", 0.0)

        c.execute("""
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, average_watts, weighted_average_watts,
                average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, id) DO UPDATE SET
                start_date = excluded.start_date,
                name = excluded.name,
                sport_type = excluded.sport_type,
                moving_time_sec = excluded.moving_time_sec,
                distance_meters = excluded.distance_meters,
                total_elevation_gain = excluded.total_elevation_gain,
                average_watts = excluded.average_watts,
                weighted_average_watts = excluded.weighted_average_watts,
                average_heartrate = excluded.average_heartrate,
                max_heartrate = excluded.max_heartrate,
                suffer_score = excluded.suffer_score,
                kilojoules = excluded.kilojoules,
                raw_json = excluded.raw_json
        """, (uid, act_id, name, sport, start_date, moving_time, dist, elev, watts, w_watts, hr, max_hr, suffer, kj, json.dumps(a)))

        saved.append({
            "id": act_id,
            "name": name,
            "sport_type": sport,
            "start_date": start_date,
            "moving_time_sec": moving_time,
            "distance_meters": dist,
            "total_elevation_gain": elev,
            "average_watts": watts,
            "weighted_average_watts": w_watts,
            "average_heartrate": hr,
            "max_heartrate": max_hr,
            "suffer_score": suffer,
            "kilojoules": kj
        })

    conn.commit()
    conn.close()
    return saved

def fetch_recent_strava_activities(limit: int = 20, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    uid = user_id or get_current_user_id()
    tokens = get_setting("strava_tokens", {}, user_id=uid)
    access_token = tokens.get("access_token") if tokens else None
    if not access_token:
        print("fetch_recent_strava_activities: No strava access_token found.")
        return []
        
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        res = requests.get(f"{STRAVA_API_BASE}/athlete/activities?per_page={limit}", headers=headers, timeout=10)
        
        if res.status_code == 401:
            print("Strava access token expired (401). Attempting token refresh...")
            access_token = refresh_strava_token(user_id=uid)
            if access_token:
                headers = {"Authorization": f"Bearer {access_token}"}
                res = requests.get(f"{STRAVA_API_BASE}/athlete/activities?per_page={limit}", headers=headers, timeout=10)
            else:
                print("Strava token refresh failed. Please check strava_client_secret.")
                return []
                
        if res.status_code != 200:
            print(f"Strava API error {res.status_code}: {res.text}")
            return []
            
        activities = res.json()
    except Exception as e:
        print(f"Network error communicating with Strava: {e}")
        return []

    return _upsert_strava_activities(activities, uid)

def get_strava_sync_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns per-user Strava backfill/sync status and total stored activity count."""
    uid = user_id or get_current_user_id()
    status = get_setting("strava_sync_status", {}, user_id=uid) or {}
    backfill_complete = bool(get_setting("strava_backfill_complete", False, user_id=uid))

    # Clear stale in_progress lock if > 10 minutes old
    if status.get("in_progress") and status.get("started_at_ts"):
        if time.time() - float(status.get("started_at_ts", 0)) > 600:
            status["in_progress"] = False
            set_setting("strava_sync_status", status, user_id=uid)

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM strava_activities WHERE user_id = ?", (uid,))
    row = c.fetchone()
    total_count = int(row[0]) if row else 0
    conn.close()

    return {
        "in_progress": bool(status.get("in_progress", False)),
        "pages_fetched": int(status.get("pages_fetched", 0)),
        "activities_synced": int(status.get("activities_synced", 0)),
        "backfill_complete": backfill_complete,
        "total_stored_activities": total_count,
        "error": status.get("error"),
        "last_run_at": status.get("last_run_at")
    }

def sync_all_strava_activities(
    user_id: Optional[str] = None,
    force_full: bool = False,
    max_pages: int = 100
) -> Dict[str, Any]:
    """
    Paginates through Strava /athlete/activities (per_page=200) to backfill all-time
    history (when force_full=True or backfill is not yet complete), or incrementally
    syncs activities since the last synced timestamp.
    """
    uid = user_id or get_current_user_id()
    tokens = get_setting("strava_tokens", {}, user_id=uid)
    access_token = tokens.get("access_token") if tokens else None
    if not access_token:
        return {"success": False, "error": "No Strava access token found.", "activities_synced": 0}

    cur_status = get_strava_sync_status(user_id=uid)
    if cur_status.get("in_progress"):
        return {"success": True, "already_running": True, **cur_status}

    backfill_complete = bool(get_setting("strava_backfill_complete", False, user_id=uid))
    last_epoch = get_setting("strava_last_synced_epoch", None, user_id=uid)
    is_incremental = (not force_full) and backfill_complete and bool(last_epoch)

    status_obj = {
        "in_progress": True,
        "started_at_ts": time.time(),
        "pages_fetched": 0,
        "activities_synced": 0,
        "error": None,
        "last_run_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    set_setting("strava_sync_status", status_obj, user_id=uid)

    total_synced = 0
    pages_fetched = 0
    newest_epoch = int(last_epoch or 0)
    completed_cleanly = True
    err_msg = None

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        for page in range(1, max_pages + 1):
            url = f"{STRAVA_API_BASE}/athlete/activities?per_page=200&page={page}"
            if is_incremental and last_epoch:
                after_ts = max(0, int(last_epoch) - 86400)
                url += f"&after={after_ts}"

            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 401:
                new_tok = refresh_strava_token(user_id=uid)
                if new_tok:
                    access_token = new_tok
                    headers = {"Authorization": f"Bearer {access_token}"}
                    res = requests.get(url, headers=headers, timeout=15)
                else:
                    completed_cleanly = False
                    err_msg = "Strava token refresh failed."
                    break

            if res.status_code == 429:
                completed_cleanly = False
                err_msg = "Strava API rate limit reached; partial history saved. Try again in 15 minutes."
                break

            if res.status_code != 200:
                completed_cleanly = False
                err_msg = f"Strava API error HTTP {res.status_code}"
                break

            batch = res.json()
            if not isinstance(batch, list) or len(batch) == 0:
                break

            _upsert_strava_activities(batch, uid)
            pages_fetched += 1
            total_synced += len(batch)

            for a in batch:
                sd = a.get("start_date")
                if sd:
                    try:
                        dt = datetime.datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
                        ep = int(dt.timestamp())
                        if ep > newest_epoch:
                            newest_epoch = ep
                    except Exception:
                        pass

            status_obj["pages_fetched"] = pages_fetched
            status_obj["activities_synced"] = total_synced
            set_setting("strava_sync_status", status_obj, user_id=uid)

            # If fewer than 200 returned, we've reached the end of the athlete's history
            if len(batch) < 200:
                break

            # Gentle pacing between pages
            time.sleep(0.15)
    except Exception as e:
        completed_cleanly = False
        err_msg = str(e)
    finally:
        status_obj["in_progress"] = False
        status_obj["pages_fetched"] = pages_fetched
        status_obj["activities_synced"] = total_synced
        status_obj["error"] = err_msg
        status_obj["last_run_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        set_setting("strava_sync_status", status_obj, user_id=uid)

        if completed_cleanly:
            set_setting("strava_backfill_complete", True, user_id=uid)
            if newest_epoch > 0:
                set_setting("strava_last_synced_epoch", newest_epoch, user_id=uid)

    return {
        "success": completed_cleanly,
        "pages_fetched": pages_fetched,
        "activities_synced": total_synced,
        "backfill_complete": bool(get_setting("strava_backfill_complete", False, user_id=uid)),
        "error": err_msg
    }

def trigger_strava_full_backfill_async(user_id: Optional[str] = None, force_full: bool = False) -> Dict[str, Any]:
    """Starts paginated all-time Strava backfill in a background daemon thread if not already running."""
    uid = user_id or get_current_user_id()
    cur_status = get_strava_sync_status(user_id=uid)
    if cur_status.get("in_progress"):
        return {"started": False, "already_running": True, **cur_status}

    t = threading.Thread(
        target=sync_all_strava_activities,
        kwargs={"user_id": uid, "force_full": force_full},
        daemon=True
    )
    t.start()
    return {"started": True, "already_running": False, **cur_status}

def get_strava_trailing_stats(activities: Optional[List[Dict[str, Any]]] = None, days: int = 7, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes trailing 7-day training load with exponential recency weighting.
    More heavily weights recent training (e.g. yesterday) over training early in the cycle (7 days ago),
    accounting for acute fatigue decay (tau ~ 3.0 days).
    """
    import math
    uid = user_id or get_current_user_id()
    if activities is None:
        strava_tokens = get_setting("strava_tokens", None, user_id=uid)
        if strava_tokens:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 30", (uid,))
            rows = c.fetchall()
            conn.close()
            activities = [dict(r) for r in rows] if rows else []
        else:
            activities = []

    if not activities:
        from app.services.mock_data import get_mock_weekly_stats
        return get_mock_weekly_stats()

    today = get_athlete_date()

    # Build calendar day slots for the last `days` completed days (days ago: 1 to 7)
    daily_buckets = {}
    for i in range(1, days + 1):
        d_str = (today - datetime.timedelta(days=i)).isoformat()
        daily_buckets[d_str] = {
            "day_index": i,
            "date": d_str,
            "tss": 0,
            "moving_sec": 0,
            "elevation_m": 0,
            "distance_m": 0,
            "activities": []
        }

    # Aggregate completed activities into their corresponding calendar days
    for act in activities:
        s_date = resolve_strava_local_start(act, user_id=user_id) or act.get("start_date", "")
        if not s_date:
            continue
        date_key = s_date[:10]
        if date_key in daily_buckets:
            suffer = act.get("suffer_score")
            if suffer is None or suffer == 0:
                dur_h = (act.get("moving_time_sec") or 0) / 3600.0
                suffer = round(dur_h * 50)
            daily_buckets[date_key]["tss"] += int(suffer or 0)
            daily_buckets[date_key]["moving_sec"] += int(act.get("moving_time_sec") or 0)
            daily_buckets[date_key]["elevation_m"] += int(act.get("total_elevation_gain") or 0)
            daily_buckets[date_key]["distance_m"] += float(act.get("distance_meters") or 0)
            daily_buckets[date_key]["activities"].append(act.get("name", "Ride"))

    sorted_days = sorted(daily_buckets.keys(), reverse=True) # yesterday first
    weights = [math.exp(-i / 3.0) for i in range(len(sorted_days))]
    w_sum = sum(weights)

    total_sec = sum(b["moving_sec"] for b in daily_buckets.values())
    total_dist_m = sum(b["distance_m"] for b in daily_buckets.values())
    total_elev_m = sum(b["elevation_m"] for b in daily_buckets.values())
    total_tss = sum(b["tss"] for b in daily_buckets.values())

    # Weighted TSS sum
    weighted_tss_sum = sum(daily_buckets[d]["tss"] * weights[i] for i, d in enumerate(sorted_days))
    acute_weighted_tss = round((weighted_tss_sum / w_sum) * len(sorted_days)) if w_sum > 0 else total_tss

    yesterday_key = sorted_days[0] if sorted_days else None
    yesterday_tss = daily_buckets[yesterday_key]["tss"] if yesterday_key else 0
    yesterday_hours = round((daily_buckets[yesterday_key]["moving_sec"] if yesterday_key else 0) / 3600.0, 1)

    recent_48h_tss = sum(daily_buckets[d]["tss"] for d in sorted_days[:2])
    early_48h_tss = sum(daily_buckets[d]["tss"] for d in sorted_days[-2:])

    if yesterday_tss >= 90 or (total_tss > 0 and (recent_48h_tss / total_tss) >= 0.55):
        load_profile = "Recent Surge (Yesterday Heavy)"
        form_status = "Acute Fatigue Wave"
        form_description = f"High acute fatigue: {yesterday_tss} TSS was logged yesterday. Fatigue is in active decay."
    elif yesterday_tss < 35 and (total_tss > 0 and (early_48h_tss / total_tss) >= 0.45):
        load_profile = "Front-Loaded (Supercompensated/Fresh)"
        form_status = "Supercompensated / Fresh"
        form_description = f"Heavy training was earlier in the cycle ({early_48h_tss} TSS). Recent rest enables supercompensation."
    else:
        load_profile = "Evenly Distributed"
        form_status = "Optimal Load Balance"
        form_description = "Training stress is well-distributed with steady recovery decay across the week."

    return {
        "total_hours": round(total_sec / 3600.0, 1),
        "total_distance_km": round(total_dist_m / 1000.0, 1),
        "total_distance_miles": round((total_dist_m / 1000.0) * 0.621371, 1),
        "total_elevation_m": int(total_elev_m),
        "total_elevation_ft": int(total_elev_m * 3.28084),
        "total_tss": int(total_tss),
        "acute_weighted_tss": int(acute_weighted_tss),
        "yesterday_tss": int(yesterday_tss),
        "yesterday_hours": yesterday_hours,
        "load_profile": load_profile,
        "form_status": form_status,
        "form_description": form_description
    }


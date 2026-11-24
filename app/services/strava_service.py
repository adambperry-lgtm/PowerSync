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

def extract_strava_id(obj: Any) -> str:
    """
    Extracts the canonical Strava object identifier as a string, preferring `id_str`
    over `id` to safely handle 64-bit identifiers (Strava API June 2027 update).
    """
    if not isinstance(obj, dict):
        return str(obj).strip() if obj is not None else ""
    val = obj.get("id_str")
    if val is None or str(val).strip() == "":
        val = obj.get("id")
    return str(val).strip() if val is not None else ""

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
            if isinstance(token_info.get("athlete"), dict):
                athlete = token_info["athlete"]
                athlete_id_str = extract_strava_id(athlete)
                if athlete_id_str:
                    athlete["id_str"] = athlete_id_str
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
        if "athlete" not in new_tokens and isinstance(tokens.get("athlete"), dict):
            new_tokens["athlete"] = tokens["athlete"]
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
        act_id = extract_strava_id(a)
        if not act_id:
            continue
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


def _normalize_stream_payload(raw_streams: Dict[str, Any]) -> Optional[Dict[str, List[float]]]:
    """Extracts and optionally downsamples time/watts/heartrate/cadence streams."""
    if not isinstance(raw_streams, dict) or raw_streams.get("unavailable"):
        return None

    out: Dict[str, List[float]] = {}
    for key in ("time", "watts", "heartrate", "cadence"):
        val = raw_streams.get(key)
        if isinstance(val, dict) and isinstance(val.get("data"), list):
            arr = val["data"]
        elif isinstance(val, list):
            arr = val
        else:
            continue
        if arr:
            out[key] = arr

    if not out:
        return None

    max_len = max(len(v) for v in out.values())
    if max_len > 7200:
        stride = max(2, max_len // 3600)
        out = {k: v[::stride] for k, v in out.items()}

    return out


def get_or_fetch_activity_streams(
    activity: Optional[Dict[str, Any]],
    user_id: Optional[str] = None,
    allow_network: bool = True,
) -> Optional[Dict[str, List[float]]]:
    """
    Returns per-second (or compact) telemetry streams (time, watts, heartrate, cadence)
    for a Strava activity, checking inline payloads and the user-isolated SQLite cache
    before querying Strava's /activities/{id}/streams endpoint.
    """
    if not isinstance(activity, dict):
        return None

    # 1. Inline streams (e.g., pre-attached or injected in tests)
    inline = _normalize_stream_payload(activity.get("streams"))
    if inline:
        return inline

    raw_json = activity.get("raw_json")
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            parsed_raw = json.loads(raw_json)
            if isinstance(parsed_raw, dict) and parsed_raw.get("streams"):
                inline_raw = _normalize_stream_payload(parsed_raw.get("streams"))
                if inline_raw:
                    return inline_raw
        except Exception:
            pass

    act_id = extract_strava_id(activity)
    if not act_id:
        return None

    uid = user_id or get_current_user_id()

    # 2. SQLite cache lookup (user-isolated)
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT streams_json FROM strava_activity_streams WHERE user_id = ? AND activity_id = ?",
            (uid, act_id),
        )
        row = c.fetchone()
        conn.close()
        if row and row["streams_json"]:
            cached = json.loads(row["streams_json"])
            if isinstance(cached, dict) and cached.get("unavailable"):
                return None
            return _normalize_stream_payload(cached)
    except Exception:
        pass

    if not allow_network:
        return None

    # Only query Strava API for real numeric Strava IDs and real-looking tokens
    if not act_id.isdigit():
        return None

    tokens = get_setting("strava_tokens", {}, user_id=uid)
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not access_token or len(str(access_token).strip()) < 12:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{STRAVA_API_BASE}/activities/{act_id}/streams?keys=time,watts,heartrate,cadence&key_by_type=true"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 401 and isinstance(tokens, dict) and tokens.get("refresh_token"):
            refreshed = refresh_strava_token(user_id=uid)
            if refreshed:
                headers = {"Authorization": f"Bearer {refreshed}"}
                res = requests.get(url, headers=headers, timeout=5)

        if res.status_code == 200:
            raw_json_payload = res.json()
            try:
                mmp_peaks = compute_mmp_peaks_from_streams(raw_json_payload)
                save_activity_mmp_peaks(uid, act_id, mmp_peaks)
            except Exception:
                pass
            normalized = _normalize_stream_payload(raw_json_payload)
            payload_to_cache = normalized if normalized else {"unavailable": True}
            try:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    """
                    INSERT INTO strava_activity_streams (user_id, activity_id, streams_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, activity_id) DO UPDATE SET
                        streams_json = excluded.streams_json,
                        fetched_at = CURRENT_TIMESTAMP
                    """,
                    (uid, act_id, json.dumps(payload_to_cache)),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return normalized
        elif res.status_code == 404:
            try:
                save_activity_mmp_peaks(uid, act_id, None)
            except Exception:
                pass
            try:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    """
                    INSERT INTO strava_activity_streams (user_id, activity_id, streams_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, activity_id) DO UPDATE SET
                        streams_json = excluded.streams_json,
                        fetched_at = CURRENT_TIMESTAMP
                    """,
                    (uid, act_id, json.dumps({"unavailable": True})),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
    except Exception as e:
        print(f"Strava stream fetch error for activity {act_id}: {e}")

    return None


MMP_WINDOWS = (
    ("5s", 5),
    ("30s", 30),
    ("1m", 60),
    ("5m", 300),
    ("20m", 1200),
    ("60m", 3600),
)


def compute_mmp_peaks_from_streams(raw_streams: Any) -> Optional[Dict[str, int]]:
    """
    Computes exact Mean Maximal Power (MMP) peaks (5s, 30s, 1m, 5m, 20m, 60m)
    from a Strava activity stream payload on a 1-Hz timeline (zero-padding pauses).
    Returns None if no valid watts stream is present.
    """
    if not isinstance(raw_streams, dict) or raw_streams.get("unavailable"):
        return None

    watts_raw = raw_streams.get("watts")
    if isinstance(watts_raw, dict) and isinstance(watts_raw.get("data"), list):
        watts = watts_raw["data"]
    elif isinstance(watts_raw, list):
        watts = watts_raw
    else:
        return None

    if not watts:
        return None

    time_raw = raw_streams.get("time")
    if isinstance(time_raw, dict) and isinstance(time_raw.get("data"), list):
        time_arr = time_raw["data"]
    elif isinstance(time_raw, list):
        time_arr = time_raw
    else:
        time_arr = None

    # Reconstruct 1-Hz timeline so pauses/stops are zero-padded rather than compressed
    if time_arr and len(time_arr) == len(watts) and len(time_arr) > 1:
        try:
            t0 = int(time_arr[0])
            t_end = int(time_arr[-1])
            span = t_end - t0 + 1
            if 1 <= span <= 43200:  # up to 12 hours
                series = [0.0] * span
                for t_val, w_val in zip(time_arr, watts):
                    idx = int(t_val) - t0
                    if 0 <= idx < span and w_val is not None:
                        w_f = float(w_val)
                        if w_f > 0:
                            series[idx] = w_f
            else:
                series = [max(0.0, float(w or 0.0)) for w in watts]
        except Exception:
            series = [max(0.0, float(w or 0.0)) for w in watts]
    else:
        series = [max(0.0, float(w or 0.0)) for w in watts]

    n = len(series)
    if n < 5 or max(series, default=0.0) <= 0.0:
        return None

    # Prefix sums for O(N) exact sliding-window averages
    pref = [0.0] * (n + 1)
    acc = 0.0
    for i, val in enumerate(series):
        acc += val
        pref[i + 1] = acc

    peaks: Dict[str, int] = {"sample_count": n}
    for key, win in MMP_WINDOWS:
        if n < win:
            peaks[key] = 0
            continue
        best = 0.0
        for i in range(win, n + 1):
            avg = (pref[i] - pref[i - win]) / win
            if avg > best:
                best = avg
        peaks[key] = int(round(best))

    # Monotonicity guarantee across durations
    if peaks["20m"] > 0 and peaks["60m"] > peaks["20m"]:
        peaks["20m"] = peaks["60m"]
    if peaks["5m"] > 0 and peaks["20m"] > peaks["5m"]:
        peaks["5m"] = peaks["20m"]
    if peaks["1m"] > 0 and peaks["5m"] > peaks["1m"]:
        peaks["1m"] = peaks["5m"]
    if peaks["30s"] > 0 and peaks["1m"] > peaks["30s"]:
        peaks["30s"] = peaks["1m"]
    if peaks["5s"] > 0 and peaks["30s"] > peaks["5s"]:
        peaks["5s"] = peaks["30s"]

    return peaks


def save_activity_mmp_peaks(user_id: str, activity_id: str, peaks: Optional[Dict[str, int]]) -> None:
    """Persists computed 1-Hz MMP peaks (or a has_power_stream=0 sentinel) per user and activity."""
    if not activity_id:
        return
    has_stream = 1 if (peaks and any(peaks.get(k, 0) > 0 for k, _ in MMP_WINDOWS)) else 0
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO strava_activity_mmp_peaks (
            user_id, activity_id, has_power_stream,
            peak_5s, peak_30s, peak_1m, peak_5m, peak_20m, peak_60m,
            sample_count, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, activity_id) DO UPDATE SET
            has_power_stream = excluded.has_power_stream,
            peak_5s = excluded.peak_5s,
            peak_30s = excluded.peak_30s,
            peak_1m = excluded.peak_1m,
            peak_5m = excluded.peak_5m,
            peak_20m = excluded.peak_20m,
            peak_60m = excluded.peak_60m,
            sample_count = excluded.sample_count,
            computed_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            str(activity_id),
            has_stream,
            int((peaks or {}).get("5s", 0)),
            int((peaks or {}).get("30s", 0)),
            int((peaks or {}).get("1m", 0)),
            int((peaks or {}).get("5m", 0)),
            int((peaks or {}).get("20m", 0)),
            int((peaks or {}).get("60m", 0)),
            int((peaks or {}).get("sample_count", 0)),
        ),
    )
    conn.commit()
    conn.close()


def get_cached_mmp_peaks_map(user_id: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """Returns a dict mapping activity_id -> cached MMP peaks for the given user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT activity_id, has_power_stream, peak_5s, peak_30s, peak_1m, peak_5m, peak_20m, peak_60m, sample_count
        FROM strava_activity_mmp_peaks
        WHERE user_id = ?
        """,
        (uid,),
    )
    rows = c.fetchall()
    conn.close()
    out: Dict[str, Dict[str, int]] = {}
    for r in rows or []:
        out[str(r["activity_id"])] = {
            "has_power_stream": bool(r["has_power_stream"]),
            "5s": int(r["peak_5s"] or 0),
            "30s": int(r["peak_30s"] or 0),
            "1m": int(r["peak_1m"] or 0),
            "5m": int(r["peak_5m"] or 0),
            "20m": int(r["peak_20m"] or 0),
            "60m": int(r["peak_60m"] or 0),
            "sample_count": int(r["sample_count"] or 0),
        }
    return out


def _parse_strava_rate_limits(headers: Any) -> Dict[str, int]:
    """Parses Strava X-ReadRateLimit-* or X-RateLimit-* headers into short/daily usage & limits."""
    out: Dict[str, int] = {}
    if not headers:
        return out
    usage_str = headers.get("X-ReadRateLimit-Usage") or headers.get("X-RateLimit-Usage") or ""
    limit_str = headers.get("X-ReadRateLimit-Limit") or headers.get("X-RateLimit-Limit") or ""
    try:
        if "," in usage_str:
            u_short, u_daily = usage_str.split(",", 1)
            out["short_usage"] = int(u_short.strip())
            out["daily_usage"] = int(u_daily.strip())
        if "," in limit_str:
            l_short, l_daily = limit_str.split(",", 1)
            out["short_limit"] = int(l_short.strip())
            out["daily_limit"] = int(l_daily.strip())
    except Exception:
        pass
    return out


def _count_eligible_power_rides_and_synced(uid: str) -> Dict[str, int]:
    """Counts user's cycling rides with power telemetry and how many have cached MMP peaks."""
    from app.services.strain_model_service import is_cycling_sport

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT a.id, a.name, a.sport_type, a.average_watts, a.weighted_average_watts, a.kilojoules,
               m.has_power_stream
        FROM strava_activities a
        LEFT JOIN strava_activity_mmp_peaks m
               ON m.user_id = a.user_id AND m.activity_id = a.id
        WHERE a.user_id = ?
        """,
        (uid,),
    )
    rows = c.fetchall()
    conn.close()

    total_eligible = 0
    synced_count = 0
    stream_backed_count = 0

    for r in rows or []:
        avg_w = float(r["average_watts"] or 0.0)
        np_w = float(r["weighted_average_watts"] or 0.0)
        kj = float(r["kilojoules"] or 0.0)
        if avg_w <= 0 and np_w <= 0 and kj <= 0:
            continue
        act_dict = {
            "id": r["id"],
            "name": r["name"],
            "sport_type": r["sport_type"],
            "average_watts": avg_w,
            "weighted_average_watts": np_w,
            "kilojoules": kj,
        }
        if not is_cycling_sport(r["sport_type"] or "", r["name"] or "", activity=act_dict):
            continue
        total_eligible += 1
        if r["has_power_stream"] is not None:
            synced_count += 1
            if int(r["has_power_stream"]) == 1:
                stream_backed_count += 1

    remaining = max(0, total_eligible - synced_count)
    pct = round((synced_count / total_eligible) * 100.0, 1) if total_eligible > 0 else 100.0
    return {
        "total_eligible": total_eligible,
        "synced_count": synced_count,
        "stream_backed_count": stream_backed_count,
        "remaining_count": remaining,
        "pct_complete": pct,
    }


def get_strava_stream_backfill_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns per-user progress for background 1-Hz power stream fetching and MMP caching."""
    uid = user_id or get_current_user_id()
    status = get_setting("strava_stream_backfill_status", {}, user_id=uid) or {}

    if status.get("in_progress") and status.get("started_at_ts"):
        if time.time() - float(status.get("started_at_ts", 0)) > 600:
            status["in_progress"] = False
            set_setting("strava_stream_backfill_status", status, user_id=uid)

    counts = _count_eligible_power_rides_and_synced(uid)
    now_ts = time.time()
    cooldown_until_ts = float(status.get("cooldown_until_ts") or 0.0)
    in_cooldown = cooldown_until_ts > now_ts
    cooldown_remaining_sec = max(0, int(cooldown_until_ts - now_ts)) if in_cooldown else 0

    tokens = get_setting("strava_tokens", {}, user_id=uid)
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    has_token = bool(access_token and len(str(access_token).strip()) >= 12)

    return {
        **counts,
        "in_progress": bool(status.get("in_progress", False)),
        "rate_limited": bool(in_cooldown or status.get("rate_limited", False)) and counts["remaining_count"] > 0,
        "cooldown_until_ts": cooldown_until_ts if in_cooldown else None,
        "cooldown_remaining_sec": cooldown_remaining_sec,
        "last_batch_fetched": int(status.get("last_batch_fetched", 0)),
        "last_error": status.get("last_error"),
        "last_run_at": status.get("last_run_at"),
        "strava_connected": has_token,
    }


def sync_missing_power_streams(user_id: Optional[str] = None, max_per_run: int = 40) -> Dict[str, Any]:
    """
    Rate-limit-safe worker that computes 1-Hz MMP peaks for cycling rides with power:
    1) Reuses any already-cached strava_activity_streams rows locally (zero API calls).
    2) Fetches missing /activities/{id}/streams from Strava (newest rides first),
       respecting X-ReadRateLimit-Usage headers and HTTP 429 cooldowns.
    """
    from app.services.strain_model_service import is_cycling_sport

    uid = user_id or get_current_user_id()
    tokens = get_setting("strava_tokens", {}, user_id=uid)
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None

    status = get_setting("strava_stream_backfill_status", {}, user_id=uid) or {}
    if status.get("in_progress") and status.get("started_at_ts"):
        if time.time() - float(status.get("started_at_ts", 0)) <= 600:
            return {"success": True, "already_running": True, **get_strava_stream_backfill_status(uid)}

    status_obj = {
        "in_progress": True,
        "started_at_ts": time.time(),
        "rate_limited": False,
        "cooldown_until_ts": 0.0,
        "last_batch_fetched": 0,
        "last_error": None,
        "last_run_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    set_setting("strava_stream_backfill_status", status_obj, user_id=uid)

    batch_fetched = 0
    rate_limited = False
    cooldown_until_ts = 0.0
    err_msg = None

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT a.id, a.name, a.sport_type, a.start_date, a.average_watts, a.weighted_average_watts, a.kilojoules,
                   s.streams_json
            FROM strava_activities a
            LEFT JOIN strava_activity_mmp_peaks m
                   ON m.user_id = a.user_id AND m.activity_id = a.id
            LEFT JOIN strava_activity_streams s
                   ON s.user_id = a.user_id AND s.activity_id = a.id
            WHERE a.user_id = ?
              AND m.activity_id IS NULL
            ORDER BY a.start_date DESC
            """,
            (uid,),
        )
        candidates = c.fetchall()
        conn.close()

        to_fetch_network: List[str] = []
        for row in candidates or []:
            avg_w = float(row["average_watts"] or 0.0)
            np_w = float(row["weighted_average_watts"] or 0.0)
            kj = float(row["kilojoules"] or 0.0)
            if avg_w <= 0 and np_w <= 0 and kj <= 0:
                continue
            act_dict = {
                "id": row["id"],
                "name": row["name"],
                "sport_type": row["sport_type"],
                "average_watts": avg_w,
                "weighted_average_watts": np_w,
                "kilojoules": kj,
            }
            if not is_cycling_sport(row["sport_type"] or "", row["name"] or "", activity=act_dict):
                continue

            act_id = str(row["id"])
            # Local cache hit in strava_activity_streams -> compute MMP with 0 network calls
            if row["streams_json"]:
                try:
                    cached = json.loads(row["streams_json"])
                    peaks = compute_mmp_peaks_from_streams(cached)
                    save_activity_mmp_peaks(uid, act_id, peaks)
                    batch_fetched += 1
                    continue
                except Exception:
                    pass

            if act_id.isdigit():
                to_fetch_network.append(act_id)

        if to_fetch_network and access_token and len(str(access_token).strip()) >= 12:
            headers = {"Authorization": f"Bearer {access_token}"}
            for act_id in to_fetch_network[:max_per_run]:
                url = f"{STRAVA_API_BASE}/activities/{act_id}/streams?keys=time,watts,heartrate,cadence&key_by_type=true"
                try:
                    res = requests.get(url, headers=headers, timeout=8)
                    if res.status_code == 401 and isinstance(tokens, dict) and tokens.get("refresh_token"):
                        refreshed = refresh_strava_token(user_id=uid)
                        if refreshed:
                            access_token = refreshed
                            headers = {"Authorization": f"Bearer {refreshed}"}
                            res = requests.get(url, headers=headers, timeout=8)

                    if res.status_code == 429:
                        rate_limited = True
                        cooldown_until_ts = time.time() + 900
                        err_msg = "Strava API rate limit reached; paused for 15 minutes."
                        break

                    if res.status_code == 200:
                        raw_payload = res.json()
                        peaks = compute_mmp_peaks_from_streams(raw_payload)
                        save_activity_mmp_peaks(uid, act_id, peaks)
                        normalized = _normalize_stream_payload(raw_payload)
                        payload_to_cache = normalized if normalized else {"unavailable": True}
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute(
                            """
                            INSERT INTO strava_activity_streams (user_id, activity_id, streams_json)
                            VALUES (?, ?, ?)
                            ON CONFLICT(user_id, activity_id) DO UPDATE SET
                                streams_json = excluded.streams_json,
                                fetched_at = CURRENT_TIMESTAMP
                            """,
                            (uid, act_id, json.dumps(payload_to_cache)),
                        )
                        conn.commit()
                        conn.close()
                        batch_fetched += 1
                    elif res.status_code == 404:
                        save_activity_mmp_peaks(uid, act_id, None)
                        batch_fetched += 1
                    elif res.status_code >= 500:
                        err_msg = f"Strava temporary error HTTP {res.status_code}"
                        break

                    rl = _parse_strava_rate_limits(res.headers)
                    s_use = rl.get("short_usage", 0)
                    s_lim = rl.get("short_limit", 0)
                    d_use = rl.get("daily_usage", 0)
                    d_lim = rl.get("daily_limit", 0)
                    if (s_lim > 0 and s_use >= int(s_lim * 0.85)) or (d_lim > 0 and d_use >= int(d_lim * 0.90)):
                        rate_limited = True
                        cooldown_until_ts = time.time() + 900
                        err_msg = "Approaching Strava API rate limit; pausing safely for 15 minutes."
                        break

                    time.sleep(0.25)
                except Exception as exc:
                    err_msg = str(exc)
                    break
    except Exception as e:
        err_msg = str(e)
    finally:
        status_obj["in_progress"] = False
        status_obj["rate_limited"] = rate_limited
        status_obj["cooldown_until_ts"] = cooldown_until_ts
        status_obj["last_batch_fetched"] = batch_fetched
        status_obj["last_error"] = err_msg
        status_obj["last_run_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        set_setting("strava_stream_backfill_status", status_obj, user_id=uid)

    return {"success": err_msg is None, **get_strava_stream_backfill_status(uid)}


def trigger_power_stream_backfill_async(user_id: Optional[str] = None, max_per_run: int = 40) -> Dict[str, Any]:
    """Starts rate-limit-safe background 1-Hz power stream backfill if eligible rides remain."""
    uid = user_id or get_current_user_id()
    cur = get_strava_stream_backfill_status(uid)
    if cur.get("in_progress"):
        return {"started": False, "already_running": True, **cur}
    if cur.get("remaining_count", 0) <= 0:
        return {"started": False, "already_complete": True, **cur}
    if not cur.get("strava_connected"):
        return {"started": False, "reason": "Strava not connected", **cur}
    if cur.get("cooldown_remaining_sec", 0) > 0:
        return {"started": False, "reason": "Rate-limit cooldown active", **cur}

    t = threading.Thread(
        target=sync_missing_power_streams,
        kwargs={"user_id": uid, "max_per_run": max_per_run},
        daemon=True,
    )
    t.start()
    return {"started": True, "already_running": False, **cur, "in_progress": True}




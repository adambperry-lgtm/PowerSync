import requests
import datetime
from typing import Dict, Any, List, Optional
from app.database import get_setting, set_setting, get_db_connection

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

def get_strava_auth_url(redirect_uri: str) -> str:
    client_id = get_setting("strava_client_id", "")
    scope = "read,activity:read_all"
    return f"{STRAVA_AUTH_URL}?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&approval_prompt=auto&scope={scope}"

def exchange_strava_code(code: str) -> Dict[str, Any]:
    client_id = str(get_setting("strava_client_id", "")).strip()
    client_secret = str(get_setting("strava_client_secret", "")).strip()
    
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
            set_setting("strava_tokens", token_info)
            return {"success": True, "token_info": token_info}
        return {"success": False, "error": f"Strava returned HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"success": False, "error": f"Network error connecting to Strava: {str(e)}"}

def refresh_strava_token() -> Optional[str]:
    tokens = get_setting("strava_tokens", {})
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None
        
    client_id = get_setting("strava_client_id", "")
    client_secret = get_setting("strava_client_secret", "")
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    res = requests.post(STRAVA_TOKEN_URL, data=data, timeout=10)
    if res.status_code == 200:
        new_tokens = res.json()
        set_setting("strava_tokens", new_tokens)
        return new_tokens.get("access_token")
    return None

def fetch_recent_strava_activities(limit: int = 20) -> List[Dict[str, Any]]:
    tokens = get_setting("strava_tokens", {})
    access_token = tokens.get("access_token")
    if not access_token:
        print("fetch_recent_strava_activities: No strava access_token found.")
        return []
        
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        res = requests.get(f"{STRAVA_API_BASE}/athlete/activities?per_page={limit}", headers=headers, timeout=10)
        
        if res.status_code == 401:
            print("Strava access token expired (401). Attempting token refresh...")
            access_token = refresh_strava_token()
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
    conn = get_db_connection()
    c = conn.cursor()
    
    saved = []
    for a in activities:
        act_id = str(a.get("id"))
        name = a.get("name", "Activity")
        sport = a.get("type", "Ride")
        start_date = a.get("start_date", "")
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
                id, name, sport_type, start_date, moving_time_sec, distance_meters,
                total_elevation_gain, average_watts, weighted_average_watts,
                average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                moving_time_sec = excluded.moving_time_sec,
                average_watts = excluded.average_watts,
                weighted_average_watts = excluded.weighted_average_watts
        """, (act_id, name, sport, start_date, moving_time, dist, elev, watts, w_watts, hr, max_hr, suffer, kj, str(a)))
        
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

def get_strava_trailing_stats(activities: Optional[List[Dict[str, Any]]] = None, days: int = 7) -> Dict[str, Any]:
    """
    Computes trailing 7-day training load with exponential recency weighting.
    More heavily weights recent training (e.g. yesterday) over training early in the cycle (7 days ago),
    accounting for acute fatigue decay (tau ~ 3.0 days).
    """
    import math
    if activities is None:
        strava_tokens = get_setting("strava_tokens", None)
        if strava_tokens:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM strava_activities ORDER BY start_date DESC LIMIT 30")
            rows = c.fetchall()
            conn.close()
            activities = [dict(r) for r in rows] if rows else []
        else:
            activities = []

    if not activities:
        from app.services.mock_data import get_mock_weekly_stats
        return get_mock_weekly_stats()

    today = datetime.date.today()

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
        s_date = act.get("start_date", "")
        if not s_date:
            continue
        date_key = s_date[:10]
        if date_key in daily_buckets:
            suffer = act.get("suffer_score")
            if suffer is None or suffer == 0:
                dur_h = act.get("moving_time_sec", 0) / 3600.0
                suffer = round(dur_h * 50)
            daily_buckets[date_key]["tss"] += int(suffer or 0)
            daily_buckets[date_key]["moving_sec"] += int(act.get("moving_time_sec", 0))
            daily_buckets[date_key]["elevation_m"] += int(act.get("total_elevation_gain", 0))
            daily_buckets[date_key]["distance_m"] += float(act.get("distance_meters", 0))
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


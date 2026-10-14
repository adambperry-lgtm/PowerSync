import requests
import datetime
import secrets
from typing import Dict, Any, Optional
from app.database import get_setting, set_setting, get_db_connection

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"

def get_whoop_auth_url(redirect_uri: str) -> str:
    client_id = get_setting("whoop_client_id", "")
    scopes = "offline read:recovery read:cycles read:workout read:sleep read:profile"
    state = secrets.token_urlsafe(16)
    set_setting("whoop_oauth_state", state)
    return f"{WHOOP_AUTH_URL}?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={state}"

def exchange_whoop_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    client_id = get_setting("whoop_client_id", "").strip()
    client_secret = get_setting("whoop_client_secret", "").strip()
    
    if not client_id:
        return {"success": False, "error": "Missing Whoop Client ID. Please configure it in Settings."}
    if not client_secret:
        return {"success": False, "error": "Missing Whoop Client Secret. Please open Settings and paste your Client Secret from developer.whoop.com."}
    if client_secret.startswith("{") or "error" in client_secret:
        return {"success": False, "error": "Invalid Whoop Client Secret. An error message was accidentally saved as the secret. Please paste your actual Client Secret from developer.whoop.com."}
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        # Whoop OAuth client expects client_secret_post (credentials in POST body)
        res = requests.post(
            WHOOP_TOKEN_URL,
            data=data,
            headers=headers,
            timeout=10
        )
        if res.status_code == 200:
            token_info = res.json()
            set_setting("whoop_tokens", token_info)
            return {"success": True, "token_info": token_info}
        return {"success": False, "error": f"Whoop returned HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"success": False, "error": f"Network error connecting to Whoop: {str(e)}"}

def refresh_whoop_token() -> Optional[str]:
    tokens = get_setting("whoop_tokens", {})
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("Whoop token refresh failed: No refresh_token found in stored tokens.")
        return None
        
    client_id = get_setting("whoop_client_id", "").strip()
    client_secret = get_setting("whoop_client_secret", "").strip()
    if not client_id or not client_secret or client_secret.startswith("{"):
        print("Whoop token refresh failed: Missing or invalid client_id/client_secret in settings.")
        return None

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "offline"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        res = requests.post(
            WHOOP_TOKEN_URL,
            data=data,
            headers=headers,
            timeout=10
        )
        if res.status_code == 200:
            new_tokens = res.json()
            if "refresh_token" not in new_tokens and refresh_token:
                new_tokens["refresh_token"] = refresh_token
            set_setting("whoop_tokens", new_tokens)
            print("Successfully refreshed Whoop access token!")
            return new_tokens.get("access_token")
        else:
            print(f"Whoop token refresh returned HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Error refreshing Whoop token: {e}")
    return None

def get_trailing_whoop_stats(days: int = 7) -> Dict[str, Any]:
    """
    Computes trailing 7-day average daily strain and peak strain days from the database.
    Excludes today's incomplete/morning cycle to accurately measure trailing physiological load.
    """
    today_iso = datetime.date.today().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT date, day_strain, recovery_score, hrv_rmssd
        FROM whoop_metrics
        ORDER BY date DESC
        LIMIT ?
    """, (days + 3,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return {
            "trailing_7d_strain_avg": 0.0,
            "trailing_7d_high_strain_count": 0,
            "trailing_strains": [],
            "days_analyzed": 0
        }

    all_records = [dict(r) for r in rows]
    # Filter for completed days prior to today
    completed_days = [r for r in all_records if r["date"] != today_iso and r["day_strain"] is not None]
    target_records = completed_days[:days]
    if not target_records:
        target_records = all_records[:days]

    strains = [float(r["day_strain"] or 0.0) for r in target_records]
    if not strains:
        return {
            "trailing_7d_strain_avg": 0.0,
            "recent_weighted_strain": 0.0,
            "yesterday_strain": 0.0,
            "strain_profile": "No Data",
            "trailing_7d_high_strain_count": 0,
            "trailing_strains": [],
            "days_analyzed": 0
        }

    import math
    avg_strain = round(sum(strains) / len(strains), 1)
    high_strain_count = sum(1 for s in strains if s >= 14.0)

    # Exponential recency weighting with half-life decay tau = 3.0 days
    # target_records[0] is Day 1 ago (yesterday), decaying to Day 7
    weights = [math.exp(-i / 3.0) for i in range(len(strains))]
    w_sum = sum(weights)
    recent_weighted_strain = round(sum(s * w for s, w in zip(strains, weights)) / w_sum, 1)

    yesterday_strain = round(strains[0], 1) if strains else 0.0

    # Analyze load concentration across the 7-day cycle
    if yesterday_strain >= 14.0 or (avg_strain > 0 and yesterday_strain >= avg_strain * 1.25):
        strain_profile = "Recent Surge (Yesterday Heavy)"
    elif yesterday_strain < 8.0 and recent_weighted_strain < avg_strain:
        strain_profile = "Front-Loaded (Fresh Today)"
    else:
        strain_profile = "Evenly Distributed"

    return {
        "trailing_7d_strain_avg": avg_strain,
        "recent_weighted_strain": recent_weighted_strain,
        "yesterday_strain": yesterday_strain,
        "strain_profile": strain_profile,
        "trailing_7d_high_strain_count": high_strain_count,
        "trailing_strains": strains,
        "days_analyzed": len(strains)
    }

def fetch_latest_whoop_metrics() -> Dict[str, Any]:
    tokens = get_setting("whoop_tokens", {})
    access_token = tokens.get("access_token")
    if not access_token:
        return {"error": "Whoop not connected", "auth_expired": True}
        
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 1. Recovery (fetch last 10 records for trailing load)
    rec_res = None
    try:
        rec_res = requests.get(f"{WHOOP_API_BASE}/recovery?limit=10", headers=headers, timeout=10)
        if rec_res.status_code == 401:
            access_token = refresh_whoop_token()
            if access_token:
                headers = {"Authorization": f"Bearer {access_token}"}
                rec_res = requests.get(f"{WHOOP_API_BASE}/recovery?limit=10", headers=headers, timeout=10)
            else:
                return {
                    "error": "Whoop session expired. Please re-authenticate Whoop in Settings or top navbar.",
                    "auth_expired": True
                }
    except Exception as e:
        return {"error": f"Network error fetching Whoop recovery: {str(e)}"}

    if not rec_res or rec_res.status_code != 200:
        return {
            "error": f"Whoop API returned error {rec_res.status_code if rec_res else 'timeout'}: {rec_res.text if rec_res else ''}",
            "auth_expired": (rec_res.status_code == 401) if rec_res else False
        }

    rec_records = rec_res.json().get("records", [])
    if not rec_records:
        return {"error": "No recovery records found from Whoop for this account."}

    # 2. Sleep (fetch last 10 records)
    sleep_records = []
    try:
        sleep_res = requests.get(f"{WHOOP_API_BASE}/activity/sleep?limit=10", headers=headers, timeout=10)
        if sleep_res.status_code == 200:
            sleep_records = sleep_res.json().get("records", [])
    except Exception as e:
        print(f"Error fetching Whoop sleep: {e}")

    # 3. Cycle / Strain (fetch last 10 records)
    cycle_records = []
    try:
        cycle_res = requests.get(f"{WHOOP_API_BASE}/cycle?limit=10", headers=headers, timeout=10)
        if cycle_res.status_code == 200:
            cycle_records = cycle_res.json().get("records", [])
    except Exception as e:
        print(f"Error fetching Whoop cycle strain: {e}")

    # Build index mappings
    rec_by_cycle = {r.get("cycle_id"): r for r in rec_records if r.get("cycle_id")}
    sleep_by_date = {}
    for s in sleep_records:
        start_iso = s.get("start", "")
        if start_iso:
            sleep_by_date[start_iso[:10]] = s

    # Persist all available trailing cycles and recoveries to SQLite
    today_iso = datetime.date.today().isoformat()
    conn = get_db_connection()
    c = conn.cursor()

    latest_date = today_iso
    latest_rec_score = None
    latest_hrv = None
    latest_rhr = None
    latest_sleep_perf = None
    latest_sleep_hrs = None
    latest_strain = None

    for idx, cycle in enumerate(cycle_records):
        cid = cycle.get("id")
        start_iso = cycle.get("start", "")
        if not start_iso:
            continue
        cycle_date = start_iso[:10]
        strain_val = round(cycle.get("score", {}).get("strain", 0.0), 1)

        rec = rec_by_cycle.get(cid)
        rec_score = rec.get("score", {}).get("recovery_score") if rec else None
        hrv_val = rec.get("score", {}).get("hrv_rmssd_milli") if rec else None
        rhr_val = rec.get("score", {}).get("resting_heart_rate") if rec else None

        slp = sleep_by_date.get(cycle_date)
        sleep_perf = slp.get("score", {}).get("sleep_performance_percentage") if slp else None
        milli_in_bed = slp.get("score", {}).get("stage_summary", {}).get("total_in_bed_time_milli", 0) if slp else 0
        sleep_hrs = round(milli_in_bed / (1000.0 * 3600.0), 1) if milli_in_bed > 0 else None

        # Track latest (first in list)
        if idx == 0:
            latest_date = cycle_date
            latest_rec_score = rec_score
            latest_hrv = hrv_val
            latest_rhr = rhr_val
            latest_sleep_perf = sleep_perf
            latest_sleep_hrs = sleep_hrs
            latest_strain = strain_val

        c.execute("""
            INSERT INTO whoop_metrics (
                date, recovery_score, hrv_rmssd, resting_heart_rate,
                sleep_performance, sleep_duration_hours, day_strain
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                recovery_score = COALESCE(excluded.recovery_score, whoop_metrics.recovery_score),
                hrv_rmssd = COALESCE(excluded.hrv_rmssd, whoop_metrics.hrv_rmssd),
                resting_heart_rate = COALESCE(excluded.resting_heart_rate, whoop_metrics.resting_heart_rate),
                sleep_performance = COALESCE(excluded.sleep_performance, whoop_metrics.sleep_performance),
                sleep_duration_hours = COALESCE(excluded.sleep_duration_hours, whoop_metrics.sleep_duration_hours),
                day_strain = COALESCE(excluded.day_strain, whoop_metrics.day_strain)
        """, (
            cycle_date,
            int(rec_score) if rec_score is not None else 50,
            round(hrv_val, 1) if hrv_val is not None else 35.0,
            int(rhr_val) if rhr_val is not None else 55,
            int(sleep_perf) if sleep_perf is not None else 80,
            sleep_hrs or 7.0,
            strain_val
        ))

    conn.commit()
    conn.close()

    trailing_stats = get_trailing_whoop_stats(days=7)

    return {
        "success": True,
        "date": latest_date,
        "recovery_score": latest_rec_score,
        "hrv_rmssd": latest_hrv,
        "resting_heart_rate": latest_rhr,
        "sleep_performance": latest_sleep_perf,
        "sleep_duration_hours": latest_sleep_hrs,
        "day_strain": latest_strain,
        "trailing_7d_strain_avg": trailing_stats["trailing_7d_strain_avg"],
        "trailing_7d_high_strain_count": trailing_stats["trailing_7d_high_strain_count"],
        "trailing_strains": trailing_stats["trailing_strains"]
    }

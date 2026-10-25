import requests
import datetime
import secrets
import zoneinfo
from typing import Dict, Any, Optional
from app.database import (
    get_setting,
    set_setting,
    get_db_connection,
    get_current_user_id,
    get_athlete_date,
    get_athlete_timezone,
    DEFAULT_USER_ID,
    GUEST_USER_ID
)

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"

def get_whoop_auth_url(redirect_uri: str, state: Optional[str] = None, user_id: Optional[str] = None) -> str:
    uid = user_id or get_current_user_id()
    client_id = get_setting("whoop_client_id", "", user_id=uid)
    scopes = "offline read:recovery read:cycles read:workout read:sleep read:profile"
    auth_state = state or secrets.token_urlsafe(16)
    return f"{WHOOP_AUTH_URL}?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={auth_state}"

def exchange_whoop_code(code: str, redirect_uri: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    client_id = str(get_setting("whoop_client_id", "", user_id=uid) or "").strip()
    client_secret = str(get_setting("whoop_client_secret", "", user_id=uid) or "").strip()
    
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
            target_users = {DEFAULT_USER_ID, GUEST_USER_ID} if uid in (DEFAULT_USER_ID, GUEST_USER_ID) else {uid}
            for u in target_users:
                set_setting("whoop_tokens", token_info, user_id=u)
            return {"success": True, "token_info": token_info}
        return {"success": False, "error": f"Whoop returned HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"success": False, "error": f"Network error connecting to Whoop: {str(e)}"}

def refresh_whoop_token(user_id: Optional[str] = None) -> Optional[str]:
    uid = user_id or get_current_user_id()
    tokens = get_setting("whoop_tokens", {}, user_id=uid)
    if not tokens and uid == GUEST_USER_ID:
        tokens = get_setting("whoop_tokens", {}, user_id=DEFAULT_USER_ID)
    refresh_token = tokens.get("refresh_token") if isinstance(tokens, dict) else None
    if not refresh_token:
        print("Whoop token refresh failed: No refresh_token found in stored tokens.")
        return None
        
    client_id = str(get_setting("whoop_client_id", "", user_id=uid) or "").strip()
    client_secret = str(get_setting("whoop_client_secret", "", user_id=uid) or "").strip()
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
            target_users = {DEFAULT_USER_ID, GUEST_USER_ID} if uid in (DEFAULT_USER_ID, GUEST_USER_ID) else {uid}
            for u in target_users:
                set_setting("whoop_tokens", new_tokens, user_id=u)
            print("Successfully refreshed Whoop access token!")
            return new_tokens.get("access_token")
        else:
            print(f"Whoop token refresh returned HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Error refreshing Whoop token: {e}")
    return None

def get_trailing_whoop_stats(days: int = 7, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes trailing 7-day average daily strain and peak strain days from the database for user_id.
    Excludes today's incomplete/morning cycle to accurately measure trailing physiological load.
    """
    uid = user_id or get_current_user_id()
    today_iso = get_athlete_date().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT date, day_strain, recovery_score, hrv_rmssd
        FROM whoop_metrics
        WHERE user_id = ?
        ORDER BY date DESC
        LIMIT ?
    """, (uid, days + 3))
    rows = c.fetchall()
    if not rows and uid == GUEST_USER_ID:
        c.execute("""
            SELECT date, day_strain, recovery_score, hrv_rmssd
            FROM whoop_metrics
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT ?
        """, (DEFAULT_USER_ID, days + 3))
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

def parse_whoop_iso_date(iso_str: Optional[str], tz: Any) -> Optional[str]:
    if not iso_str:
        return None
    try:
        cleaned = str(iso_str).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(tz).date().isoformat()
    except Exception:
        return str(iso_str)[:10] if len(str(iso_str)) >= 10 else None

def fetch_latest_whoop_metrics(user_id: Optional[str] = None) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    tokens = get_setting("whoop_tokens", {}, user_id=uid)
    if not tokens and uid == GUEST_USER_ID:
        tokens = get_setting("whoop_tokens", {}, user_id=DEFAULT_USER_ID)
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not access_token:
        return {"error": "Whoop not connected", "auth_expired": True}
        
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 1. Recovery (fetch last 10 records for trailing load)
    rec_res = None
    try:
        rec_res = requests.get(f"{WHOOP_API_BASE}/recovery?limit=10", headers=headers, timeout=10)
        if rec_res.status_code == 401:
            access_token = refresh_whoop_token(user_id=uid)
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

    tz = get_athlete_timezone(user_id=uid)
    today_iso = get_athlete_date(user_id=uid).isoformat()

    # Build index mappings
    rec_by_cycle = {r.get("cycle_id"): r for r in rec_records if r.get("cycle_id")}
    sleep_by_id = {s.get("id"): s for s in sleep_records if s.get("id")}
    sleep_by_cycle = {s.get("cycle_id"): s for s in sleep_records if s.get("cycle_id") and not s.get("nap")}
    cycle_by_id = {c.get("id"): c for c in cycle_records if c.get("id")}

    # Assemble daily biometric records: { date_str: { recovery_score, hrv_rmssd, resting_heart_rate, sleep_performance, sleep_duration_hours, day_strain } }
    daily_records: Dict[str, Dict[str, Any]] = {}

    def get_or_create_day(d: str) -> Dict[str, Any]:
        if d not in daily_records:
            daily_records[d] = {
                "recovery_score": None,
                "hrv_rmssd": None,
                "resting_heart_rate": None,
                "sleep_performance": None,
                "sleep_duration_hours": None,
                "day_strain": None
            }
        return daily_records[d]

    # Map cycles (strain)
    # cycle_records is in descending order (index 0 is current day, index 1 is yesterday, etc.)
    for idx, cycle in enumerate(cycle_records):
        cid = cycle.get("id")
        strain = round(float(cycle.get("score", {}).get("strain", 0.0) or 0.0), 1)
        
        # Primary date: (today - idx days)
        cycle_date = (get_athlete_date(user_id=uid) - datetime.timedelta(days=idx)).isoformat()
        
        # Cross-reference with matching recovery if available
        rec = rec_by_cycle.get(cid)
        if rec and rec.get("created_at"):
            parsed_rec_date = parse_whoop_iso_date(rec.get("created_at"), tz)
            if parsed_rec_date:
                if idx == 0:
                    cycle_date = today_iso
                elif parsed_rec_date != today_iso:
                    cycle_date = parsed_rec_date

        if cycle_date:
            day_entry = get_or_create_day(cycle_date)
            if idx == 0 or day_entry["day_strain"] is None:
                day_entry["day_strain"] = strain

    # Map sleeps
    for idx, slp in enumerate(sleep_records):
        if slp.get("nap"):
            continue
        perf = slp.get("score", {}).get("sleep_performance_percentage")
        milli = slp.get("score", {}).get("stage_summary", {}).get("total_in_bed_time_milli", 0) or 0
        hrs = round(milli / (1000.0 * 3600.0), 1) if milli > 0 else None
        wake_date = parse_whoop_iso_date(slp.get("end") or slp.get("start"), tz)
        if idx == 0:
            today_entry = get_or_create_day(today_iso)
            if perf is not None:
                today_entry["sleep_performance"] = int(perf)
            if hrs is not None:
                today_entry["sleep_duration_hours"] = hrs
        if wake_date and wake_date != today_iso:
            day_entry = get_or_create_day(wake_date)
            if day_entry["sleep_performance"] is None and perf is not None:
                day_entry["sleep_performance"] = int(perf)
            if day_entry["sleep_duration_hours"] is None and hrs is not None:
                day_entry["sleep_duration_hours"] = hrs

    # Map recoveries
    for idx, rec in enumerate(rec_records):
        rec_score = rec.get("score", {}).get("recovery_score")
        hrv_val = rec.get("score", {}).get("hrv_rmssd_milli")
        rhr_val = rec.get("score", {}).get("resting_heart_rate")

        cid = rec.get("cycle_id")
        sid = rec.get("sleep_id")
        slp = sleep_by_id.get(sid) or sleep_by_cycle.get(cid)
        
        # Recovery date resolution
        rec_date = None
        if slp and slp.get("end"):
            rec_date = parse_whoop_iso_date(slp.get("end"), tz)
        if not rec_date and rec.get("created_at"):
            rec_date = parse_whoop_iso_date(rec.get("created_at"), tz)

        # Most recent recovery always populates today's card so athlete sees active recovery all day
        if idx == 0:
            today_entry = get_or_create_day(today_iso)
            if rec_score is not None:
                today_entry["recovery_score"] = int(rec_score)
            if hrv_val is not None:
                today_entry["hrv_rmssd"] = round(float(hrv_val), 1)
            if rhr_val is not None:
                today_entry["resting_heart_rate"] = int(rhr_val)
            if slp:
                s_perf = slp.get("score", {}).get("sleep_performance_percentage")
                s_milli = slp.get("score", {}).get("stage_summary", {}).get("total_in_bed_time_milli", 0) or 0
                if s_perf is not None:
                    today_entry["sleep_performance"] = int(s_perf)
                if s_milli > 0:
                    today_entry["sleep_duration_hours"] = round(s_milli / (1000.0 * 3600.0), 1)

        if rec_date and rec_date != today_iso:
            day_entry = get_or_create_day(rec_date)
            if day_entry["recovery_score"] is None and rec_score is not None:
                day_entry["recovery_score"] = int(rec_score)
            if day_entry["hrv_rmssd"] is None and hrv_val is not None:
                day_entry["hrv_rmssd"] = round(float(hrv_val), 1)
            if day_entry["resting_heart_rate"] is None and rhr_val is not None:
                day_entry["resting_heart_rate"] = int(rhr_val)
            if slp:
                s_perf = slp.get("score", {}).get("sleep_performance_percentage")
                s_milli = slp.get("score", {}).get("stage_summary", {}).get("total_in_bed_time_milli", 0) or 0
                if day_entry["sleep_performance"] is None and s_perf is not None:
                    day_entry["sleep_performance"] = int(s_perf)
                if day_entry["sleep_duration_hours"] is None and s_milli > 0:
                    day_entry["sleep_duration_hours"] = round(s_milli / (1000.0 * 3600.0), 1)

    # Persist all assembled days to SQLite
    target_users = {DEFAULT_USER_ID, GUEST_USER_ID} if uid in (DEFAULT_USER_ID, GUEST_USER_ID) else {uid}
    conn = get_db_connection()
    c = conn.cursor()
    for d_str, d_val in daily_records.items():
        if not d_str:
            continue
        for u in target_users:
            c.execute("""
                INSERT INTO whoop_metrics (
                    user_id, date, recovery_score, hrv_rmssd, resting_heart_rate,
                    sleep_performance, sleep_duration_hours, day_strain, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    recovery_score = COALESCE(excluded.recovery_score, whoop_metrics.recovery_score),
                    hrv_rmssd = COALESCE(excluded.hrv_rmssd, whoop_metrics.hrv_rmssd),
                    resting_heart_rate = COALESCE(excluded.resting_heart_rate, whoop_metrics.resting_heart_rate),
                    sleep_performance = COALESCE(excluded.sleep_performance, whoop_metrics.sleep_performance),
                    sleep_duration_hours = COALESCE(excluded.sleep_duration_hours, whoop_metrics.sleep_duration_hours),
                    day_strain = COALESCE(excluded.day_strain, whoop_metrics.day_strain),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                u,
                d_str,
                d_val["recovery_score"],
                d_val["hrv_rmssd"],
                d_val["resting_heart_rate"],
                d_val["sleep_performance"],
                d_val["sleep_duration_hours"],
                d_val["day_strain"]
            ))
    conn.commit()
    conn.close()

    # Record sync timestamp
    now_ts = datetime.datetime.now().timestamp()
    for u in target_users:
        set_setting("last_whoop_sync_timestamp", now_ts, user_id=u)

    # Read back latest row (prioritizing today's record)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? AND date = ?", (uid, today_iso))
    latest_row = c.fetchone()
    if not latest_row:
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (uid,))
        latest_row = c.fetchone()
    if not latest_row and uid == GUEST_USER_ID:
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? AND date = ?", (DEFAULT_USER_ID, today_iso))
        latest_row = c.fetchone()
    if not latest_row and uid == GUEST_USER_ID:
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (DEFAULT_USER_ID,))
        latest_row = c.fetchone()
    conn.close()

    trailing_stats = get_trailing_whoop_stats(days=7, user_id=uid)

    return {
        "success": True,
        "date": latest_row["date"] if latest_row else today_iso,
        "recovery_score": int(latest_row["recovery_score"]) if (latest_row and latest_row["recovery_score"] is not None) else None,
        "hrv_rmssd": float(latest_row["hrv_rmssd"]) if (latest_row and latest_row["hrv_rmssd"] is not None) else None,
        "resting_heart_rate": int(latest_row["resting_heart_rate"]) if (latest_row and latest_row["resting_heart_rate"] is not None) else None,
        "sleep_performance": int(latest_row["sleep_performance"]) if (latest_row and latest_row["sleep_performance"] is not None) else None,
        "sleep_duration_hours": float(latest_row["sleep_duration_hours"]) if (latest_row and latest_row["sleep_duration_hours"] is not None) else None,
        "day_strain": float(latest_row["day_strain"]) if (latest_row and latest_row["day_strain"] is not None) else None,
        "trailing_7d_strain_avg": trailing_stats.get("trailing_7d_strain_avg", 0.0),
        "trailing_7d_high_strain_count": trailing_stats.get("trailing_7d_high_strain_count", 0),
        "trailing_strains": trailing_stats.get("trailing_strains", [])
    }

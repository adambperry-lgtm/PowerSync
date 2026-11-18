import json
import secrets
import datetime
from typing import Any, Dict, List, Optional, Tuple
from app.database import (
    get_db_connection,
    get_setting,
    set_setting,
    get_current_user_id,
    get_athlete_date,
    set_athlete_weight_kg,
    set_athlete_weight_lbs,
    KG_TO_LBS,
    GUEST_USER_ID,
)


def get_or_create_apple_health_token(user_id: Optional[str] = None, regenerate: bool = False) -> str:
    """Returns the user's personal Apple Health webhook token, creating one if absent."""
    uid = user_id or get_current_user_id()
    if uid == GUEST_USER_ID:
        return ""
    existing = get_setting("apple_health_webhook_token", "", user_id=uid)
    if existing and isinstance(existing, str) and existing.strip() and not regenerate:
        return existing.strip()
    token = f"ps_ah_{secrets.token_urlsafe(24)}"
    set_setting("apple_health_webhook_token", token, user_id=uid)
    return token


def resolve_user_by_apple_health_token(token: Optional[str]) -> Optional[str]:
    """Resolves a user_id from a personal Apple Health webhook token."""
    if not token or not isinstance(token, str):
        return None
    clean = token.strip()
    if not clean:
        return None
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT user_id, value FROM settings WHERE key = 'apple_health_webhook_token'"
        )
        rows = c.fetchall()
        for r in rows:
            raw_val = r["value"]
            try:
                decoded = json.loads(raw_val) if raw_val else ""
            except Exception:
                decoded = raw_val
            if isinstance(decoded, str) and secrets.compare_digest(decoded.strip(), clean):
                uid = r["user_id"]
                if uid and uid != GUEST_USER_ID:
                    return uid
    finally:
        conn.close()
    return None


def _parse_date_str(raw: Any, fallback_date: Optional[str] = None) -> str:
    """Extracts YYYY-MM-DD from ISO, Health Auto Export ('2026-11-18 07:15:00 -0800'), or date strings."""
    if isinstance(raw, str) and raw.strip():
        s = raw.strip()
        # Fast path: starts with YYYY-MM-DD
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            cand = s[:10]
            try:
                datetime.date.fromisoformat(cand)
                return cand
            except ValueError:
                pass
        # Try common formats
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
    return fallback_date or get_athlete_date().isoformat()


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        return f if (f == f) else None  # guard NaN
    except (TypeError, ValueError):
        return None


def _to_int(val: Any) -> Optional[int]:
    f = _to_float(val)
    if f is None:
        return None
    return int(round(f))


def _compute_readiness_score(
    hrv_sdnn: Optional[float],
    resting_hr: Optional[int],
    sleep_hours: Optional[float],
    user_id: str,
) -> int:
    """
    Computes a 1-99 physiological readiness/recovery score from Apple Health
    HRV (SDNN), Resting HR, and Sleep duration against the athlete's trailing
    14-day baseline (or sensible defaults when <3 days of history exist).
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT hrv_sdnn, resting_heart_rate, sleep_duration_hours
            FROM apple_health_records
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 14
            """,
            (user_id,),
        )
        hist = c.fetchall()
    finally:
        conn.close()

    hrvs = [float(r["hrv_sdnn"]) for r in hist if r["hrv_sdnn"] is not None and float(r["hrv_sdnn"]) > 0]
    rhrs = [float(r["resting_heart_rate"]) for r in hist if r["resting_heart_rate"] is not None and float(r["resting_heart_rate"]) > 0]

    base_hrv = sum(hrvs) / len(hrvs) if len(hrvs) >= 3 else 50.0
    base_rhr = sum(rhrs) / len(rhrs) if len(rhrs) >= 3 else 58.0

    # Baseline 68, adjusted by HRV (+), RHR (-), and Sleep (+)
    score = 68.0
    if hrv_sdnn is not None and hrv_sdnn > 0 and base_hrv > 0:
        hrv_delta_pct = (hrv_sdnn - base_hrv) / base_hrv
        score += max(-22.0, min(22.0, hrv_delta_pct * 55.0))
    if resting_hr is not None and resting_hr > 0 and base_rhr > 0:
        rhr_delta = base_rhr - float(resting_hr)  # positive when RHR is lower than baseline
        score += max(-15.0, min(15.0, rhr_delta * 2.5))
    if sleep_hours is not None and sleep_hours > 0:
        sleep_delta = sleep_hours - 7.5
        score += max(-20.0, min(12.0, sleep_delta * 8.0))

    return max(1, min(99, int(round(score))))


def _normalize_health_auto_export(payload: Dict[str, Any], default_date: str) -> Dict[str, Dict[str, Any]]:
    """
    Parses Health Auto Export JSON format:
    { "data": { "metrics": [ { "name": "...", "units": "...", "data": [ { "date": "...", "qty": ... } ] } ] } }
    Returns dict keyed by YYYY-MM-DD -> normalized metric dict.
    """
    by_date: Dict[str, Dict[str, Any]] = {}
    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    metrics = data_block.get("metrics", [])
    if not isinstance(metrics, list):
        return by_date

    def ensure_day(d: str) -> Dict[str, Any]:
        if d not in by_date:
            by_date[d] = {"date": d}
        return by_date[d]

    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name", "")).strip().lower()
        units = str(metric.get("units", "")).strip().lower()
        samples = metric.get("data", [])
        if not isinstance(samples, list):
            continue

        for sample in samples:
            if not isinstance(sample, dict):
                continue
            d = _parse_date_str(sample.get("date") or sample.get("sleepStart") or sample.get("inBedStart"), default_date)
            day = ensure_day(d)

            if name in ("heart_rate_variability", "hrv", "heart_rate_variability_sdnn"):
                val = _to_float(sample.get("qty") or sample.get("avg") or sample.get("value"))
                if val is not None and val > 0:
                    day.setdefault("_hrv_list", []).append(val)

            elif name in ("resting_heart_rate", "rhr"):
                val = _to_float(sample.get("qty") or sample.get("avg") or sample.get("value"))
                if val is not None and val > 0:
                    day["resting_heart_rate"] = int(round(val))

            elif name in ("sleep_analysis", "sleep"):
                # Health Auto Export may send asleep/totalSleep/deep/rem in hrs, min, or sec
                asleep = _to_float(sample.get("asleep") or sample.get("totalSleep") or sample.get("qty"))
                deep = _to_float(sample.get("deep"))
                rem = _to_float(sample.get("rem"))
                in_bed = _to_float(sample.get("inBed"))

                def to_hours(v: Optional[float]) -> Optional[float]:
                    if v is None:
                        return None
                    if "min" in units:
                        return round(v / 60.0, 2)
                    if "sec" in units or v > 100:
                        return round(v / 3600.0, 2)
                    return round(v, 2)

                h_asleep = to_hours(asleep)
                h_deep = to_hours(deep)
                h_rem = to_hours(rem)
                h_in_bed = to_hours(in_bed)
                if h_asleep is not None and h_asleep > 0:
                    day["sleep_duration_hours"] = round(float(day.get("sleep_duration_hours") or 0.0) + h_asleep, 2)
                if h_deep is not None and h_deep >= 0:
                    day["sleep_deep_hours"] = round(float(day.get("sleep_deep_hours") or 0.0) + h_deep, 2)
                if h_rem is not None and h_rem >= 0:
                    day["sleep_rem_hours"] = round(float(day.get("sleep_rem_hours") or 0.0) + h_rem, 2)
                if h_asleep and h_in_bed and h_in_bed > 0:
                    day["sleep_efficiency_pct"] = round(min(100.0, (h_asleep / h_in_bed) * 100.0), 1)

            elif name in ("weight_body_mass", "body_mass", "weight"):
                val = _to_float(sample.get("qty") or sample.get("value"))
                if val is not None and val > 0:
                    if "lb" in units:
                        day["weight_lbs"] = round(val, 2)
                        day["weight_kg"] = round(val / KG_TO_LBS, 2)
                    else:
                        day["weight_kg"] = round(val, 2)
                        day["weight_lbs"] = round(val * KG_TO_LBS, 2)

            elif name in ("body_fat_percentage", "body_fat"):
                val = _to_float(sample.get("qty") or sample.get("value"))
                if val is not None and val > 0:
                    day["body_fat_pct"] = round(val * 100.0 if val <= 1.0 else val, 1)

            elif name in ("vo2_max", "vo2max"):
                val = _to_float(sample.get("qty") or sample.get("value"))
                if val is not None and val > 0:
                    day["vo2_max"] = round(val, 1)

            elif name in ("active_energy", "active_energy_burned"):
                val = _to_float(sample.get("qty") or sample.get("value"))
                if val is not None and val >= 0:
                    kcal = val / 4.184 if "kj" in units else val
                    day["active_energy_kcal"] = round(float(day.get("active_energy_kcal") or 0.0) + kcal, 1)

    # Collapse HRV sample lists to daily mean
    for day in by_date.values():
        hrv_list = day.pop("_hrv_list", None)
        if hrv_list:
            day["hrv_sdnn"] = round(sum(hrv_list) / len(hrv_list), 1)

    return by_date


def _normalize_flat_record(item: Dict[str, Any], default_date: str) -> Dict[str, Any]:
    """Normalizes a simple Apple Shortcuts / manual JSON record."""
    d = _parse_date_str(item.get("date") or item.get("day"), default_date)
    out: Dict[str, Any] = {"date": d}

    hrv = _to_float(item.get("hrv_sdnn") if item.get("hrv_sdnn") is not None else item.get("hrv"))
    if hrv is not None and hrv > 0:
        out["hrv_sdnn"] = round(hrv, 1)

    rhr = _to_int(item.get("resting_heart_rate") if item.get("resting_heart_rate") is not None else item.get("rhr"))
    if rhr is not None and rhr > 0:
        out["resting_heart_rate"] = rhr

    sleep = _to_float(
        item.get("sleep_duration_hours")
        if item.get("sleep_duration_hours") is not None
        else item.get("sleep_hours")
    )
    if sleep is not None and sleep >= 0:
        out["sleep_duration_hours"] = round(sleep, 2)

    deep = _to_float(item.get("sleep_deep_hours"))
    if deep is not None and deep >= 0:
        out["sleep_deep_hours"] = round(deep, 2)

    rem = _to_float(item.get("sleep_rem_hours"))
    if rem is not None and rem >= 0:
        out["sleep_rem_hours"] = round(rem, 2)

    eff = _to_float(item.get("sleep_efficiency_pct"))
    if eff is not None and eff > 0:
        out["sleep_efficiency_pct"] = round(min(100.0, eff), 1)

    w_kg = _to_float(item.get("weight_kg"))
    w_lbs = _to_float(item.get("weight_lbs") if item.get("weight_lbs") is not None else item.get("weight"))
    if w_kg is not None and w_kg > 0:
        out["weight_kg"] = round(w_kg, 2)
        out["weight_lbs"] = round(w_kg * KG_TO_LBS, 2)
    elif w_lbs is not None and w_lbs > 0:
        out["weight_lbs"] = round(w_lbs, 2)
        out["weight_kg"] = round(w_lbs / KG_TO_LBS, 2)

    bf = _to_float(item.get("body_fat_pct"))
    if bf is not None and bf > 0:
        out["body_fat_pct"] = round(bf, 1)

    vo2 = _to_float(item.get("vo2_max") if item.get("vo2_max") is not None else item.get("vo2max"))
    if vo2 is not None and vo2 > 0:
        out["vo2_max"] = round(vo2, 1)

    kcal = _to_float(
        item.get("active_energy_kcal")
        if item.get("active_energy_kcal") is not None
        else item.get("calories")
    )
    if kcal is not None and kcal >= 0:
        out["active_energy_kcal"] = round(kcal, 1)

    rec = _to_int(item.get("recovery_score"))
    if rec is not None and 1 <= rec <= 100:
        out["recovery_score"] = rec

    return out


def upsert_apple_health_record(
    record: Dict[str, Any],
    user_id: Optional[str] = None,
    source: str = "webhook",
    raw_payload: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Merges non-null fields into apple_health_records for (user_id, date) so partial
    pushes (e.g., morning HRV + evening weight) accumulate cleanly.
    """
    uid = user_id or get_current_user_id()
    date_str = _parse_date_str(record.get("date"))

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT * FROM apple_health_records WHERE user_id = ? AND date = ?",
            (uid, date_str),
        )
        existing_row = c.fetchone()
        existing = dict(existing_row) if existing_row else {}

        fields = [
            "hrv_sdnn",
            "resting_heart_rate",
            "sleep_duration_hours",
            "sleep_deep_hours",
            "sleep_rem_hours",
            "sleep_efficiency_pct",
            "weight_kg",
            "weight_lbs",
            "body_fat_pct",
            "vo2_max",
            "active_energy_kcal",
            "recovery_score",
        ]
        merged: Dict[str, Any] = {}
        for f in fields:
            val = record.get(f)
            merged[f] = val if val is not None else existing.get(f)

        # Auto-compute recovery_score if missing and we have at least one recovery signal
        if merged.get("recovery_score") is None and any(
            merged.get(k) is not None for k in ("hrv_sdnn", "resting_heart_rate", "sleep_duration_hours")
        ):
            merged["recovery_score"] = _compute_readiness_score(
                merged.get("hrv_sdnn"),
                merged.get("resting_heart_rate"),
                merged.get("sleep_duration_hours"),
                uid,
            )

        raw_str = json.dumps(raw_payload) if raw_payload is not None else existing.get("raw_json")

        c.execute(
            """
            INSERT INTO apple_health_records (
                user_id, date, source, hrv_sdnn, resting_heart_rate,
                sleep_duration_hours, sleep_deep_hours, sleep_rem_hours, sleep_efficiency_pct,
                weight_kg, weight_lbs, body_fat_pct, vo2_max, active_energy_kcal,
                recovery_score, raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, date) DO UPDATE SET
                source = excluded.source,
                hrv_sdnn = excluded.hrv_sdnn,
                resting_heart_rate = excluded.resting_heart_rate,
                sleep_duration_hours = excluded.sleep_duration_hours,
                sleep_deep_hours = excluded.sleep_deep_hours,
                sleep_rem_hours = excluded.sleep_rem_hours,
                sleep_efficiency_pct = excluded.sleep_efficiency_pct,
                weight_kg = excluded.weight_kg,
                weight_lbs = excluded.weight_lbs,
                body_fat_pct = excluded.body_fat_pct,
                vo2_max = excluded.vo2_max,
                active_energy_kcal = excluded.active_energy_kcal,
                recovery_score = excluded.recovery_score,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                uid,
                date_str,
                source,
                merged["hrv_sdnn"],
                merged["resting_heart_rate"],
                merged["sleep_duration_hours"],
                merged["sleep_deep_hours"],
                merged["sleep_rem_hours"],
                merged["sleep_efficiency_pct"],
                merged["weight_kg"],
                merged["weight_lbs"],
                merged["body_fat_pct"],
                merged["vo2_max"],
                merged["active_energy_kcal"],
                merged["recovery_score"],
                raw_str,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Sync athlete weight if this record has weight and is the most recent record
    if merged.get("weight_kg") is not None:
        latest = get_apple_health_summary(user_id=uid, limit=1).get("latest")
        if not latest or latest.get("date", "") <= date_str:
            set_athlete_weight_kg(float(merged["weight_kg"]), user_id=uid)

    return {"date": date_str, "source": source, **merged}


def ingest_apple_health_payload(
    payload: Any,
    user_id: Optional[str] = None,
    source: str = "webhook",
) -> Dict[str, Any]:
    """
    Ingests Health Auto Export JSON, Apple Shortcuts flat JSON, or a list of daily records.
    """
    uid = user_id or get_current_user_id()
    default_date = get_athlete_date().isoformat()
    normalized_days: List[Dict[str, Any]] = []

    if isinstance(payload, dict):
        data_block = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if isinstance(data_block.get("metrics"), list):
            by_date = _normalize_health_auto_export(payload, default_date)
            normalized_days = list(by_date.values())
        elif isinstance(payload.get("records"), list):
            for item in payload["records"]:
                if isinstance(item, dict):
                    normalized_days.append(_normalize_flat_record(item, default_date))
        else:
            normalized_days.append(_normalize_flat_record(payload, default_date))
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                normalized_days.append(_normalize_flat_record(item, default_date))

    saved_dates: List[str] = []
    for day_rec in sorted(normalized_days, key=lambda x: x.get("date", "")):
        # Skip completely empty records
        has_data = any(
            day_rec.get(k) is not None
            for k in (
                "hrv_sdnn",
                "resting_heart_rate",
                "sleep_duration_hours",
                "weight_kg",
                "weight_lbs",
                "body_fat_pct",
                "vo2_max",
                "active_energy_kcal",
                "recovery_score",
            )
        )
        if not has_data:
            continue
        res = upsert_apple_health_record(day_rec, user_id=uid, source=source, raw_payload=payload)
        saved_dates.append(res["date"])

    set_setting("last_apple_health_sync_timestamp", datetime.datetime.now().timestamp(), user_id=uid)
    summary = get_apple_health_summary(user_id=uid, limit=14)
    return {
        "success": True,
        "records_upserted": len(saved_dates),
        "dates": saved_dates,
        "latest": summary.get("latest"),
    }


def get_apple_health_summary(user_id: Optional[str] = None, limit: int = 14) -> Dict[str, Any]:
    """Returns connection status, latest Apple Health record, and recent history for a user."""
    uid = user_id or get_current_user_id()
    has_token = bool(get_setting("apple_health_webhook_token", "", user_id=uid))
    last_sync = get_setting("last_apple_health_sync_timestamp", None, user_id=uid)

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT date, source, hrv_sdnn, resting_heart_rate,
                   sleep_duration_hours, sleep_deep_hours, sleep_rem_hours, sleep_efficiency_pct,
                   weight_kg, weight_lbs, body_fat_pct, vo2_max, active_energy_kcal,
                   recovery_score, updated_at
            FROM apple_health_records
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (uid, limit),
        )
        rows = [dict(r) for r in c.fetchall()]
    finally:
        conn.close()

    latest = rows[0] if rows else None
    connected = bool(latest is not None or has_token)
    return {
        "connected": connected,
        "has_token": has_token,
        "has_records": bool(latest is not None),
        "last_sync": last_sync,
        "latest": latest,
        "history": rows,
    }


def get_latest_apple_health_as_recovery(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Formats the latest Apple Health record into PowerSync's recovery/readiness payload
    format when Whoop is not connected.
    """
    uid = user_id or get_current_user_id()
    summary = get_apple_health_summary(user_id=uid, limit=7)
    latest = summary.get("latest")
    if not latest:
        return None

    today_iso = get_athlete_date().isoformat()
    is_today = latest.get("date") == today_iso
    rec_score = int(latest.get("recovery_score") or 68)
    hrv = round(float(latest["hrv_sdnn"]), 1) if latest.get("hrv_sdnn") is not None else None
    rhr = int(latest["resting_heart_rate"]) if latest.get("resting_heart_rate") is not None else None
    sleep_h = round(float(latest["sleep_duration_hours"]), 1) if latest.get("sleep_duration_hours") is not None else 7.5
    sleep_eff = int(round(float(latest["sleep_efficiency_pct"]))) if latest.get("sleep_efficiency_pct") is not None else int(min(100, max(50, round((sleep_h / 8.0) * 100))))

    return {
        "source": "apple_health",
        "entry_source": latest.get("source", "webhook"),
        "date": latest.get("date"),
        "is_today": is_today,
        "auth_expired": False,
        "recovery_score": rec_score,
        "recovery_zone": "green" if rec_score > 66 else ("yellow" if rec_score >= 34 else "red"),
        "hrv_rmssd": hrv if hrv is not None else 45.0,
        "resting_heart_rate": rhr if rhr is not None else 58,
        "sleep_performance": sleep_eff,
        "sleep_duration_hours": sleep_h,
        "day_strain": 0.0,
        "trailing_7d_strain_avg": 0.0,
        "recent_weighted_strain": 0.0,
        "yesterday_strain": 0.0,
        "strain_profile": "Apple Health",
        "trailing_7d_high_strain_days": 0,
        "trailing_strains": [],
        "trends": {
            "hrv_vs_baseline": f"{hrv} ms" if hrv is not None else "--",
            "rhr_vs_baseline": f"{rhr} bpm" if rhr is not None else "--",
            "sleep_consistency": "Apple Health Today" if is_today else f"Apple Health ({latest.get('date')})",
        },
    }

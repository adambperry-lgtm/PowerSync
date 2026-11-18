import datetime
import json
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.database import (
    get_athlete_now,
    get_current_user_id,
    get_db_connection,
    get_setting,
    resolve_strava_local_start,
)
from app.services.power_profile_service import calculate_activity_peak_powers
from app.services.strain_model_service import (
    calculate_activity_strain,
    is_cycling_sport,
)


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        if val is None or val == "":
            return default
        return int(round(float(val)))
    except (TypeError, ValueError):
        return default


def _parse_raw_json(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("{"):
            try:
                return json.loads(s)
            except Exception:
                return {}
    return {}


def _is_indoor_ride(sport_type: str, raw: Dict[str, Any], name: str) -> bool:
    st = (sport_type or "").lower()
    if "virtual" in st or raw.get("trainer") is True:
        return True
    nm = (name or "").lower()
    if "zwift" in nm or "trainerroad" in nm or "rouvy" in nm:
        return True
    # No GPS polyline and trainer-like sport
    poly = ((raw.get("map") or {}).get("summary_polyline") or "").strip()
    if not poly and st in ("ride", "virtualride") and raw.get("start_latlng") in (None, [], ""):
        return True
    return False


def _compute_ride_tss(
    moving_sec: int,
    np_watts: float,
    avg_watts: float,
    ftp: float,
    suffer_score: float,
) -> float:
    """
    Coggan TSS = (t * NP * IF) / (FTP * 3600) * 100
    Falls back to HR suffer_score or duration estimate when power is absent.
    """
    if moving_sec <= 0:
        return 0.0
    power = np_watts if np_watts > 0 else avg_watts
    if power > 0 and ftp > 0:
        intensity = power / ftp
        tss = (moving_sec * power * intensity) / (ftp * 3600.0) * 100.0
        return round(min(tss, 650.0), 1)
    if suffer_score > 0:
        return round(min(suffer_score * 1.15, 500.0), 1)
    # Fallback: ~50 TSS/hr endurance estimate
    return round((moving_sec / 3600.0) * 50.0, 1)


def _date_range_bounds(
    range_key: str, today: datetime.date
) -> Tuple[Optional[datetime.date], Optional[datetime.date], Optional[datetime.date]]:
    """
    Returns (start_date, prev_start_date, prev_end_date) for the requested range.
    """
    rk = (range_key or "90d").lower().strip()
    if rk == "7d":
        start = today - datetime.timedelta(days=6)
        prev_end = start - datetime.timedelta(days=1)
        prev_start = prev_end - datetime.timedelta(days=6)
        return start, prev_start, prev_end
    if rk == "30d":
        start = today - datetime.timedelta(days=29)
        prev_end = start - datetime.timedelta(days=1)
        prev_start = prev_end - datetime.timedelta(days=29)
        return start, prev_start, prev_end
    if rk == "90d":
        start = today - datetime.timedelta(days=89)
        prev_end = start - datetime.timedelta(days=1)
        prev_start = prev_end - datetime.timedelta(days=89)
        return start, prev_start, prev_end
    if rk == "ytd":
        start = datetime.date(today.year, 1, 1)
        span_days = (today - start).days
        prev_start = datetime.date(today.year - 1, 1, 1)
        prev_end = prev_start + datetime.timedelta(days=span_days)
        return start, prev_start, prev_end
    if rk == "1y":
        start = today - datetime.timedelta(days=364)
        prev_end = start - datetime.timedelta(days=1)
        prev_start = prev_end - datetime.timedelta(days=364)
        return start, prev_start, prev_end
    # "all"
    return None, None, None


def _pct_delta(cur: float, prev: float) -> Optional[float]:
    if prev <= 0:
        return None
    return round(((cur - prev) / prev) * 100.0, 1)


def _load_normalized_rides_and_whoop(
    user_id: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], float, float]:
    """
    Loads all cycling rides from strava_activities and all whoop_metrics for user_id,
    enriched with local date, TSS, EF, 3-tier strain, and polyline.
    """
    ftp = _safe_float(get_setting("ftp", default=250, user_id=user_id), 250.0)
    if ftp <= 0:
        ftp = 250.0
    weight_kg = _safe_float(get_setting("weight_kg", default=75.0, user_id=user_id), 75.0)
    if weight_kg <= 0:
        weight_kg = 75.0

    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        """
        SELECT id, name, sport_type, start_date, elapsed_time_sec, moving_time_sec,
               distance_meters, total_elevation_gain, average_watts, weighted_average_watts,
               average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
        FROM strava_activities
        WHERE user_id = ?
        ORDER BY start_date DESC
        """,
        (user_id,),
    )
    act_rows = c.fetchall()

    c.execute(
        """
        SELECT date, recovery_score, hrv_rmssd, resting_heart_rate,
               sleep_performance, sleep_duration_hours, day_strain
        FROM whoop_metrics
        WHERE user_id = ?
        ORDER BY date ASC
        """,
        (user_id,),
    )
    whoop_rows = c.fetchall()
    conn.close()

    whoop_by_date: Dict[str, Dict[str, Any]] = {}
    for w in whoop_rows:
        wd = dict(w)
        d_str = str(wd.get("date") or "")[:10]
        if d_str:
            whoop_by_date[d_str] = wd

    rides: List[Dict[str, Any]] = []
    for r in act_rows:
        rd = dict(r)
        sport = str(rd.get("sport_type") or "")
        if not is_cycling_sport(sport):
            continue

        raw = _parse_raw_json(rd.get("raw_json"))
        local_iso = resolve_strava_local_start(rd, user_id=user_id)
        local_date = (local_iso or str(rd.get("start_date") or ""))[:10]
        if len(local_date) != 10:
            continue

        moving_sec = _safe_int(rd.get("moving_time_sec") or rd.get("elapsed_time_sec"))
        elapsed_sec = _safe_int(rd.get("elapsed_time_sec") or moving_sec)
        dist_m = _safe_float(rd.get("distance_meters"))
        elev_m = _safe_float(rd.get("total_elevation_gain"))
        avg_watts = _safe_float(rd.get("average_watts"))
        np_watts = _safe_float(rd.get("weighted_average_watts"))
        if np_watts <= 0 and avg_watts > 0:
            np_watts = avg_watts
        avg_hr = _safe_float(rd.get("average_heartrate"))
        max_hr = _safe_float(rd.get("max_heartrate"))
        suffer = _safe_float(rd.get("suffer_score"))
        kj = _safe_float(rd.get("kilojoules"))
        if kj <= 0 and avg_watts > 0 and moving_sec > 0:
            kj = round((avg_watts * moving_sec) / 1000.0, 1)

        tss = _compute_ride_tss(moving_sec, np_watts, avg_watts, ftp, suffer)
        ef = round(np_watts / avg_hr, 2) if (np_watts > 0 and avg_hr > 0) else None
        intensity_factor = round(np_watts / ftp, 2) if (np_watts > 0 and ftp > 0) else None

        polyline = ((raw.get("map") or {}).get("summary_polyline") or "").strip()
        is_indoor = _is_indoor_ride(sport, raw, str(rd.get("name") or ""))

        # 3-Tier Strain breakdown
        try:
            strain_input = dict(rd)
            if raw.get("max_watts") and not strain_input.get("max_watts"):
                strain_input["max_watts"] = raw.get("max_watts")
            strain = calculate_activity_strain(strain_input, ftp=int(round(ftp)))
            s_low = round(_safe_float(strain.get("low_xss")), 1)
            s_high = round(_safe_float(strain.get("high_xss")), 1)
            s_peak = round(_safe_float(strain.get("peak_xss")), 1)
        except Exception:
            s_low, s_high, s_peak = round(tss * 0.75, 1), round(tss * 0.2, 1), round(tss * 0.05, 1)

        # Peak power curve estimates for this activity
        try:
            peaks = calculate_activity_peak_powers(rd, ftp=int(round(ftp)))
        except Exception:
            peaks = {}

        whoop_day = whoop_by_date.get(local_date)
        whoop_rec = whoop_day.get("recovery_score") if whoop_day else None
        whoop_hrv = whoop_day.get("hrv_rmssd") if whoop_day else None
        whoop_rhr = whoop_day.get("resting_heart_rate") if whoop_day else None
        whoop_sleep = whoop_day.get("sleep_duration_hours") if whoop_day else None

        rides.append(
            {
                "id": str(rd.get("id")),
                "name": str(rd.get("name") or "Cycling Ride"),
                "sport_type": sport,
                "date": local_date,
                "local_start": local_iso,
                "is_indoor": is_indoor,
                "moving_time_sec": moving_sec,
                "elapsed_time_sec": elapsed_sec,
                "distance_km": round(dist_m / 1000.0, 2),
                "distance_mi": round(dist_m / 1609.344, 2),
                "elevation_m": round(elev_m, 1),
                "elevation_ft": round(elev_m * 3.28084, 0),
                "avg_watts": round(avg_watts, 0) if avg_watts > 0 else None,
                "np_watts": round(np_watts, 0) if np_watts > 0 else None,
                "max_watts": round(_safe_float(raw.get("max_watts")), 0) if _safe_float(raw.get("max_watts")) > 0 else None,
                "avg_hr": round(avg_hr, 0) if avg_hr > 0 else None,
                "max_hr": round(max_hr, 0) if max_hr > 0 else None,
                "kilojoules": round(kj, 0) if kj > 0 else 0,
                "tss": tss,
                "intensity_factor": intensity_factor,
                "ef": ef,
                "avg_speed_kmh": round((dist_m / moving_sec) * 3.6, 1) if (dist_m > 0 and moving_sec > 0) else None,
                "polyline": polyline,
                "has_polyline": bool(polyline),
                "strain_low": s_low,
                "strain_high": s_high,
                "strain_peak": s_peak,
                "peaks": peaks,
                "whoop_recovery": whoop_rec,
                "whoop_hrv": round(_safe_float(whoop_hrv), 1) if whoop_hrv is not None else None,
                "whoop_rhr": whoop_rhr,
                "whoop_sleep_hrs": round(_safe_float(whoop_sleep), 2) if whoop_sleep is not None else None,
            }
        )

    return rides, whoop_by_date, ftp, weight_kg


def _summarize_kpis(rides: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = len(rides)
    dist_km = sum(r["distance_km"] for r in rides)
    dist_mi = sum(r["distance_mi"] for r in rides)
    sec = sum(r["moving_time_sec"] for r in rides)
    elev_m = sum(r["elevation_m"] for r in rides)
    elev_ft = sum(r["elevation_ft"] for r in rides)
    kj = sum(r["kilojoules"] for r in rides)
    tss = sum(r["tss"] for r in rides)

    np_vals = [r["np_watts"] for r in rides if r["np_watts"]]
    ef_vals = [r["ef"] for r in rides if r["ef"]]
    hr_vals = [r["avg_hr"] for r in rides if r["avg_hr"]]

    return {
        "ride_count": count,
        "distance_km": round(dist_km, 1),
        "distance_mi": round(dist_mi, 1),
        "moving_hours": round(sec / 3600.0, 1),
        "elevation_m": round(elev_m, 0),
        "elevation_ft": round(elev_ft, 0),
        "kilojoules": round(kj, 0),
        "tss": round(tss, 0),
        "avg_np": round(sum(np_vals) / len(np_vals), 0) if np_vals else None,
        "avg_ef": round(sum(ef_vals) / len(ef_vals), 2) if ef_vals else None,
        "avg_hr": round(sum(hr_vals) / len(hr_vals), 0) if hr_vals else None,
    }


def _compute_pmc_series(
    all_rides: List[Dict[str, Any]],
    whoop_by_date: Dict[str, Dict[str, Any]],
    start_date: Optional[datetime.date],
    end_date: datetime.date,
) -> List[Dict[str, Any]]:
    """
    Computes daily CTL (42d), ATL (7d), TSB across full history so values are warmed up,
    then returns the slice [start_date .. end_date].
    """
    if not all_rides and not whoop_by_date:
        return []

    tss_by_day: Dict[datetime.date, float] = defaultdict(float)
    ride_count_by_day: Dict[datetime.date, int] = defaultdict(int)
    earliest = end_date - datetime.timedelta(days=90)

    for r in all_rides:
        try:
            d = datetime.date.fromisoformat(r["date"])
        except ValueError:
            continue
        if d > end_date:
            continue
        tss_by_day[d] += r["tss"]
        ride_count_by_day[d] += 1
        if d < earliest:
            earliest = d

    if start_date and start_date < earliest:
        earliest = start_date

    ctl = 0.0
    atl = 0.0
    k_ctl = 1.0 - math.exp(-1.0 / 42.0)
    k_atl = 1.0 - math.exp(-1.0 / 7.0)

    slice_start = start_date or earliest
    series: List[Dict[str, Any]] = []
    cur = earliest
    while cur <= end_date:
        tsb = ctl - atl
        day_tss = tss_by_day.get(cur, 0.0)
        ctl = ctl + (day_tss - ctl) * k_ctl
        atl = atl + (day_tss - atl) * k_atl

        if cur >= slice_start:
            d_str = cur.isoformat()
            w = whoop_by_date.get(d_str)
            series.append(
                {
                    "date": d_str,
                    "tss": round(day_tss, 1),
                    "rides": ride_count_by_day.get(cur, 0),
                    "ctl": round(ctl, 1),
                    "atl": round(atl, 1),
                    "tsb": round(tsb, 1),
                    "recovery": w.get("recovery_score") if w else None,
                    "hrv": round(_safe_float(w.get("hrv_rmssd")), 1) if (w and w.get("hrv_rmssd") is not None) else None,
                    "rhr": w.get("resting_heart_rate") if w else None,
                }
            )
        cur += datetime.timedelta(days=1)

    return series


def _compute_volume_buckets(
    rides: List[Dict[str, Any]], range_key: str
) -> List[Dict[str, Any]]:
    if not rides:
        return []
    use_monthly = (range_key or "").lower() in ("1y", "all")
    buckets: Dict[str, Dict[str, Any]] = {}

    for r in rides:
        try:
            d = datetime.date.fromisoformat(r["date"])
        except ValueError:
            continue
        if use_monthly:
            key = d.strftime("%Y-%m")
            label = d.strftime("%b '%y")
        else:
            # ISO week Monday
            monday = d - datetime.timedelta(days=d.weekday())
            key = monday.isoformat()
            label = monday.strftime("%b %-d")

        if key not in buckets:
            buckets[key] = {
                "key": key,
                "label": label,
                "hours_indoor": 0.0,
                "hours_outdoor": 0.0,
                "distance_km": 0.0,
                "elevation_m": 0.0,
                "tss": 0.0,
                "strain_low": 0.0,
                "strain_high": 0.0,
                "strain_peak": 0.0,
                "rides": 0,
            }
        b = buckets[key]
        hrs = r["moving_time_sec"] / 3600.0
        if r["is_indoor"]:
            b["hours_indoor"] += hrs
        else:
            b["hours_outdoor"] += hrs
        b["distance_km"] += r["distance_km"]
        b["elevation_m"] += r["elevation_m"]
        b["tss"] += r["tss"]
        b["strain_low"] += r["strain_low"]
        b["strain_high"] += r["strain_high"]
        b["strain_peak"] += r["strain_peak"]
        b["rides"] += 1

    ordered = [buckets[k] for k in sorted(buckets.keys())]
    for b in ordered:
        b["hours_indoor"] = round(b["hours_indoor"], 1)
        b["hours_outdoor"] = round(b["hours_outdoor"], 1)
        b["hours_total"] = round(b["hours_indoor"] + b["hours_outdoor"], 1)
        b["distance_km"] = round(b["distance_km"], 1)
        b["elevation_m"] = round(b["elevation_m"], 0)
        b["tss"] = round(b["tss"], 0)
        b["strain_low"] = round(b["strain_low"], 1)
        b["strain_high"] = round(b["strain_high"], 1)
        b["strain_peak"] = round(b["strain_peak"], 1)
    return ordered


def _compute_recovery_matrix(rides: List[Dict[str, Any]]) -> Dict[str, Any]:
    zones = {
        "green": {"label": "Green (67–100%)", "rides": []},
        "yellow": {"label": "Yellow (34–66%)", "rides": []},
        "red": {"label": "Red (0–33%)", "rides": []},
    }
    scatter: List[Dict[str, Any]] = []

    for r in rides:
        rec = r.get("whoop_recovery")
        if rec is None:
            continue
        rec_val = int(rec)
        if rec_val >= 67:
            z_key = "green"
        elif rec_val >= 34:
            z_key = "yellow"
        else:
            z_key = "red"
        zones[z_key]["rides"].append(r)

        if r.get("ef") is not None or r.get("np_watts") is not None:
            scatter.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "date": r["date"],
                    "recovery": rec_val,
                    "hrv": r.get("whoop_hrv"),
                    "ef": r.get("ef"),
                    "np_watts": r.get("np_watts"),
                    "tss": r["tss"],
                    "duration_min": round(r["moving_time_sec"] / 60.0),
                    "zone": z_key,
                }
            )

    summary = {}
    for k, v in zones.items():
        rlist = v["rides"]
        np_vals = [x["np_watts"] for x in rlist if x["np_watts"]]
        hr_vals = [x["avg_hr"] for x in rlist if x["avg_hr"]]
        ef_vals = [x["ef"] for x in rlist if x["ef"]]
        tss_vals = [x["tss"] for x in rlist]
        summary[k] = {
            "label": v["label"],
            "ride_count": len(rlist),
            "avg_np": round(sum(np_vals) / len(np_vals), 0) if np_vals else None,
            "avg_hr": round(sum(hr_vals) / len(hr_vals), 0) if hr_vals else None,
            "avg_ef": round(sum(ef_vals) / len(ef_vals), 2) if ef_vals else None,
            "avg_tss": round(sum(tss_vals) / len(tss_vals), 0) if tss_vals else None,
        }

    return {"buckets": summary, "scatter": scatter[:250]}


def _compute_power_curve_and_prs(
    range_rides: List[Dict[str, Any]],
    all_rides: List[Dict[str, Any]],
    weight_kg: float,
) -> Dict[str, Any]:
    durations = [
        ("5s", "5s Sprint"),
        ("15s", "15s Attack"),
        ("1m", "1m Anaerobic"),
        ("5m", "5m VO2max"),
        ("20m", "20m Threshold"),
        ("60m", "60m Endurance"),
    ]

    def _best_for_set(rset: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        best: Dict[str, Dict[str, Any]] = {}
        for key, _ in durations:
            best_w = 0
            best_ride = None
            for r in rset:
                w = _safe_int((r.get("peaks") or {}).get(key))
                if w > best_w:
                    best_w = w
                    best_ride = r
            best[key] = {
                "watts": best_w,
                "w_kg": round(best_w / weight_kg, 2) if (best_w > 0 and weight_kg > 0) else 0.0,
                "ride_id": best_ride["id"] if best_ride else None,
                "ride_name": best_ride["name"] if best_ride else None,
                "date": best_ride["date"] if best_ride else None,
            }
        return best

    range_best = _best_for_set(range_rides)
    all_best = _best_for_set(all_rides)

    curve = []
    for key, label in durations:
        curve.append(
            {
                "key": key,
                "label": label,
                "range_watts": range_best[key]["watts"],
                "range_w_kg": range_best[key]["w_kg"],
                "range_date": range_best[key]["date"],
                "all_time_watts": all_best[key]["watts"],
                "all_time_w_kg": all_best[key]["w_kg"],
                "all_time_date": all_best[key]["date"],
                "all_time_ride": all_best[key]["ride_name"],
            }
        )

    # Breakthroughs / Superlatives in selected range
    breakthroughs = []
    if range_rides:
        longest = max(range_rides, key=lambda x: x["distance_km"])
        if longest["distance_km"] > 0:
            breakthroughs.append(
                {
                    "badge": "Longest Ride",
                    "value": f"{longest['distance_km']} km ({longest['distance_mi']} mi)",
                    "ride_id": longest["id"],
                    "ride_name": longest["name"],
                    "date": longest["date"],
                }
            )
        biggest_climb = max(range_rides, key=lambda x: x["elevation_m"])
        if biggest_climb["elevation_m"] > 0:
            breakthroughs.append(
                {
                    "badge": "Biggest Climb",
                    "value": f"{int(biggest_climb['elevation_m'])} m ({int(biggest_climb['elevation_ft'])} ft)",
                    "ride_id": biggest_climb["id"],
                    "ride_name": biggest_climb["name"],
                    "date": biggest_climb["date"],
                }
            )
        highest_tss = max(range_rides, key=lambda x: x["tss"])
        if highest_tss["tss"] > 0:
            breakthroughs.append(
                {
                    "badge": "Peak Training Load",
                    "value": f"{int(round(highest_tss['tss']))} TSS",
                    "ride_id": highest_tss["id"],
                    "ride_name": highest_tss["name"],
                    "date": highest_tss["date"],
                }
            )
        np_rides = [x for x in range_rides if x["np_watts"]]
        if np_rides:
            best_np = max(np_rides, key=lambda x: x["np_watts"] or 0)
            breakthroughs.append(
                {
                    "badge": "Highest Avg/NP Power",
                    "value": f"{int(best_np['np_watts'])} W",
                    "ride_id": best_np["id"],
                    "ride_name": best_np["name"],
                    "date": best_np["date"],
                }
            )
        ef_rides = [x for x in range_rides if x["ef"]]
        if ef_rides:
            best_ef = max(ef_rides, key=lambda x: x["ef"] or 0)
            breakthroughs.append(
                {
                    "badge": "Best Aerobic Efficiency",
                    "value": f"{best_ef['ef']} EF",
                    "ride_id": best_ef["id"],
                    "ride_name": best_ef["name"],
                    "date": best_ef["date"],
                }
            )

    return {"curve": curve, "breakthroughs": breakthroughs}


def _compute_year_in_sport(rides: List[Dict[str, Any]], range_key: str) -> Dict[str, Any]:
    if not rides:
        return {"has_data": False}

    day_counts: Dict[str, int] = defaultdict(int)
    unique_dates = set()
    indoor_count = 0
    outdoor_count = 0
    total_kj = 0.0

    for r in rides:
        total_kj += r["kilojoules"]
        if r["is_indoor"]:
            indoor_count += 1
        else:
            outdoor_count += 1
        try:
            d = datetime.date.fromisoformat(r["date"])
            unique_dates.add(d)
            day_counts[d.strftime("%A")] += 1
        except ValueError:
            pass

    fav_day = max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else "Saturday"

    # Longest streak of consecutive riding days
    sorted_dates = sorted(unique_dates)
    longest_streak = 0
    cur_streak = 0
    prev_d = None
    for d in sorted_dates:
        if prev_d and (d - prev_d).days == 1:
            cur_streak += 1
        else:
            cur_streak = 1
        if cur_streak > longest_streak:
            longest_streak = cur_streak
        prev_d = d

    total_rides = len(rides)
    outdoor_pct = round((outdoor_count / total_rides) * 100) if total_rides else 0
    indoor_pct = 100 - outdoor_pct

    # Fun energy equivalents (~1 kJ ~= 1 kcal human metabolic cost at ~24% efficiency)
    pizza_slices = max(1, round(total_kj / 285.0)) if total_kj > 0 else 0
    everests = round(sum(r["elevation_m"] for r in rides) / 8849.0, 2)

    return {
        "has_data": True,
        "range_label": range_key.upper(),
        "favorite_day": fav_day,
        "favorite_day_count": day_counts.get(fav_day, 0),
        "longest_streak_days": longest_streak,
        "active_days": len(unique_dates),
        "outdoor_pct": outdoor_pct,
        "indoor_pct": indoor_pct,
        "pizza_slices": pizza_slices,
        "everests": everests,
    }


def get_ride_history_analytics(
    user_id: Optional[str] = None,
    range_key: str = "90d",
    env_filter: str = "all",
) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    if uid == "usr_guest":
        return {
            "success": True,
            "is_guest": True,
            "range": range_key,
            "env": env_filter,
            "kpis": {},
            "deltas": {},
            "volume_buckets": [],
            "heatmap_rides": [],
            "pmc_series": [],
            "recovery_matrix": {"buckets": {}, "scatter": []},
            "power_curve": {"curve": [], "breakthroughs": []},
            "year_in_sport": {"has_data": False},
            "rides": [],
        }

    all_rides, whoop_by_date, ftp, weight_kg = _load_normalized_rides_and_whoop(uid)

    env = (env_filter or "all").lower().strip()
    if env == "indoor":
        env_rides = [r for r in all_rides if r["is_indoor"]]
    elif env == "outdoor":
        env_rides = [r for r in all_rides if not r["is_indoor"]]
    else:
        env_rides = all_rides

    today = get_athlete_now(user_id=uid).date()
    start_date, prev_start, prev_end = _date_range_bounds(range_key, today)

    if start_date:
        filtered_rides = [
            r for r in env_rides if start_date.isoformat() <= r["date"] <= today.isoformat()
        ]
    else:
        filtered_rides = list(env_rides)

    if prev_start and prev_end:
        prev_rides = [
            r for r in env_rides if prev_start.isoformat() <= r["date"] <= prev_end.isoformat()
        ]
    else:
        prev_rides = []

    kpis = _summarize_kpis(filtered_rides)
    prev_kpis = _summarize_kpis(prev_rides) if prev_rides else None
    deltas: Dict[str, Optional[float]] = {}
    if prev_kpis:
        for key in ("ride_count", "distance_km", "moving_hours", "elevation_m", "kilojoules", "tss"):
            deltas[key] = _pct_delta(
                _safe_float(kpis.get(key)), _safe_float(prev_kpis.get(key))
            )

    volume_buckets = _compute_volume_buckets(filtered_rides, range_key)

    heatmap_rides = [
        {
            "id": r["id"],
            "name": r["name"],
            "date": r["date"],
            "distance_km": r["distance_km"],
            "elevation_m": r["elevation_m"],
            "tss": r["tss"],
            "avg_watts": r["avg_watts"],
            "polyline": r["polyline"],
        }
        for r in filtered_rides
        if r["has_polyline"] and not r["is_indoor"]
    ]

    pmc_series = _compute_pmc_series(env_rides, whoop_by_date, start_date, today)
    recovery_matrix = _compute_recovery_matrix(filtered_rides)
    power_curve = _compute_power_curve_and_prs(filtered_rides, all_rides, weight_kg)
    year_in_sport = _compute_year_in_sport(filtered_rides, range_key)

    # Strip heavy polyline & peaks dicts from table rows to keep payload crisp
    ride_rows = [
        {k: v for k, v in r.items() if k not in ("polyline", "peaks")}
        for r in filtered_rides
    ]

    return {
        "success": True,
        "is_guest": False,
        "range": range_key,
        "env": env,
        "ftp": round(ftp),
        "weight_kg": round(weight_kg, 1),
        "kpis": kpis,
        "deltas": deltas,
        "volume_buckets": volume_buckets,
        "heatmap_rides": heatmap_rides,
        "pmc_series": pmc_series,
        "recovery_matrix": recovery_matrix,
        "power_curve": power_curve,
        "year_in_sport": year_in_sport,
        "rides": ride_rows,
    }


def get_single_ride_detail(
    ride_id: str, user_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    uid = user_id or get_current_user_id()
    if uid == "usr_guest":
        return None
    all_rides, _, ftp, weight_kg = _load_normalized_rides_and_whoop(uid)
    target = next((r for r in all_rides if r["id"] == str(ride_id)), None)
    if not target:
        return None

    # Find up to 3 similar rides by duration (+/- 25%) and environment
    dur = target["moving_time_sec"]
    similar = [
        {
            "id": r["id"],
            "name": r["name"],
            "date": r["date"],
            "np_watts": r["np_watts"],
            "avg_hr": r["avg_hr"],
            "ef": r["ef"],
            "tss": r["tss"],
            "distance_km": r["distance_km"],
        }
        for r in all_rides
        if r["id"] != target["id"]
        and r["is_indoor"] == target["is_indoor"]
        and dur > 0
        and abs(r["moving_time_sec"] - dur) <= dur * 0.25
    ][:4]

    return {
        "success": True,
        "ride": target,
        "ftp": round(ftp),
        "weight_kg": round(weight_kg, 1),
        "similar_rides": similar,
    }

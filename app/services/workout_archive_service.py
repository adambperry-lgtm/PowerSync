import copy
import datetime
import json
import math
import uuid
from typing import Any, Dict, List, Optional

from app.database import get_athlete_date, get_current_user_id, get_db_connection
from app.services.ai_coach import enrich_workout_strain
from app.services.workout_catalog import ZONE_ARCHETYPES
from app.services.zwift_service import (
    calc_intervals_duration_sec,
    generate_intervals_icu_text,
    generate_zwo_xml,
    reconcile_workout_intervals,
)

ZONE_LABELS = {
    "sweet_spot": "Sweet Spot",
    "tempo": "Tempo",
    "vo2_max": "VO2 Max",
    "endurance_base": "Endurance Base",
    "express": "Express (Time-Crunched)",
}


def calculate_workout_metrics(intervals: List[Dict[str, Any]], ftp: int = 250) -> Dict[str, Any]:
    """
    Computes Coggan Normalized Power (NP), Intensity Factor (IF), and TSS
    alongside exact total duration from structured workout intervals.
    TSS = (t * NP * IF) / (FTP * 3600) * 100
    """
    ftp = max(50, int(ftp or 250))
    if not intervals:
        return {
            "total_duration_sec": 0,
            "duration_minutes": 0,
            "normalized_power_watts": 0,
            "intensity_factor": 0.0,
            "estimated_tss": 0,
        }

    power_samples: List[float] = []
    for item in intervals:
        seg_type = str(item.get("type", "SteadyState")).lower()
        if seg_type in ("repeats", "intervalblock", "intervals"):
            repeat = max(1, int(item.get("repeat", 1)))
            on_dur = max(0, int(item.get("on_duration_sec", 0)))
            off_dur = max(0, int(item.get("off_duration_sec", 0)))
            on_w = ftp * (float(item.get("on_power_pct", 95)) / 100.0)
            off_w = ftp * (float(item.get("off_power_pct", 55)) / 100.0)
            for _ in range(repeat):
                if on_dur > 0:
                    power_samples.extend([on_w] * on_dur)
                if off_dur > 0:
                    power_samples.extend([off_w] * off_dur)
        elif seg_type in ("warmup", "cooldown", "ramp"):
            dur = max(0, int(item.get("duration_sec", 0)))
            p_low = ftp * (float(item.get("power_low_pct", 50)) / 100.0)
            p_high = ftp * (float(item.get("power_high_pct", 75)) / 100.0)
            if dur > 0:
                if dur == 1:
                    power_samples.append((p_low + p_high) / 2.0)
                else:
                    for s in range(dur):
                        frac = s / float(dur - 1)
                        power_samples.append(p_low + (p_high - p_low) * frac)
        else:
            dur = max(0, int(item.get("duration_sec", 0)))
            p_w = ftp * (float(item.get("power_pct", 65)) / 100.0)
            if dur > 0:
                power_samples.extend([p_w] * dur)

    total_sec = len(power_samples)
    if total_sec == 0:
        return {
            "total_duration_sec": 0,
            "duration_minutes": 0,
            "normalized_power_watts": 0,
            "intensity_factor": 0.0,
            "estimated_tss": 0,
        }

    # 30-second rolling average for Coggan NP (falls back to direct average if < 30s)
    if total_sec >= 30:
        window_sum = sum(power_samples[:30])
        rolling_fourth = [(window_sum / 30.0) ** 4]
        for idx in range(30, total_sec):
            window_sum += power_samples[idx] - power_samples[idx - 30]
            rolling_fourth.append((window_sum / 30.0) ** 4)
        np_watts = (sum(rolling_fourth) / len(rolling_fourth)) ** 0.25
    else:
        np_watts = (sum(p ** 4 for p in power_samples) / total_sec) ** 0.25

    if_val = np_watts / float(ftp)
    tss_val = ((total_sec * np_watts * if_val) / (float(ftp) * 3600.0)) * 100.0

    return {
        "total_duration_sec": total_sec,
        "duration_minutes": max(1, round(total_sec / 60.0)),
        "normalized_power_watts": round(np_watts),
        "intensity_factor": round(if_val, 2),
        "estimated_tss": max(1, round(tss_val)),
    }


def hydrate_workout_payload(
    workout: Dict[str, Any],
    ftp: int = 250,
    reconcile_duration: bool = False,
) -> Dict[str, Any]:
    """
    Ensures a workout dictionary has up-to-date Coggan metrics (NP, IF, TSS),
    3-tier XSS strain, .zwo XML, and Intervals.icu text.
    """
    w = copy.deepcopy(workout)
    ftp = max(50, int(ftp or 250))
    intervals = w.get("intervals") or []

    if reconcile_duration and w.get("duration_minutes") and intervals:
        intervals = reconcile_workout_intervals(intervals, int(w["duration_minutes"]), ftp)
        w["intervals"] = intervals

    metrics = calculate_workout_metrics(intervals, ftp=ftp)
    if metrics["total_duration_sec"] > 0:
        w["duration_minutes"] = metrics["duration_minutes"]
        w["normalized_power_watts"] = metrics["normalized_power_watts"]
        w["intensity_factor"] = metrics["intensity_factor"]
        w["estimated_tss"] = metrics["estimated_tss"]
    else:
        w.setdefault("normalized_power_watts", 0)
        w.setdefault("intensity_factor", 0.0)
        w.setdefault("estimated_tss", int(w.get("estimated_tss") or 0))

    if intervals:
        w["zwo_content"] = generate_zwo_xml(copy.deepcopy(w), ftp)
        w["intervals_icu_text"] = generate_intervals_icu_text(copy.deepcopy(w), ftp=ftp)
    else:
        w.setdefault("zwo_content", "")
        w.setdefault("intervals_icu_text", "")

    enrich_workout_strain(w, ftp=ftp)
    return w


def adjust_workout_structure(
    workout: Dict[str, Any],
    target_duration_min: Optional[int] = None,
    intensity_adjust_pct: int = 0,
    ftp: int = 250,
) -> Dict[str, Any]:
    """
    Creates a customized copy of a workout with scaled intensity (%) and/or
    reconciled target duration, recalculating all physiological metrics.
    """
    w = copy.deepcopy(workout)
    intervals = copy.deepcopy(w.get("intervals") or [])

    if intensity_adjust_pct and intensity_adjust_pct != 0:
        multiplier = 1.0 + (float(intensity_adjust_pct) / 100.0)
        for interval in intervals:
            if "power_pct" in interval:
                interval["power_pct"] = max(35, min(220, round(float(interval["power_pct"]) * multiplier)))
            if "on_power_pct" in interval:
                interval["on_power_pct"] = max(40, min(250, round(float(interval["on_power_pct"]) * multiplier)))
            if "off_power_pct" in interval:
                interval["off_power_pct"] = max(35, min(150, round(float(interval["off_power_pct"]) * multiplier)))
            if "power_low_pct" in interval:
                interval["power_low_pct"] = max(35, min(150, round(float(interval["power_low_pct"]) * multiplier)))
            if "power_high_pct" in interval:
                interval["power_high_pct"] = max(40, min(200, round(float(interval["power_high_pct"]) * multiplier)))

        rationale = w.get("ai_rationale") or ""
        tag = f"[Intensity scaled {intensity_adjust_pct:+d}%]"
        if tag not in rationale:
            w["ai_rationale"] = f"{rationale} {tag}".strip()

    if target_duration_min is not None and int(target_duration_min) > 0 and intervals:
        target_dur = max(15, min(300, int(target_duration_min)))
        intervals = reconcile_workout_intervals(intervals, target_dur, ftp)
        w["duration_minutes"] = target_dur

    w["intervals"] = intervals
    return hydrate_workout_payload(w, ftp=ftp, reconcile_duration=False)


def get_workout_library(
    ftp: int = 250,
    duration_min: int = 60,
    zone_filter: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Instantiates all structured workout archetypes from the Coach Catalog
    so athletes can browse, preview, customize, or push any template to Zwift.
    """
    dur = max(20, min(240, int(duration_min or 60)))
    q = (query or "").strip().lower()
    zf = (zone_filter or "").strip().lower()
    if zf in ("", "all", "archive"):
        zf = ""

    library: List[Dict[str, Any]] = []
    for zone_key, builders in ZONE_ARCHETYPES.items():
        if zf and zone_key != zf:
            continue
        zone_dur = 35 if (zone_key == "express" and duration_min == 60) else dur
        for builder in builders:
            raw = builder(zone_dur, ftp, None)
            arch_id = raw.get("archetype_id", "template")
            raw["id"] = f"lib_{arch_id}"
            raw["source"] = "library"
            raw["zone"] = zone_key
            raw["zone_label"] = ZONE_LABELS.get(zone_key, zone_key.replace("_", " ").title())
            raw["description"] = raw.get("ai_rationale", "")
            raw.setdefault("duration_minutes", zone_dur)
            hydrated = hydrate_workout_payload(raw, ftp=ftp, reconcile_duration=True)
            hydrated["source"] = "library"
            hydrated["zone"] = zone_key
            hydrated["zone_label"] = raw["zone_label"]

            if q:
                haystack = " ".join([
                    str(hydrated.get("title", "")),
                    str(hydrated.get("focus_area", "")),
                    str(hydrated.get("zone_label", "")),
                    str(hydrated.get("ai_rationale", "")),
                    str(hydrated.get("archetype_id", "")),
                ]).lower()
                if q not in haystack:
                    continue

            library.append(hydrated)

    return library


def get_archived_workouts(
    user_id: Optional[str] = None,
    ftp: int = 250,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves all prior, scheduled, prescribed, and custom archived workouts
    for the current user from SQLite.
    """
    uid = user_id or get_current_user_id()
    q = (query or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM workouts
        WHERE user_id = ?
        ORDER BY date DESC, created_at DESC
        """,
        (uid,),
    )
    rows = cursor.fetchall()
    conn.close()

    results: List[Dict[str, Any]] = []
    for r in rows:
        w = dict(r)
        try:
            w["intervals"] = json.loads(w.get("intervals_json") or "[]")
        except Exception:
            w["intervals"] = []
        w.pop("intervals_json", None)

        if q:
            haystack = " ".join([
                str(w.get("title", "")),
                str(w.get("focus_area", "")),
                str(w.get("description", "")),
                str(w.get("ai_rationale", "")),
                str(w.get("date", "")),
            ]).lower()
            if q not in haystack:
                continue

        hydrated = hydrate_workout_payload(w, ftp=ftp, reconcile_duration=False)
        hydrated["source"] = "archive"
        hydrated["status"] = w.get("status") or "archived"
        hydrated["date"] = w.get("date") or ""
        results.append(hydrated)

    return results


def save_custom_workout(
    workout_data: Dict[str, Any],
    user_id: Optional[str] = None,
    ftp: int = 250,
) -> Dict[str, Any]:
    """
    Saves or updates a customized/archived workout in SQLite for the active user.
    """
    uid = user_id or get_current_user_id()
    raw_id = str(workout_data.get("id") or "").strip()
    # If cloning from a library template, transient daily ID, or empty, mint a persistent custom ID
    if (
        not raw_id
        or raw_id.startswith("lib_")
        or raw_id.startswith("workout_primary")
        or raw_id.startswith("workout_alt")
    ):
        w_id = f"custom_{uuid.uuid4().hex[:10]}"
    else:
        w_id = raw_id

    date_str = str(workout_data.get("date") or get_athlete_date(uid).isoformat())[:10]
    hydrated = hydrate_workout_payload(workout_data, ftp=ftp, reconcile_duration=False)
    hydrated["id"] = w_id
    hydrated["date"] = date_str
    hydrated["status"] = workout_data.get("status") or "archived"
    hydrated["source"] = "archive"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO workouts (
            user_id, id, date, title, description, focus_area, duration_minutes,
            estimated_tss, intervals_json, zwo_content, intervals_icu_text,
            ai_rationale, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, id) DO UPDATE SET
            date = excluded.date,
            title = excluded.title,
            description = excluded.description,
            focus_area = excluded.focus_area,
            duration_minutes = excluded.duration_minutes,
            estimated_tss = excluded.estimated_tss,
            intervals_json = excluded.intervals_json,
            zwo_content = excluded.zwo_content,
            intervals_icu_text = excluded.intervals_icu_text,
            ai_rationale = excluded.ai_rationale,
            status = excluded.status
        """,
        (
            uid,
            w_id,
            date_str,
            hydrated.get("title") or "Custom Workout",
            hydrated.get("description") or hydrated.get("ai_rationale") or "",
            hydrated.get("focus_area") or "Custom",
            int(hydrated["duration_minutes"]) if hydrated.get("duration_minutes") is not None else 45,
            int(hydrated["estimated_tss"]) if hydrated.get("estimated_tss") is not None else 40,
            json.dumps(hydrated.get("intervals") or []),
            hydrated.get("zwo_content") or "",
            hydrated.get("intervals_icu_text") or "",
            hydrated.get("ai_rationale") or "",
            hydrated["status"],
        ),
    )
    conn.commit()
    conn.close()
    return hydrated


def delete_archived_workout(workout_id: str, user_id: Optional[str] = None) -> bool:
    """Deletes a workout from the user's archive in SQLite."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workouts WHERE user_id = ? AND id = ?", (uid, workout_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def resolve_workout_by_identifier(
    workout_id: Optional[str] = None,
    archetype_id: Optional[str] = None,
    query: Optional[str] = None,
    duration_min: int = 60,
    ftp: int = 250,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolves a workout from either the user's Archive or the Coach Library
    by exact ID, archetype_id, or fuzzy title match.
    """
    uid = user_id or get_current_user_id()
    archived = get_archived_workouts(user_id=uid, ftp=ftp)

    if workout_id:
        for w in archived:
            if w.get("id") == workout_id:
                return w
        if workout_id.startswith("lib_"):
            archetype_id = workout_id[4:]

    library = get_workout_library(ftp=ftp, duration_min=duration_min)
    if archetype_id:
        for w in library:
            if w.get("archetype_id") == archetype_id or w.get("id") == f"lib_{archetype_id}":
                return w

    if query:
        q = query.strip().lower()
        for w in archived:
            if q in str(w.get("title", "")).lower():
                return w
        for w in library:
            if q in str(w.get("title", "")).lower() or q in str(w.get("archetype_id", "")).lower():
                return w

    return None


def _build_outdoor_route_cache_row(d: Dict[str, Any], ftp: int) -> Optional[Dict[str, Any]]:
    import ast
    from app.services.outdoor_coach import decode_polyline, generate_svg_path
    from app.services.ride_history_service import _is_indoor_ride
    from app.services.strain_model_service import is_cycling_sport

    sport = str(d.get("sport_type") or "Ride")
    if not is_cycling_sport(sport):
        return None

    title = d.get("name") or "Outdoor Ride"
    raw = d.get("raw_json")
    raw_d: Dict[str, Any] = {}
    if raw:
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            try:
                parsed = ast.literal_eval(raw)
            except Exception:
                parsed = None
        if isinstance(parsed, dict):
            raw_d = parsed

    if _is_indoor_ride(sport, raw_d, title):
        return None

    dur_sec = int(d.get("moving_time_sec") or d.get("elapsed_time_sec") or 0)
    if dur_sec < 600:
        return None
    dur_min = max(1, round(dur_sec / 60.0))
    dist_m = float(d.get("distance_meters") or 0.0)
    dist_km = round(dist_m / 1000.0, 1)
    dist_mi = round(dist_m * 0.000621371, 1)
    elev_m = round(float(d.get("total_elevation_gain") or 0.0))
    elev_ft = round(elev_m * 3.28084)

    poly = ((raw_d.get("map") or {}).get("summary_polyline") or "").strip()
    pts = decode_polyline(poly)
    thumb_svg, _, _ = generate_svg_path(pts, 140, 64, padding=6) if pts else ("", None, None)

    is_loop = False
    orientation_label = "Outdoor Route"
    if pts and len(pts) >= 2:
        d_se = math.sqrt(((pts[0][0] - pts[-1][0]) * 111.0) ** 2 + ((pts[0][1] - pts[-1][1]) * 85.0) ** 2)
        if d_se < 0.8:
            is_loop = True
            orientation_label = "Loop Route"
        elif d_se < 2.0:
            orientation_label = "Out-and-Back"
        else:
            orientation_label = "Point-to-Point"

    avg_w = round(float(d.get("average_watts") or 0))
    np_w = round(float(d.get("weighted_average_watts") or avg_w or 0))
    if np_w > 0 and dur_sec > 0:
        if_val = round(np_w / float(ftp), 2)
        est_tss = max(1, round(((dur_sec * np_w * if_val) / (float(ftp) * 3600.0)) * 100.0))
    else:
        if_val = 0.0
        est_tss = round(float(d.get("suffer_score") or 0))

    climbing_ft_per_mi = round(elev_ft / max(0.5, dist_mi), 1) if dist_mi > 0 else 0.0
    if climbing_ft_per_mi < 30.0:
        terrain_type = "flat"
    elif climbing_ft_per_mi <= 65.0:
        terrain_type = "rolling"
    else:
        terrain_type = "hilly"

    ride_id = str(d.get("id") or "")
    start_date = str(d.get("start_date") or "")
    date_str = start_date[:10]
    return {
        "id": ride_id,
        "title": title,
        "sport_type": sport,
        "start_date": start_date,
        "date_str": date_str,
        "duration_minutes": dur_min,
        "moving_time_formatted": f"{dur_min // 60}h {dur_min % 60}m" if dur_min >= 60 else f"{dur_min}m",
        "distance_miles": dist_mi,
        "distance_km": dist_km,
        "elevation_gain_ft": elev_ft,
        "elevation_gain_m": elev_m,
        "climbing_ft_per_mile": climbing_ft_per_mi,
        "terrain_type": terrain_type,
        "average_watts": avg_w,
        "normalized_power_watts": np_w,
        "intensity_factor": if_val,
        "estimated_tss": est_tss,
        "has_gps": 1 if len(pts) >= 2 else 0,
        "thumbnail_svg": thumb_svg,
        "is_loop": 1 if is_loop else 0,
        "orientation_label": orientation_label,
        "strava_url": f"https://www.strava.com/activities/{ride_id}",
    }


def sync_outdoor_routes_cache(
    user_id: Optional[str] = None,
    ftp: int = 250,
    fetch_remote_if_needed: bool = True,
) -> int:
    """
    Incrementally syncs new outdoor rides from `strava_activities` into the
    persistent `outdoor_routes_cache` table in SQLite. Only parses/computes
    SVGs for newly added rides, making archive loads near-instant.
    Returns count of newly cached routes.
    """
    from app.database import get_setting

    uid = user_id or get_current_user_id()
    if uid == "usr_guest":
        return 0
    ftp = max(50, int(ftp or 250))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM outdoor_routes_cache WHERE user_id = ?", (uid,))
    cached_ids = {str(r[0]) for r in cursor.fetchall()}

    cursor.execute(
        """
        SELECT id FROM strava_activities
        WHERE user_id = ? AND COALESCE(moving_time_sec, elapsed_time_sec, 0) >= 600
        """,
        (uid,),
    )
    strava_ids = {str(r[0]) for r in cursor.fetchall()}

    # If strava_activities is empty or has no outdoor routes yet and Strava is connected, fetch once
    if fetch_remote_if_needed and not cached_ids and not strava_ids and get_setting("strava_tokens", None, user_id=uid):
        conn.close()
        try:
            from app.services.strava_service import fetch_recent_strava_activities, trigger_strava_full_backfill_async
            fetch_recent_strava_activities(limit=200, user_id=uid)
            trigger_strava_full_backfill_async(user_id=uid)
        except Exception:
            pass
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM strava_activities
            WHERE user_id = ? AND COALESCE(moving_time_sec, elapsed_time_sec, 0) >= 600
            """,
            (uid,),
        )
        strava_ids = {str(r[0]) for r in cursor.fetchall()}

    # Remove deleted rides from cache if any
    stale_ids = cached_ids - strava_ids
    if stale_ids:
        placeholders = ",".join("?" for _ in stale_ids)
        cursor.execute(
            f"DELETE FROM outdoor_routes_cache WHERE user_id = ? AND id IN ({placeholders})",
            (uid, *stale_ids),
        )

    missing_ids = strava_ids - cached_ids
    inserted = 0
    if missing_ids:
        placeholders = ",".join("?" for _ in missing_ids)
        cursor.execute(
            f"""
            SELECT id, name, sport_type, start_date, moving_time_sec, elapsed_time_sec, distance_meters,
                   total_elevation_gain, average_watts, weighted_average_watts,
                   average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
            FROM strava_activities
            WHERE user_id = ? AND id IN ({placeholders})
            """,
            (uid, *missing_ids),
        )
        new_rows = cursor.fetchall()
        for r in new_rows:
            item = _build_outdoor_route_cache_row(dict(r), ftp=ftp)
            if not item:
                continue
            cursor.execute(
                """
                INSERT INTO outdoor_routes_cache (
                    user_id, id, title, sport_type, start_date, date_str, duration_minutes,
                    moving_time_formatted, distance_miles, distance_km, elevation_gain_ft,
                    elevation_gain_m, climbing_ft_per_mile, terrain_type, average_watts,
                    normalized_power_watts, intensity_factor, estimated_tss, has_gps,
                    thumbnail_svg, is_loop, orientation_label, strava_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, id) DO UPDATE SET
                    title = excluded.title,
                    sport_type = excluded.sport_type,
                    start_date = excluded.start_date,
                    date_str = excluded.date_str,
                    duration_minutes = excluded.duration_minutes,
                    moving_time_formatted = excluded.moving_time_formatted,
                    distance_miles = excluded.distance_miles,
                    distance_km = excluded.distance_km,
                    elevation_gain_ft = excluded.elevation_gain_ft,
                    elevation_gain_m = excluded.elevation_gain_m,
                    climbing_ft_per_mile = excluded.climbing_ft_per_mile,
                    terrain_type = excluded.terrain_type,
                    average_watts = excluded.average_watts,
                    normalized_power_watts = excluded.normalized_power_watts,
                    intensity_factor = excluded.intensity_factor,
                    estimated_tss = excluded.estimated_tss,
                    has_gps = excluded.has_gps,
                    thumbnail_svg = excluded.thumbnail_svg,
                    is_loop = excluded.is_loop,
                    orientation_label = excluded.orientation_label,
                    strava_url = excluded.strava_url
                """,
                (
                    uid,
                    item["id"],
                    item["title"],
                    item["sport_type"],
                    item["start_date"],
                    item["date_str"],
                    item["duration_minutes"],
                    item["moving_time_formatted"],
                    item["distance_miles"],
                    item["distance_km"],
                    item["elevation_gain_ft"],
                    item["elevation_gain_m"],
                    item["climbing_ft_per_mile"],
                    item["terrain_type"],
                    item["average_watts"],
                    item["normalized_power_watts"],
                    item["intensity_factor"],
                    item["estimated_tss"],
                    item["has_gps"],
                    item["thumbnail_svg"],
                    item["is_loop"],
                    item["orientation_label"],
                    item["strava_url"],
                ),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted


def get_archived_outdoor_routes(
    user_id: Optional[str] = None,
    ftp: int = 250,
    query: Optional[str] = None,
    min_duration_min: Optional[int] = None,
    max_duration_min: Optional[int] = None,
    min_distance_mi: Optional[float] = None,
    max_distance_mi: Optional[float] = None,
    terrain: Optional[str] = None,
    sort_by: str = "recent",
) -> List[Dict[str, Any]]:
    """
    Retrieves precomputed outdoor routes from `outdoor_routes_cache` in SQLite
    (incrementally syncing any new `strava_activities` first). Omits heavy GPS
    `map_points` so the full route list loads instantaneously.
    """
    from app.services.outdoor_coach import format_relative_date

    uid = user_id or get_current_user_id()
    if uid == "usr_guest":
        return []

    ftp = max(50, int(ftp or 250))
    sync_outdoor_routes_cache(user_id=uid, ftp=ftp)

    sql = ["SELECT * FROM outdoor_routes_cache WHERE user_id = ?"]
    params: List[Any] = [uid]

    if min_duration_min is not None:
        sql.append("AND duration_minutes >= ?")
        params.append(int(min_duration_min))
    if max_duration_min is not None:
        sql.append("AND duration_minutes <= ?")
        params.append(int(max_duration_min))
    if min_distance_mi is not None:
        sql.append("AND distance_miles >= ?")
        params.append(float(min_distance_mi))
    if max_distance_mi is not None:
        sql.append("AND distance_miles <= ?")
        params.append(float(max_distance_mi))

    terrain_filter = (terrain or "").strip().lower()
    if terrain_filter and terrain_filter != "all":
        sql.append("AND terrain_type = ?")
        params.append(terrain_filter)

    q = (query or "").strip().lower()
    if q:
        sql.append("AND (LOWER(title) LIKE ? OR LOWER(sport_type) LIKE ? OR date_str LIKE ?)")
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q])

    order_map = {
        "duration_desc": "duration_minutes DESC, start_date DESC",
        "duration_asc": "duration_minutes ASC, start_date DESC",
        "distance_desc": "distance_miles DESC, start_date DESC",
        "distance_asc": "distance_miles ASC, start_date DESC",
        "elevation_desc": "elevation_gain_ft DESC, start_date DESC",
    }
    sql.append(f"ORDER BY {order_map.get(sort_by, 'start_date DESC')}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(" ".join(sql), tuple(params))
    rows = cursor.fetchall()
    conn.close()

    results: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        results.append({
            "id": d["id"],
            "source": "outdoor",
            "title": d["title"],
            "sport_type": d["sport_type"],
            "date": d["date_str"],
            "date_relative": format_relative_date(d["start_date"]),
            "duration_minutes": d["duration_minutes"],
            "moving_time_formatted": d["moving_time_formatted"],
            "distance_miles": d["distance_miles"],
            "distance_km": d["distance_km"],
            "elevation_gain_ft": d["elevation_gain_ft"],
            "elevation_gain_m": d["elevation_gain_m"],
            "climbing_ft_per_mile": d["climbing_ft_per_mile"],
            "terrain_type": d["terrain_type"],
            "average_watts": d["average_watts"],
            "normalized_power_watts": d["normalized_power_watts"],
            "intensity_factor": d["intensity_factor"],
            "estimated_tss": d["estimated_tss"],
            "has_gps": bool(d["has_gps"]),
            "thumbnail_svg": d["thumbnail_svg"] or "",
            "is_loop": bool(d["is_loop"]),
            "orientation_label": d["orientation_label"] or "Outdoor Route",
            "strava_url": d["strava_url"] or f"https://www.strava.com/activities/{d['id']}",
        })
    return results


def get_single_outdoor_route_detail(
    ride_id: str,
    user_id: Optional[str] = None,
    ftp: int = 250,
) -> Optional[Dict[str, Any]]:
    """
    Loads full GPS `map_points` and large SVG fallback for a single outdoor route
    on demand when the user opens the Route Inspector modal.
    """
    import ast
    from app.services.outdoor_coach import decode_polyline, format_relative_date, generate_svg_path, sample_coordinates

    uid = user_id or get_current_user_id()
    if uid == "usr_guest":
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM outdoor_routes_cache WHERE user_id = ? AND id = ?",
        (uid, str(ride_id)),
    )
    cached_row = cursor.fetchone()
    cursor.execute(
        "SELECT raw_json FROM strava_activities WHERE user_id = ? AND id = ?",
        (uid, str(ride_id)),
    )
    act_row = cursor.fetchone()
    conn.close()

    if not cached_row and not act_row:
        return None

    poly = ""
    if act_row and act_row["raw_json"]:
        raw = act_row["raw_json"]
        raw_d = None
        try:
            raw_d = json.loads(raw)
        except Exception:
            try:
                raw_d = ast.literal_eval(raw)
            except Exception:
                raw_d = None
        if isinstance(raw_d, dict):
            poly = ((raw_d.get("map") or {}).get("summary_polyline") or "").strip()

    pts = decode_polyline(poly)
    svg_path, start_xy, end_xy = generate_svg_path(pts, 380, 160, padding=14) if pts else ("", None, None)

    if cached_row:
        d = dict(cached_row)
        out = {
            "id": d["id"],
            "source": "outdoor",
            "title": d["title"],
            "sport_type": d["sport_type"],
            "date": d["date_str"],
            "date_relative": format_relative_date(d["start_date"]),
            "duration_minutes": d["duration_minutes"],
            "moving_time_formatted": d["moving_time_formatted"],
            "distance_miles": d["distance_miles"],
            "distance_km": d["distance_km"],
            "elevation_gain_ft": d["elevation_gain_ft"],
            "elevation_gain_m": d["elevation_gain_m"],
            "climbing_ft_per_mile": d["climbing_ft_per_mile"],
            "terrain_type": d["terrain_type"],
            "average_watts": d["average_watts"],
            "normalized_power_watts": d["normalized_power_watts"],
            "intensity_factor": d["intensity_factor"],
            "estimated_tss": d["estimated_tss"],
            "has_gps": len(pts) >= 2,
            "thumbnail_svg": d["thumbnail_svg"] or "",
            "svg_path": svg_path,
            "start_xy": start_xy,
            "end_xy": end_xy,
            "is_loop": bool(d["is_loop"]),
            "orientation_label": d["orientation_label"] or "Outdoor Route",
            "map_points": sample_coordinates(pts, 250) if pts else [],
            "strava_url": d["strava_url"] or f"https://www.strava.com/activities/{d['id']}",
        }
        return out

    return {
        "id": str(ride_id),
        "map_points": sample_coordinates(pts, 250) if pts else [],
        "svg_path": svg_path,
        "start_xy": start_xy,
        "end_xy": end_xy,
    }



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
    # If cloning from a library template or empty, mint a persistent custom ID
    if not raw_id or raw_id.startswith("lib_") or raw_id.startswith("workout_primary") or raw_id.startswith("workout_alt"):
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
            int(hydrated.get("duration_minutes") or 45),
            int(hydrated.get("estimated_tss") or 40),
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

"""
Non-circular 4-Pillar Ride Debrief Analytics Engine.

Evaluates completed sessions across four orthogonal, physiology-first dimensions
so Zwift/ERG rides are never rubber-stamped solely on NP-vs-file compliance:
  1. Physiological Response  — Efficiency Factor (NP/HR) vs. personal baseline,
                               aerobic decoupling (Pw:Hr), HR cost, WHOOP strain & reaction.
  2. Readiness & Strategic Fit — Independent physiological readiness ceiling (WHOOP recovery,
                               14d HRV baseline, sleep, acute load) vs. actual session demand.
  3. Execution Nuances       — Variability Index (VI), ERG detection, duration completion,
                               half-split power/cadence/HR fade, interval fade, 3-tier XSS.
  4. Long-Term Goal Progress — Macrocycle phase & strain-mix alignment, pace-adjusted weekly
                               TSS/XSS trajectory, FTP gap, and 42-day power profile trends.
"""

import datetime
import math
from typing import Any, Dict, List, Optional, Tuple

from app.database import (
    get_athlete_date,
    get_current_user_id,
    get_db_connection,
)
from app.services.strain_model_service import is_cycling_sport


def _calc_stream_np(watts: List[float], dt_sec: float = 1.0) -> float:
    """Computes Coggan 30-second rolling Normalized Power from a power array."""
    clean = [max(0.0, float(w or 0.0)) for w in watts]
    n = len(clean)
    if n == 0:
        return 0.0
    win = max(1, int(round(30.0 / max(0.5, dt_sec))))
    if n < win:
        return (sum(w ** 4 for w in clean) / n) ** 0.25

    window_sum = sum(clean[:win])
    p4_sum = (window_sum / win) ** 4
    count = 1
    for i in range(win, n):
        window_sum += clean[i] - clean[i - win]
        p4_sum += (window_sum / win) ** 4
        count += 1
    return (p4_sum / count) ** 0.25


def _detect_work_intervals(
    watts: List[float],
    hr: Optional[List[float]],
    cadence: Optional[List[float]],
    ftp: int,
    dt_sec: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """
    Identifies discrete high-intensity work intervals (>= 85% FTP lasting >= 45s)
    and compares the first work block against the final work block to expose fade.
    """
    n = len(watts)
    if n < 60 or ftp <= 0:
        return None

    smooth_win = max(1, int(round(10.0 / max(0.5, dt_sec))))
    smoothed: List[float] = []
    running = 0.0
    for i, w in enumerate(watts):
        running += w
        if i >= smooth_win:
            running -= watts[i - smooth_win]
        denom = min(i + 1, smooth_win)
        smoothed.append(running / denom)

    work_thresh = ftp * 0.85
    rest_thresh = ftp * 0.75
    min_work_samples = max(3, int(round(45.0 / max(0.5, dt_sec))))
    min_rest_samples = max(2, int(round(20.0 / max(0.5, dt_sec))))

    blocks: List[Tuple[int, int]] = []
    in_block = False
    start_idx = 0
    below_rest_count = 0

    for i, p in enumerate(smoothed):
        if not in_block:
            if p >= work_thresh:
                in_block = True
                start_idx = i
                below_rest_count = 0
        else:
            if p < rest_thresh:
                below_rest_count += 1
                if below_rest_count >= min_rest_samples:
                    end_idx = i - below_rest_count + 1
                    if end_idx - start_idx >= min_work_samples:
                        blocks.append((start_idx, end_idx))
                    in_block = False
                    below_rest_count = 0
            else:
                below_rest_count = 0

    if in_block and (n - start_idx) >= min_work_samples:
        blocks.append((start_idx, n))

    if len(blocks) < 2:
        return None

    def _summarize_block(s_i: int, e_i: int) -> Dict[str, Optional[float]]:
        w_slice = [watts[k] for k in range(s_i, e_i)]
        avg_w = sum(w_slice) / max(1, len(w_slice))
        avg_hr = None
        if hr and len(hr) >= e_i:
            hr_slice = [float(hr[k]) for k in range(s_i, e_i) if hr[k] and float(hr[k]) > 40]
            if hr_slice:
                avg_hr = sum(hr_slice) / len(hr_slice)
        avg_cad = None
        if cadence and len(cadence) >= e_i:
            cad_slice = [float(cadence[k]) for k in range(s_i, e_i) if cadence[k] and float(cadence[k]) > 30]
            if cad_slice:
                avg_cad = sum(cad_slice) / len(cad_slice)
        return {"watts": avg_w, "hr": avg_hr, "cadence": avg_cad}

    first = _summarize_block(*blocks[0])
    last = _summarize_block(*blocks[-1])

    power_fade_pct = (
        round(((last["watts"] - first["watts"]) / first["watts"]) * 100.0, 1)
        if first["watts"] and first["watts"] > 0
        else None
    )
    hr_drift_bpm = (
        round(last["hr"] - first["hr"], 1)
        if first["hr"] is not None and last["hr"] is not None
        else None
    )
    cadence_fade_rpm = (
        round(last["cadence"] - first["cadence"], 1)
        if first["cadence"] is not None and last["cadence"] is not None
        else None
    )

    return {
        "interval_count": len(blocks),
        "first_block_watts": round(first["watts"]),
        "last_block_watts": round(last["watts"]),
        "interval_power_fade_pct": power_fade_pct,
        "first_block_hr": round(first["hr"]) if first["hr"] is not None else None,
        "last_block_hr": round(last["hr"]) if last["hr"] is not None else None,
        "interval_hr_drift_bpm": hr_drift_bpm,
        "first_block_cadence": round(first["cadence"]) if first["cadence"] is not None else None,
        "last_block_cadence": round(last["cadence"]) if last["cadence"] is not None else None,
        "interval_cadence_fade_rpm": cadence_fade_rpm,
    }


def _pearson_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    """Computes Pearson correlation coefficient between two equal-length numeric series."""
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    vx = sum(a * a for a in dx)
    vy = sum(b * b for b in dy)
    if vx <= 1e-9 or vy <= 1e-9:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / math.sqrt(vx * vy)


def _median_val(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


def _detect_erg_stream_steadiness(
    watts: List[float],
    dt_sec: float = 1.0,
    cadence: Optional[List[float]] = None,
) -> Tuple[Optional[bool], Optional[float], Dict[str, Any]]:
    """
    Distinguishes true smart-trainer ERG-mode lock from human self-paced SIM / Free-Ride /
    Slope / Resistance riding using three orthogonal physical signals across 20s active windows:
      1. Tight within-window CV: ERG holds wattage tightly (median CV <= 0.038, >=55% windows <= 0.038).
      2. Plateau step flatness: adjacent active windows inside ERG blocks stay flat (<=2.5% jump on >=40% pairs),
         whereas SIM/free-ride power drifts continuously with gradient, drafting, and effort.
      3. Power-cadence decoupling: in SIM/resistance mode, rising cadence increases power (median r >= 0.50);
         in ERG mode, the trainer inversely adjusts torque to keep watts flat regardless of cadence.
    """
    win = max(5, int(round(20.0 / max(0.5, dt_sec))))
    if len(watts) < win * 6:
        return None, None, {}

    has_cad = bool(cadence and len(cadence) == len(watts))
    cvs: List[float] = []
    window_means: List[Tuple[int, float]] = []
    pw_cad_rs: List[float] = []

    for w_idx, i in enumerate(range(0, len(watts) - win + 1, win)):
        seg = watts[i : i + win]
        if any(w <= 50.0 for w in seg):
            continue
        mean_w = sum(seg) / len(seg)
        if mean_w <= 50.0:
            continue
        var_w = sum((w - mean_w) ** 2 for w in seg) / len(seg)
        std_w = math.sqrt(var_w)
        cv = std_w / mean_w
        cvs.append(cv)
        window_means.append((w_idx, mean_w))

        if has_cad and std_w >= 2.0:
            c_seg = [float(cadence[k] or 0.0) for k in range(i, i + win)]  # type: ignore[index]
            if all(c > 30.0 for c in c_seg):
                c_mean = sum(c_seg) / len(c_seg)
                c_std = math.sqrt(sum((c - c_mean) ** 2 for c in c_seg) / len(c_seg))
                if c_std >= 1.5:
                    r_val = _pearson_corr(seg, c_seg)
                    if r_val is not None:
                        pw_cad_rs.append(r_val)

    if len(cvs) < 6:
        return None, None, {}

    median_cv = _median_val(cvs)
    assert median_cv is not None
    tight_frac = sum(1 for c in cvs if c <= 0.038) / len(cvs)

    # Check consecutive active window pairs for horizontal ERG plateaus vs. drifting SIM/free-ride power
    adj_diffs: List[float] = []
    for idx in range(1, len(window_means)):
        prev_wi, prev_m = window_means[idx - 1]
        cur_wi, cur_m = window_means[idx]
        if cur_wi == prev_wi + 1:
            denom = max(prev_m, cur_m, 1.0)
            adj_diffs.append(abs(cur_m - prev_m) / denom)
    flat_step_frac = (
        sum(1 for d in adj_diffs if d <= 0.025) / len(adj_diffs)
        if adj_diffs
        else 1.0
    )

    median_pw_cad_r = _median_val(pw_cad_rs) if len(pw_cad_rs) >= 4 else None

    steadiness_pass = (median_cv <= 0.038) and (tight_frac >= 0.55) and (flat_step_frac >= 0.40)
    cadence_coupled_sim = bool(
        median_pw_cad_r is not None
        and median_pw_cad_r >= 0.50
        and median_cv > 0.015
    )
    erg_detected = bool(steadiness_pass and not cadence_coupled_sim)

    diagnostics = {
        "median_cv": round(median_cv, 4),
        "tight_window_frac": round(tight_frac, 3),
        "flat_step_frac": round(flat_step_frac, 3),
        "median_pw_cad_r": round(median_pw_cad_r, 3) if median_pw_cad_r is not None else None,
        "cadence_coupled_sim": cadence_coupled_sim,
    }
    return erg_detected, round(median_cv, 4), diagnostics


def _has_explicit_non_erg_signal(
    primary_act: Optional[Dict[str, Any]],
    custom_prompt: str = "",
) -> bool:
    """
    Checks Strava activity metadata, title/description, and athlete debrief notes for
    unambiguous non-ERG ride indicators (races, group/pacer rides, free rides, SIM mode, etc.).
    """
    import json
    import re

    act = primary_act or {}
    name_l = str(act.get("name") or "").lower()
    desc_l = ""

    raw_json = act.get("raw_json")
    if raw_json:
        try:
            parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            if isinstance(parsed, dict):
                # Strava API cycling workout_type == 11 indicates a Race
                if parsed.get("workout_type") == 11:
                    return True
                desc_l = str(parsed.get("description") or "").lower()
        except Exception:
            pass

    combined_meta = f"{name_l} {desc_l}"
    non_erg_patterns = (
        r"\bno[\s-]*erg\b",
        r"\bnon[\s-]*erg\b",
        r"\berg[\s-]*off\b",
        r"\bwithout[\s-]*erg\b",
        r"\bsim[\s-]*mode\b",
        r"\bfree[\s-]*ride\b",
        r"\bfreeride\b",
        r"\brace\b",
        r"\bracing\b",
        r"\bzrl\b",
        r"\bttt\b",
        r"\btime[\s-]*trial\b",
        r"\bgroup[\s-]*ride\b",
        r"\bpacer\b",
        r"\brobopacer\b",
        r"\bpace[\s-]*partner\b",
        r"\bfondo\b",
        r"\bclimb[\s-]*portal\b",
        r"\bcrit\b",
        r"\bzwift[\s-]*games\b",
        r"\btour[\s-]*(of|de)\b",
    )
    if any(re.search(pat, combined_meta) for pat in non_erg_patterns):
        return True

    if custom_prompt and custom_prompt.strip():
        note_l = custom_prompt.lower()
        note_non_erg_patterns = (
            r"\bnot[\s-]*erg\b",
            r"\bwasn'?t[\s-]*erg\b",
            r"\bwas[\s-]+not[\s-]+erg\b",
            r"\bno[\s-]*erg\b",
            r"\bnon[\s-]*erg\b",
            r"\berg[\s-]*off\b",
            r"\bwithout[\s-]*erg\b",
            r"\bsim[\s-]*mode\b",
            r"\bfree[\s-]*ride\b",
        )
        if any(re.search(pat, note_l) for pat in note_non_erg_patterns):
            return True

    return False


def compute_stream_analytics(
    streams: Optional[Dict[str, List[float]]],
    ftp: int = 250,
) -> Optional[Dict[str, Any]]:
    """
    Computes physiological & pacing stream analytics from time/watts/heartrate/cadence:
      - Aerobic Decoupling (Pw:Hr) on main body (excluding warmup/cooldown ramps)
      - 1st-half vs. 2nd-half NP fade, HR drift, and Cadence fade
      - Discrete work-interval fade (1st vs. last >=85% FTP block)
      - Coggan Power Time-in-Zone distribution (Z1..Z5+)
      - Multi-signal ERG vs. Self-Paced SIM/Free-Ride detection (CV + plateaus + power-cadence coupling)
      - Peak 5s burst power & high-intensity surge count (>=120% FTP)
    """
    if not isinstance(streams, dict):
        return None

    raw_watts = streams.get("watts") or []
    raw_hr = streams.get("heartrate") or []
    raw_cad = streams.get("cadence") or []
    raw_time = streams.get("time") or []

    if len(raw_watts) < 60:
        return None

    watts = [max(0.0, float(w or 0.0)) for w in raw_watts]
    n = len(watts)

    # Estimate sample interval dt_sec
    if len(raw_time) >= 2 and float(raw_time[-1]) > float(raw_time[0]):
        total_sec = float(raw_time[-1]) - float(raw_time[0])
        dt_sec = max(0.5, total_sec / max(1, len(raw_time) - 1))
    else:
        dt_sec = 1.0
        total_sec = float(n)

    # Coggan Time-in-Zone distribution across full ride
    z1 = z2 = z3 = z4 = z5 = 0
    f = max(1.0, float(ftp))
    for w in watts:
        ratio = w / f
        if ratio < 0.56:
            z1 += 1
        elif ratio < 0.76:
            z2 += 1
        elif ratio < 0.91:
            z3 += 1
        elif ratio < 1.06:
            z4 += 1
        else:
            z5 += 1
    time_in_zones = {
        "Z1": round((z1 / n) * 100),
        "Z2": round((z2 / n) * 100),
        "Z3": round((z3 / n) * 100),
        "Z4": round((z4 / n) * 100),
        "Z5+": round((z5 / n) * 100),
    }

    # Trim initial warmup & final cooldown (up to 5 min or 10% of ride each) for decoupling/half-split
    trim_sec = min(300.0, total_sec * 0.10) if total_sec >= 1200 else 0.0
    trim_n = int(round(trim_sec / dt_sec))
    if n - (2 * trim_n) >= 60:
        body_start, body_end = trim_n, n - trim_n
    else:
        body_start, body_end = 0, n

    body_watts = watts[body_start:body_end]
    mid = len(body_watts) // 2
    if mid < 20:
        return {"has_streams": True, "time_in_zones": time_in_zones}

    w1 = body_watts[:mid]
    w2 = body_watts[mid:]
    np1 = _calc_stream_np(w1, dt_sec=dt_sec)
    np2 = _calc_stream_np(w2, dt_sec=dt_sec)
    power_fade_pct = round(((np2 - np1) / np1) * 100.0, 1) if np1 > 10 else None

    decoupling_pct = None
    ef1 = None
    ef2 = None
    hr_drift_bpm = None
    if len(raw_hr) >= body_end:
        body_hr = [float(h or 0.0) for h in raw_hr[body_start:body_end]]
        h1_valid = [h for h in body_hr[:mid] if h > 40]
        h2_valid = [h for h in body_hr[mid:] if h > 40]
        if len(h1_valid) >= 15 and len(h2_valid) >= 15 and total_sec >= 900:
            avg_h1 = sum(h1_valid) / len(h1_valid)
            avg_h2 = sum(h2_valid) / len(h2_valid)
            hr_drift_bpm = round(avg_h2 - avg_h1, 1)
            if np1 > 20 and np2 > 20 and avg_h1 > 40 and avg_h2 > 40:
                ef1 = round(np1 / avg_h1, 2)
                ef2 = round(np2 / avg_h2, 2)
                if ef1 > 0:
                    decoupling_pct = round(((ef1 - ef2) / ef1) * 100.0, 1)

    cadence_avg = None
    cadence_first_half = None
    cadence_second_half = None
    cadence_fade_rpm = None
    if len(raw_cad) >= body_end:
        all_cad_valid = [float(c) for c in raw_cad if c and float(c) > 25]
        if all_cad_valid:
            cadence_avg = round(sum(all_cad_valid) / len(all_cad_valid))
        body_cad = raw_cad[body_start:body_end]
        c1 = [float(c) for c in body_cad[:mid] if c and float(c) > 25]
        c2 = [float(c) for c in body_cad[mid:] if c and float(c) > 25]
        if len(c1) >= 15 and len(c2) >= 15:
            cadence_first_half = round(sum(c1) / len(c1), 1)
            cadence_second_half = round(sum(c2) / len(c2), 1)
            cadence_fade_rpm = round(cadence_second_half - cadence_first_half, 1)

    interval_fade = _detect_work_intervals(
        watts=watts,
        hr=raw_hr if len(raw_hr) == n else None,
        cadence=raw_cad if len(raw_cad) == n else None,
        ftp=ftp,
        dt_sec=dt_sec,
    )
    erg_stream_detected, erg_stream_cv, erg_diagnostics = _detect_erg_stream_steadiness(
        watts,
        dt_sec=dt_sec,
        cadence=raw_cad if len(raw_cad) == n else None,
    )

    # Peak 5s burst power & discrete surge count (>= 120% FTP for >= 5s)
    win_5s = max(1, int(round(5.0 / max(0.5, dt_sec))))
    max_5s_watts = None
    if n >= win_5s:
        s5 = sum(watts[:win_5s])
        best_5s = s5 / win_5s
        for i in range(win_5s, n):
            s5 += watts[i] - watts[i - win_5s]
            avg5 = s5 / win_5s
            if avg5 > best_5s:
                best_5s = avg5
        max_5s_watts = round(best_5s)

    surge_thresh = f * 1.20
    surge_reset = f * 0.95
    surge_min_samples = max(2, int(round(5.0 / max(0.5, dt_sec))))
    surge_count = 0
    above_run = 0
    in_surge = False
    for w in watts:
        if not in_surge:
            if w >= surge_thresh:
                above_run += 1
                if above_run >= surge_min_samples:
                    surge_count += 1
                    in_surge = True
            else:
                above_run = 0
        else:
            if w < surge_reset:
                in_surge = False
                above_run = 0

    return {
        "has_streams": True,
        "duration_sec": round(total_sec),
        "first_half_np": round(np1),
        "second_half_np": round(np2),
        "power_fade_pct": power_fade_pct,
        "first_half_ef": ef1,
        "second_half_ef": ef2,
        "decoupling_pct": decoupling_pct,
        "hr_drift_bpm": hr_drift_bpm,
        "cadence_avg": cadence_avg,
        "cadence_first_half": cadence_first_half,
        "cadence_second_half": cadence_second_half,
        "cadence_fade_rpm": cadence_fade_rpm,
        "interval_fade": interval_fade,
        "time_in_zones": time_in_zones,
        "erg_stream_detected": erg_stream_detected,
        "erg_stream_cv": erg_stream_cv,
        "erg_diagnostics": erg_diagnostics,
        "max_5s_watts": max_5s_watts,
        "surge_count": surge_count,
    }


def _get_personal_ef_baseline(
    user_id: str,
    act_date_str: str,
    primary_pct_ftp: int,
    ftp: int,
    lookback_days: int = 60,
) -> Dict[str, Any]:
    """
    Computes the athlete's personal Efficiency Factor (NP / avg HR) baseline from
    stored Strava cycling activities prior to act_date_str (strictly user-isolated).
    Prefers intensity-matched rides (+/- 15% FTP) when >= 3 exist.
    """
    try:
        ref_d = datetime.date.fromisoformat(act_date_str[:10])
    except Exception:
        ref_d = get_athlete_date(user_id)
    start_iso = (ref_d - datetime.timedelta(days=lookback_days)).isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT name, sport_type, start_date, moving_time_sec,
               average_watts, weighted_average_watts, average_heartrate
        FROM strava_activities
        WHERE user_id = ?
          AND substr(start_date, 1, 10) >= ?
          AND substr(start_date, 1, 10) < ?
        ORDER BY start_date DESC
        LIMIT 80
        """,
        (user_id, start_iso, act_date_str[:10]),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    all_efs: List[float] = []
    matched_efs: List[float] = []
    safe_ftp = max(1, int(ftp or 250))

    for r in rows:
        if not is_cycling_sport(r.get("sport_type") or "", r.get("name") or ""):
            continue
        dur = int(r.get("moving_time_sec") or 0)
        if dur < 1200:  # >= 20 min for stable EF
            continue
        np_w = float(r.get("weighted_average_watts") or r.get("average_watts") or 0.0)
        hr = float(r.get("average_heartrate") or 0.0)
        if np_w < 50 or hr < 75:
            continue
        ef = np_w / hr
        all_efs.append(ef)
        r_pct = (np_w / safe_ftp) * 100.0
        if primary_pct_ftp > 0 and abs(r_pct - primary_pct_ftp) <= 15.0:
            matched_efs.append(ef)

    if len(matched_efs) >= 3:
        return {
            "baseline_ef": round(sum(matched_efs) / len(matched_efs), 2),
            "sample_count": len(matched_efs),
            "baseline_scope": "intensity-matched 60d",
        }
    if len(all_efs) >= 2:
        return {
            "baseline_ef": round(sum(all_efs) / len(all_efs), 2),
            "sample_count": len(all_efs),
            "baseline_scope": "60d cycling avg",
        }
    return {"baseline_ef": None, "sample_count": 0, "baseline_scope": None}


def _get_personal_whoop_baseline(
    user_id: str,
    act_date_str: str,
    lookback_days: int = 14,
) -> Dict[str, Any]:
    """Computes trailing 14-day personal HRV and Recovery baselines prior to act_date_str."""
    try:
        ref_d = datetime.date.fromisoformat(act_date_str[:10])
    except Exception:
        ref_d = get_athlete_date(user_id)
    start_iso = (ref_d - datetime.timedelta(days=lookback_days)).isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT date, recovery_score, hrv_rmssd, day_strain
        FROM whoop_metrics
        WHERE user_id = ?
          AND date >= ?
          AND date < ?
        ORDER BY date DESC
        """,
        (user_id, start_iso, act_date_str[:10]),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    hrvs = [float(r["hrv_rmssd"]) for r in rows if r.get("hrv_rmssd") and float(r["hrv_rmssd"]) > 0]
    recs = [float(r["recovery_score"]) for r in rows if r.get("recovery_score") is not None]
    strains = [float(r["day_strain"]) for r in rows if r.get("day_strain") and float(r["day_strain"]) > 0]

    return {
        "hrv_baseline": round(sum(hrvs) / len(hrvs), 1) if len(hrvs) >= 3 else None,
        "recovery_baseline": round(sum(recs) / len(recs)) if len(recs) >= 3 else None,
        "strain_baseline": round(sum(strains) / len(strains), 1) if len(strains) >= 3 else None,
        "sample_days": len(rows),
    }


def analyze_physiological_response(
    *,
    has_cycling: bool,
    primary_watts: int,
    primary_pct_ftp: int,
    act_hr: int,
    act_max_hr: int,
    max_hr: int,
    calculated_tss: int,
    workout_strain: float,
    workout_recovery: int,
    workout_hrv: float,
    today_recovery: int,
    today_hrv: float,
    is_today: bool,
    is_yesterday: bool,
    vi: Optional[float],
    stream_metrics: Optional[Dict[str, Any]],
    act_date_str: str,
    ftp: int,
    user_id: str,
) -> Dict[str, Any]:
    """Pillar 1: Internal cardiovascular cost vs. external mechanical output."""
    if not has_cycling:
        hr_pct = round((act_hr / max(1, max_hr)) * 100) if act_hr > 0 else None
        rec_delta = (today_recovery - workout_recovery) if not is_today else None
        chips = []
        if act_hr > 0:
            chips.append(f"Avg HR {act_hr} bpm" + (f" ({hr_pct}% max)" if hr_pct else ""))
        if workout_strain > 0:
            chips.append(f"WHOOP {workout_strain:.1f} strain")
        if is_yesterday and rec_delta is not None:
            sign = "+" if rec_delta >= 0 else ""
            chips.append(f"Next-Day Rec {sign}{rec_delta}%")
        summary = (
            f"Cardiovascular load registered {act_hr} bpm avg HR and {workout_strain:.1f} WHOOP strain "
            f"without cycling pedal fatigue."
            if act_hr > 0
            else f"Logged {workout_strain:.1f} WHOOP strain from cross-training while sparing cycling musculature."
        )
        return {
            "status": "Aerobic Cross-Stimulus",
            "color": "emerald",
            "ef": None,
            "ef_baseline": None,
            "ef_delta_pct": None,
            "decoupling_pct": None,
            "avg_hr_pct_max": hr_pct,
            "max_hr_pct_max": round((act_max_hr / max(1, max_hr)) * 100) if act_max_hr > 0 else None,
            "recovery_reaction_delta": rec_delta,
            "chips": chips,
            "summary": summary,
        }

    ef = round(primary_watts / act_hr, 2) if (primary_watts > 0 and act_hr > 40) else None
    ef_base_info = _get_personal_ef_baseline(
        user_id=user_id,
        act_date_str=act_date_str,
        primary_pct_ftp=primary_pct_ftp,
        ftp=ftp,
    )
    ef_baseline = ef_base_info["baseline_ef"]
    ef_delta_pct = (
        round(((ef - ef_baseline) / ef_baseline) * 100.0, 1)
        if (ef is not None and ef_baseline and ef_baseline > 0)
        else None
    )

    decoupling_pct = stream_metrics.get("decoupling_pct") if stream_metrics else None
    hr_drift_bpm = stream_metrics.get("hr_drift_bpm") if stream_metrics else None
    is_stochastic = bool(vi and vi > 1.15)

    avg_hr_pct = round((act_hr / max(1, max_hr)) * 100) if act_hr > 0 else None
    max_hr_pct = round((act_max_hr / max(1, max_hr)) * 100) if act_max_hr > 0 else None
    rec_delta = (today_recovery - workout_recovery) if is_yesterday else None

    # Determine physiological response verdict
    status = "Normal Cardiac Cost"
    color = "cyan"
    signals_good = 0
    signals_strain = 0

    if ef_delta_pct is not None:
        if ef_delta_pct >= 3.0:
            signals_good += 2
        elif ef_delta_pct <= -4.0:
            signals_strain += 2
    if decoupling_pct is not None and not is_stochastic:
        if decoupling_pct <= 4.5:
            signals_good += 2
        elif decoupling_pct >= 8.0:
            signals_strain += 2
        elif decoupling_pct >= 5.5:
            signals_strain += 1
    if is_yesterday and rec_delta is not None:
        if rec_delta <= -20:
            signals_strain += 1
        elif rec_delta >= 5:
            signals_good += 1

    if signals_strain >= 2:
        if decoupling_pct is not None and decoupling_pct >= 8.0 and not is_stochastic:
            status = "High Cardiac Drift"
            color = "rose"
        else:
            status = "Elevated Cardiac Cost"
            color = "amber"
    elif signals_good >= 2:
        status = "Strong Aerobic Efficiency"
        color = "emerald"
    elif decoupling_pct is not None and decoupling_pct <= 5.0 and not is_stochastic:
        status = "Well Coupled"
        color = "emerald"

    # Build concise metric chips
    chips: List[str] = []
    if ef is not None:
        if ef_delta_pct is not None:
            sign = "+" if ef_delta_pct >= 0 else ""
            chips.append(f"EF {ef:.2f} ({sign}{ef_delta_pct:.1f}% vs {ef_base_info['baseline_scope']})")
        else:
            chips.append(f"EF {ef:.2f} W/bpm")
    if decoupling_pct is not None:
        lbl = "Cardiac Drift" if is_stochastic else "Pw:Hr Drift"
        sign = "+" if decoupling_pct > 0 else ""
        chips.append(f"{lbl} {sign}{decoupling_pct:.1f}%")
    if avg_hr_pct is not None:
        chips.append(f"HR {act_hr} bpm ({avg_hr_pct}% max)")
    if is_yesterday and rec_delta is not None:
        sign = "+" if rec_delta >= 0 else ""
        chips.append(f"Next-Day Rec {workout_recovery}%→{today_recovery}% ({sign}{rec_delta}%)")
    elif workout_strain > 0:
        chips.append(f"WHOOP Strain {workout_strain:.1f}")

    # Build plain-English summary
    parts: List[str] = []
    if ef is not None and ef_delta_pct is not None:
        if ef_delta_pct >= 3.0:
            parts.append(
                f"Efficiency Factor hit {ef:.2f} ({ef_delta_pct:+.1f}% above your {ef_baseline:.2f} {ef_base_info['baseline_scope']}), "
                f"showing you delivered more watts per heartbeat than usual."
            )
        elif ef_delta_pct <= -4.0:
            parts.append(
                f"Efficiency Factor dipped to {ef:.2f} ({ef_delta_pct:+.1f}% below your {ef_baseline:.2f} baseline), "
                f"indicating higher cardiovascular cost per watt—often a sign of residual fatigue, heat, or hydration lag."
            )
        else:
            parts.append(
                f"Efficiency Factor was {ef:.2f} ({ef_delta_pct:+.1f}% vs. your {ef_baseline:.2f} baseline), "
                f"tracking cleanly with your recent aerobic norm."
            )
    elif ef is not None:
        parts.append(f"Aerobic Efficiency Factor registered {ef:.2f} ({primary_watts}W NP / {act_hr} bpm).")
    elif act_hr > 0:
        parts.append(f"Average heart rate held at {act_hr} bpm ({avg_hr_pct}% of max HR).")
    else:
        parts.append("No heart rate telemetry was recorded for this session, limiting internal-cost analysis.")

    if decoupling_pct is not None:
        if is_stochastic:
            parts.append(f"HR drifted {hr_drift_bpm:+.0f} bpm across the second half ({decoupling_pct:+.1f}% Pw:Hr shift across intervals).")
        elif decoupling_pct <= 5.0:
            parts.append(f"Aerobic decoupling stayed tight at {decoupling_pct:.1f}% (<5%), confirming solid aerobic durability.")
        elif decoupling_pct <= 8.0:
            parts.append(f"Moderate aerobic decoupling of {decoupling_pct:.1f}% (HR {hr_drift_bpm:+.0f} bpm late) shows creeping cardiovascular fatigue.")
        else:
            parts.append(f"Notable aerobic decoupling of {decoupling_pct:.1f}% (HR {hr_drift_bpm:+.0f} bpm late) points to fueling, cooling, or durability limits.")

    if is_yesterday and rec_delta is not None:
        if rec_delta <= -15:
            parts.append(f"WHOOP recovery reacted by dropping from {workout_recovery}% to {today_recovery}% today, confirming real systemic load.")
        elif rec_delta >= 5:
            parts.append(f"Your body absorbed the load smoothly—WHOOP recovery rebounded from {workout_recovery}% to {today_recovery}% today.")
        else:
            parts.append(f"WHOOP recovery held steady ({workout_recovery}% → {today_recovery}% today), showing good load absorption.")

    return {
        "status": status,
        "color": color,
        "ef": ef,
        "ef_baseline": ef_baseline,
        "ef_baseline_scope": ef_base_info["baseline_scope"],
        "ef_delta_pct": ef_delta_pct,
        "decoupling_pct": decoupling_pct,
        "hr_drift_bpm": hr_drift_bpm,
        "avg_hr_pct_max": avg_hr_pct,
        "max_hr_pct_max": max_hr_pct,
        "recovery_reaction_delta": rec_delta,
        "chips": chips,
        "summary": " ".join(parts),
    }


def analyze_readiness_fit(
    *,
    has_cycling: bool,
    primary_pct_ftp: int,
    calculated_tss: int,
    high_xss: float,
    peak_xss: float,
    workout_recovery: int,
    workout_hrv: float,
    sleep_score: int,
    acute_tss: int,
    weekly_tss_target: int,
    day_cfg: Optional[Dict[str, Any]],
    prescribed_source: str,
    prescribed_title: str,
    act_date_str: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Pillar 2: Evaluates whether the session actually made sense for the athlete's
    physiological readiness—completely independent of ERG/scheduled workout overrides.
    """
    whoop_base = _get_personal_whoop_baseline(user_id=user_id, act_date_str=act_date_str)
    hrv_baseline = whoop_base["hrv_baseline"]
    hrv_delta_pct = (
        round(((workout_hrv - hrv_baseline) / hrv_baseline) * 100.0, 1)
        if (workout_hrv and workout_hrv > 0 and hrv_baseline and hrv_baseline > 0)
        else None
    )

    is_rest_directive = bool(day_cfg and (day_cfg.get("is_default_rest") or day_cfg.get("is_directive_rest")))
    high_acute_load = bool(weekly_tss_target > 0 and acute_tss >= weekly_tss_target * 0.90)
    hrv_depressed = bool(hrv_delta_pct is not None and hrv_delta_pct <= -15.0)
    poor_sleep = bool(sleep_score and sleep_score < 70)

    # Independent physiological readiness ceiling
    if workout_recovery < 34:
        rec_tier = "Red Recovery — Rest / Zone 1"
        rec_max_pct = 58
        rec_max_tss = 30
        readiness_band = "red"
    elif workout_recovery <= 66 or hrv_depressed:
        rec_tier = "Yellow Readiness — Zone 2 Aerobic Base"
        rec_max_pct = 76
        rec_max_tss = 65
        readiness_band = "yellow"
    else:
        if high_acute_load or poor_sleep:
            rec_tier = "Green w/ Fatigue Guard — Endurance / Tempo"
            rec_max_pct = 86
            rec_max_tss = 85
        else:
            rec_tier = "Green Readiness — Cleared for Quality"
            rec_max_pct = 110
            rec_max_tss = 120
        readiness_band = "green"

    high_intensity_load = (primary_pct_ftp >= 82) or (high_xss >= 18.0) or (peak_xss >= 6.0)

    # Compare actual workout demand against independent readiness ceiling
    if not has_cycling:
        status = "Aligned with Readiness"
        color = "emerald"
        if readiness_band == "red" and calculated_tss >= 45:
            status = "Heavy for Red Readiness"
            color = "amber"
            summary = f"Cross-training logged {calculated_tss} TSS on {workout_recovery}% Red recovery—keep tomorrow easy to clear systemic stress."
        else:
            summary = f"Cross-training load ({calculated_tss} TSS) fit well alongside your {workout_recovery}% recovery baseline."
    elif is_rest_directive and calculated_tss >= 40:
        status = "Trained on Rest Day"
        color = "amber"
        summary = (
            f"Your weekly schedule marks this as a dedicated rest day, yet you logged {calculated_tss} TSS at {primary_pct_ftp}% FTP. "
            f"Ensure you bank a substitute recovery day so chronic fatigue doesn't accumulate."
        )
    elif readiness_band == "red":
        if primary_pct_ftp > rec_max_pct + 6 or calculated_tss > rec_max_tss + 15:
            status = "Overreached Readiness"
            color = "rose"
            summary = (
                f"Even if you hit your planned file, pushing {primary_pct_ftp}% FTP ({calculated_tss} TSS) on {workout_recovery}% Red recovery "
                f"exceeded what your body was primed to absorb (ceiling: ≤{rec_max_pct}% FTP / ≤{rec_max_tss} TSS). Prioritize full recovery next."
            )
        else:
            status = "Smart Recovery Discipline"
            color = "emerald"
            summary = f"You respected your {workout_recovery}% Red recovery by keeping output restrained ({primary_pct_ftp}% FTP, {calculated_tss} TSS)."
    elif readiness_band == "yellow":
        if primary_pct_ftp > rec_max_pct + 10 or (high_intensity_load and calculated_tss > rec_max_tss):
            status = "Aggressive for Readiness"
            color = "amber"
            hrv_note = f" and HRV {hrv_delta_pct:+.0f}% vs. 14d avg" if hrv_depressed else ""
            summary = (
                f"With {workout_recovery}% readiness{hrv_note}, your independent ceiling was Zone 2 (≤{rec_max_pct}% FTP). "
                f"Pushing {primary_pct_ftp}% FTP ({calculated_tss} TSS, {high_xss:.0f} High XSS) is an aggressive stretch—watch tomorrow's recovery closely."
            )
        elif primary_pct_ftp > rec_max_pct + 4 or high_xss >= 14.0:
            status = "Productive Stretch"
            color = "amber"
            summary = (
                f"Slightly above your {workout_recovery}% readiness Zone 2 ceiling ({primary_pct_ftp}% FTP vs. ≤{rec_max_pct}%), "
                f"but controlled total load ({calculated_tss} TSS) keeps it absorbable with good sleep tonight."
            )
        else:
            status = "Aligned with Readiness"
            color = "emerald"
            summary = (
                f"Smart match for {workout_recovery}% Yellow readiness: {primary_pct_ftp}% FTP ({calculated_tss} TSS) built aerobic work "
                f"without digging an unrecoverable fatigue hole."
            )
    else:  # green
        if primary_pct_ftp < 72 and calculated_tss < 55:
            status = "Deliberate Base Choice"
            color = "cyan"
            summary = (
                f"Your {workout_recovery}% Green readiness had headroom for threshold/VO2 work, so riding at {primary_pct_ftp}% FTP ({calculated_tss} TSS) "
                f"was a conservative aerobic choice—ideal if you are saving legs for a key upcoming session."
            )
        elif high_acute_load and primary_pct_ftp > 90 and calculated_tss > 85:
            status = "Heavy on Stacked Fatigue"
            color = "amber"
            summary = (
                f"Morning recovery was Green ({workout_recovery}%), but trailing 7-day load was already high ({acute_tss} TSS). "
                f"Stacking {calculated_tss} TSS at {primary_pct_ftp}% FTP deepens acute fatigue—plan an absorption day next."
            )
        else:
            status = "Aligned with Readiness"
            color = "emerald"
            summary = (
                f"Strong strategic fit: you capitalized on {workout_recovery}% Green readiness with {primary_pct_ftp}% FTP ({calculated_tss} TSS), "
                f"matching stimulus to your body's capacity to adapt."
            )

    chips = [
        f"Recovery {workout_recovery}%",
        f"Ceiling: {rec_tier.split('—')[-1].strip()}",
    ]
    if hrv_delta_pct is not None:
        sign = "+" if hrv_delta_pct >= 0 else ""
        chips.append(f"HRV {workout_hrv:.0f}ms ({sign}{hrv_delta_pct:.0f}% vs 14d)")
    elif workout_hrv and workout_hrv > 0:
        chips.append(f"HRV {workout_hrv:.0f}ms")
    if is_rest_directive:
        chips.append("Scheduled Rest Day")

    return {
        "status": status,
        "color": color,
        "readiness_band": readiness_band,
        "recommended_tier": rec_tier,
        "recommended_max_pct_ftp": rec_max_pct,
        "recommended_max_tss": rec_max_tss,
        "hrv_baseline": hrv_baseline,
        "hrv_delta_pct": hrv_delta_pct,
        "is_rest_directive": is_rest_directive,
        "chips": chips,
        "summary": summary,
    }


def analyze_execution_nuances(
    *,
    has_cycling: bool,
    primary_act: Dict[str, Any],
    primary_watts: int,
    act_min: int,
    planned_duration_min: Optional[int],
    low_xss: float,
    high_xss: float,
    peak_xss: float,
    total_xss: float,
    battery_depleted_pct: float,
    stream_metrics: Optional[Dict[str, Any]],
    ftp: int = 250,
    custom_prompt: str = "",
) -> Dict[str, Any]:
    """
    Pillar 3: Looks past whole-ride NP compliance to evaluate how the ride actually unfolded:
    accurate ERG vs. self-paced detection, VI, duration completion, power/cadence/interval fade,
    peak surges, and energy-system mix.
    """
    if not has_cycling:
        return {
            "status": "Non-Cycling Session",
            "color": "cyan",
            "vi": None,
            "is_erg_like": False,
            "pacing_mode": "cross_training",
            "pacing_mode_label": "Cross-Training",
            "duration_completion_pct": None,
            "power_fade_pct": None,
            "cadence_avg": None,
            "cadence_fade_rpm": None,
            "interval_fade": None,
            "time_in_zones": None,
            "chips": [f"Duration {act_min}m", f"Total Strain {total_xss:.1f} XSS"],
            "summary": f"Logged {act_min}m of cross-training ({total_xss:.1f} XSS). Cycling power execution metrics do not apply.",
        }

    avg_watts = float(primary_act.get("average_watts") or 0.0)
    vi = round(primary_watts / avg_watts, 2) if (primary_watts > 0 and avg_watts > 20) else None
    sport_l = (primary_act.get("sport_type") or primary_act.get("type") or "").lower()
    name_l = (primary_act.get("name") or "").lower()
    is_indoor_platform = ("virtual" in sport_l) or any(k in name_l for k in ("zwift", "trainerroad", "rouvy", "wahoo", "erg"))
    erg_stream_detected = stream_metrics.get("erg_stream_detected") if stream_metrics else None
    explicit_non_erg = _has_explicit_non_erg_signal(primary_act, custom_prompt=custom_prompt)

    # Accurate ERG detection hierarchy:
    # 1. Explicit non-ERG metadata/title/note always rules out ERG.
    # 2. Non-indoor platforms (outdoor rides) are never ERG.
    # 3. When 1-Hz power stream telemetry exists, trust stream ERG detection (NEVER override with VI!).
    # 4. Only when streams are unavailable on an indoor ride, use a tight VI <= 1.03 fallback.
    if explicit_non_erg or not is_indoor_platform:
        is_erg_like = False
    elif erg_stream_detected is not None:
        is_erg_like = bool(erg_stream_detected)
    else:
        is_erg_like = bool(vi is not None and vi <= 1.03)

    if is_erg_like:
        pacing_mode = "erg"
        pacing_mode_label = "ERG-Locked"
    elif is_indoor_platform:
        pacing_mode = "self_paced_indoor"
        pacing_mode_label = "Self-Paced Indoor (Non-ERG)"
    else:
        pacing_mode = "outdoor"
        pacing_mode_label = "Outdoor Self-Paced"

    duration_completion_pct = (
        round((act_min / planned_duration_min) * 100)
        if (planned_duration_min and planned_duration_min > 0)
        else None
    )

    power_fade_pct = stream_metrics.get("power_fade_pct") if stream_metrics else None
    cadence_avg = stream_metrics.get("cadence_avg") if stream_metrics else None
    cadence_fade_rpm = stream_metrics.get("cadence_fade_rpm") if stream_metrics else None
    interval_fade = stream_metrics.get("interval_fade") if stream_metrics else None
    time_in_zones = stream_metrics.get("time_in_zones") if stream_metrics else None
    max_5s_watts = stream_metrics.get("max_5s_watts") if stream_metrics else None
    surge_count = int(stream_metrics.get("surge_count") or 0) if stream_metrics else 0

    # Determine status
    status = "Disciplined Self-Pacing" if pacing_mode == "self_paced_indoor" else "Controlled Pacing"
    color = "emerald"
    if duration_completion_pct is not None and duration_completion_pct < 80:
        status = "Cut Short"
        color = "amber"
    elif interval_fade and interval_fade.get("interval_power_fade_pct") is not None and interval_fade["interval_power_fade_pct"] <= -6.0 and not is_erg_like:
        status = "Late Interval Fade"
        color = "amber"
    elif cadence_fade_rpm is not None and cadence_fade_rpm <= -5.0:
        status = "Muscular Cadence Fade"
        color = "amber"
    elif power_fade_pct is not None and power_fade_pct <= -6.0 and not is_erg_like:
        status = "Second-Half Fade"
        color = "amber"
    elif power_fade_pct is not None and power_fade_pct >= 4.0 and not is_erg_like:
        status = "Strong Negative Split"
        color = "emerald"
    elif is_erg_like:
        status = "ERG-Locked Structure"
        color = "cyan"
    elif vi is not None and vi > 1.12:
        status = "Punchy / Stochastic"
        color = "cyan"

    chips: List[str] = []
    if pacing_mode == "self_paced_indoor":
        chips.append("Self-Paced (Non-ERG)")
    if vi is not None:
        if is_erg_like:
            vi_lbl = "ERG Structured" if vi > 1.05 else "ERG Steady"
        elif pacing_mode == "self_paced_indoor":
            vi_lbl = "Self-Paced Steady" if vi <= 1.06 else ("Self-Paced Variable" if vi <= 1.12 else "Stochastic")
        else:
            vi_lbl = "Smooth" if vi <= 1.06 else ("Rolling" if vi <= 1.12 else "Stochastic")
        chips.append(f"VI {vi:.2f} ({vi_lbl})")
    if duration_completion_pct is not None and planned_duration_min:
        chips.append(f"Duration {act_min}m / {planned_duration_min}m ({duration_completion_pct}%)")
    if interval_fade and interval_fade.get("interval_count"):
        f_pct = interval_fade.get("interval_power_fade_pct")
        f_str = f" ({f_pct:+.1f}% last vs 1st)" if (f_pct is not None and not is_erg_like) else ""
        chips.append(f"{interval_fade['interval_count']} Work Blocks{f_str}")
    elif power_fade_pct is not None:
        chips.append(f"2nd Half NP {power_fade_pct:+.1f}%")
    if not is_erg_like and surge_count >= 3:
        chips.append(f"{surge_count} Surges (>120% FTP)")
    if cadence_avg is not None:
        cad_str = f"Cadence {cadence_avg} rpm"
        if cadence_fade_rpm is not None and abs(cadence_fade_rpm) >= 2.0:
            cad_str += f" ({cadence_fade_rpm:+.0f} late)"
        chips.append(cad_str)
    if battery_depleted_pct >= 15.0:
        chips.append(f"W' Used {battery_depleted_pct:.0f}%")

    parts: List[str] = []
    if is_erg_like:
        if vi is not None and vi > 1.05:
            parts.append(
                f"Indoor ERG-mode structured intervals (VI {vi:.2f}) held each block's target wattage automatically, so focus on your cadence stability and heart-rate cost rather than wattage compliance."
            )
        else:
            parts.append(
                f"Indoor ERG-style pacing locked wattage tightly (VI {vi:.2f}), so wattage compliance alone isn't the real story—focus on your cadence and heart-rate cost."
            )
    elif pacing_mode == "self_paced_indoor":
        if vi is not None and vi <= 1.06:
            parts.append(
                f"Self-paced indoor ride (non-ERG)—holding a tight VI of {vi:.2f} manually without trainer lock reflects strong shifting and pacing discipline."
            )
        elif vi is not None and vi <= 1.12:
            parts.append(
                f"Self-paced indoor ride (non-ERG, VI {vi:.2f}) where you modulated power manually across virtual terrain, pacing shifts, or hard efforts."
            )
        elif vi is not None:
            parts.append(
                f"Self-paced indoor ride (non-ERG) with a punchy, stochastic power profile (VI {vi:.2f}) driven by manual surges and terrain."
            )
        else:
            parts.append("Self-paced indoor session (non-ERG) with manual power control.")
    elif vi is not None:
        if vi <= 1.05:
            parts.append(f"Very steady self-paced effort outdoors (VI {vi:.2f}), minimizing wasted anaerobic surges.")
        elif vi <= 1.12:
            parts.append(f"Moderately variable outdoor power profile (VI {vi:.2f}), typical of rolling terrain or structured surges.")
        else:
            parts.append(f"Highly stochastic outdoor effort (VI {vi:.2f}) with repeated surges above average power.")

    if not is_erg_like and power_fade_pct is not None and not (interval_fade and interval_fade.get("interval_count", 0) >= 2):
        if power_fade_pct >= 4.0:
            parts.append(
                f"Executed a strong negative split ({power_fade_pct:+.1f}% NP in the 2nd half: {stream_metrics.get('first_half_np')}W → {stream_metrics.get('second_half_np')}W), finishing stronger than you started."
            )
        elif power_fade_pct <= -6.0:
            parts.append(
                f"Second-half NP faded {power_fade_pct:.1f}% ({stream_metrics.get('first_half_np')}W → {stream_metrics.get('second_half_np')}W), suggesting an aggressive opening pace or late fatigue."
            )
        else:
            parts.append(
                f"Even manual split across both halves ({power_fade_pct:+.1f}% NP shift: {stream_metrics.get('first_half_np')}W → {stream_metrics.get('second_half_np')}W)."
            )

    if duration_completion_pct is not None and planned_duration_min:
        if duration_completion_pct < 80:
            parts.append(f"You wrapped early ({act_min}m vs. {planned_duration_min}m planned, {duration_completion_pct}%), trimming planned volume.")
        elif duration_completion_pct >= 115:
            parts.append(f"You extended the ride beyond the plan ({act_min}m vs. {planned_duration_min}m planned, +{act_min - planned_duration_min}m extra volume).")

    if interval_fade and interval_fade.get("interval_count", 0) >= 2:
        ic = interval_fade["interval_count"]
        fp = interval_fade.get("interval_power_fade_pct")
        fh = interval_fade.get("interval_hr_drift_bpm")
        fc = interval_fade.get("interval_cadence_fade_rpm")
        if fp is not None and fp <= -5.0 and not is_erg_like:
            parts.append(f"Across {ic} self-paced work blocks, power faded {fp:.1f}% from block 1 ({interval_fade['first_block_watts']}W) to block {ic} ({interval_fade['last_block_watts']}W).")
        elif fp is not None and fp >= 4.0 and not is_erg_like:
            hr_s = f" with HR {fh:+.0f} bpm" if fh is not None and abs(fh) >= 3 else ""
            parts.append(f"Built power across {ic} self-paced work blocks (+{fp:.1f}% from {interval_fade['first_block_watts']}W to {interval_fade['last_block_watts']}W){hr_s}.")
        elif fp is not None:
            hr_s = f" while HR rose {fh:+.0f} bpm" if fh is not None and abs(fh) >= 3 else ""
            cad_s = f" and cadence shifted {fc:+.0f} rpm" if fc is not None and abs(fc) >= 3 else ""
            if is_erg_like:
                parts.append(f"Across {ic} ERG work blocks ({interval_fade['first_block_watts']}W avg → {interval_fade['last_block_watts']}W avg){hr_s}{cad_s}.")
            else:
                parts.append(f"Held power cleanly across all {ic} self-paced work blocks ({interval_fade['first_block_watts']}W → {interval_fade['last_block_watts']}W){hr_s}{cad_s}.")
    elif cadence_fade_rpm is not None:
        if cadence_fade_rpm <= -5.0:
            parts.append(f"Cadence dropped {abs(cadence_fade_rpm):.0f} rpm in the second half (avg {cadence_avg} rpm), an early sign of muscular fatigue even while holding watts.")
        elif cadence_avg:
            parts.append(f"Cadence stayed consistent around {cadence_avg} rpm ({cadence_fade_rpm:+.0f} rpm late).")

    if not is_erg_like and (surge_count >= 3 or (max_5s_watts and max_5s_watts >= max(350, int(ftp * 1.65)))):
        burst_note = f"Peak 5s burst hit {max_5s_watts}W" if max_5s_watts else "Multiple anaerobic surges"
        if surge_count >= 3:
            parts.append(f"{burst_note} across {surge_count} discrete surges above 120% FTP.")
        else:
            parts.append(f"{burst_note}, taxing neuromuscular power.")

    if total_xss > 0:
        high_share = round(((high_xss + peak_xss) / total_xss) * 100)
        if high_share >= 25:
            parts.append(f"Energy mix skewed glycolytic/anaerobic ({high_share}% High+Peak XSS, {battery_depleted_pct:.0f}% W' battery tapped).")
        else:
            parts.append(f"Energy mix stayed predominantly aerobic ({100 - high_share}% Low XSS, {battery_depleted_pct:.0f}% W' tapped).")

    return {
        "status": status,
        "color": color,
        "vi": vi,
        "is_erg_like": is_erg_like,
        "pacing_mode": pacing_mode,
        "pacing_mode_label": pacing_mode_label,
        "planned_duration_min": planned_duration_min,
        "actual_duration_min": act_min,
        "duration_completion_pct": duration_completion_pct,
        "power_fade_pct": power_fade_pct,
        "cadence_avg": cadence_avg,
        "cadence_fade_rpm": cadence_fade_rpm,
        "interval_fade": interval_fade,
        "time_in_zones": time_in_zones,
        "max_5s_watts": max_5s_watts,
        "surge_count": surge_count,
        "chips": chips,
        "summary": " ".join(parts),
    }


def analyze_long_term_goal_progress(
    *,
    program: Dict[str, Any],
    active_plan: Optional[Dict[str, Any]],
    ftp: int,
    calculated_tss: int,
    low_xss: float,
    high_xss: float,
    peak_xss: float,
    total_xss: float,
    acute_tss: int,
    today: datetime.date,
    user_id: str,
    session_power_prs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Pillar 4: Connects today's session directly to the athlete's long-term macrocycle goal,
    weekly pace, FTP progression gap, phase energy-system target, Spiderweb Power PRs set
    in this session, and 30-day power profile trends.
    """
    prog = program or {}
    goal_title = prog.get("goal_title") or prog.get("title") or "Threshold & FTP Progression"
    phase = prog.get("phase") or "Build Phase"
    phase_focus = prog.get("phase_focus") or prog.get("target_focus_duration") or "Progressive Power Density"
    current_week = int(prog.get("current_week") or 1)
    total_weeks = int(prog.get("total_weeks") or 8)
    days_remaining = int(prog.get("days_remaining") or max(0, (total_weeks - current_week) * 7))
    target_ftp = int(prog.get("target_ftp") or (ftp + 15))
    ftp_gap = max(0, target_ftp - ftp)

    weekly_tss_target = int(prog.get("weekly_tss_target") or 360)
    # Use the larger of program's weekly actual or trailing acute_tss if program dict is minimal
    weekly_tss_actual = int(prog.get("weekly_tss_actual") if prog.get("weekly_tss_actual") is not None else acute_tss)
    weekly_tss_pct = min(150, round((weekly_tss_actual / max(1, weekly_tss_target)) * 100))
    ride_share_pct = round((calculated_tss / max(1, weekly_tss_target)) * 100) if calculated_tss > 0 else 0

    # Pace-adjusted weekly status based on weekday (Mon=1 .. Sun=7)
    day_of_week_num = today.weekday() + 1
    expected_pct = round((day_of_week_num / 7.0) * 100)
    is_deload = "deload" in phase.lower() or "recovery" in phase.lower()

    prs = session_power_prs if isinstance(session_power_prs, dict) else {}
    has_session_prs = bool(prs.get("has_prs"))
    has_all_time_prs = bool(prs.get("has_all_time_prs"))

    if has_all_time_prs and not is_deload:
        all_cnt = int(prs.get("all_time_count") or 0)
        pace_status = f"New Spiderweb PR{'s' if all_cnt > 1 else ''}"
        color = "emerald"
    elif is_deload:
        pace_status = "Recovery / Deload Week"
        color = "cyan"
    elif weekly_tss_pct >= expected_pct + 15:
        pace_status = "Ahead of Weekly Pace"
        color = "emerald" if weekly_tss_pct <= 115 else "amber"
    elif weekly_tss_pct >= expected_pct - 15:
        pace_status = "On Track"
        color = "emerald"
    else:
        pace_status = "Behind Weekly Pace"
        color = "amber"

    # Compare this ride's 3-tier strain signature against phase target distribution
    target_dist = prog.get("target_strain_distribution") or {"low_pct": 75, "high_pct": 20, "peak_pct": 5}
    target_high_peak = int(target_dist.get("high_pct", 20)) + int(target_dist.get("peak_pct", 5))
    ride_high_peak = round(((high_xss + peak_xss) / total_xss) * 100) if total_xss > 0 else 0

    if total_xss <= 0:
        phase_alignment = "Passive rest day supporting adaptation."
    elif "base" in phase.lower():
        if ride_high_peak <= 18:
            phase_alignment = "Directly reinforces your Base Phase aerobic foundation."
        else:
            phase_alignment = f"Added extra high-end stimulus ({ride_high_peak}% High+Peak XSS) on top of your Base Phase aerobic focus."
    elif "build" in phase.lower() or "peak" in phase.lower() or "specialty" in phase.lower():
        if ride_high_peak >= max(12, target_high_peak - 10):
            phase_alignment = f"Directly feeds your {phase} target ({ride_high_peak}% High+Peak XSS toward your {target_high_peak}% phase goal)."
        else:
            phase_alignment = f"Banked aerobic durability ({100 - ride_high_peak}% Low XSS) during {phase}; pair with 1–2 higher-intensity sessions this week to hit your {target_high_peak}% High/Peak target."
    else:
        phase_alignment = f"Supports {phase} freshness and load management."

    # Pull lightweight 30-day power spiderweb progress (strictly user-isolated)
    trend_20m_w = None
    trend_5m_w = None
    growth_focus = None
    recent_pr_badge = None
    try:
        from app.services.power_profile_service import get_power_spiderweb_profile
        profile = get_power_spiderweb_profile(timeframe="30d", user_id=user_id)
        if isinstance(profile, dict):
            s_deltas = profile.get("summary_deltas") or {}
            t20 = s_deltas.get("threshold_20m") or {}
            t5 = s_deltas.get("vo2_5m") or {}
            if t20.get("delta_watts") is not None and t20.get("previous_watts"):
                trend_20m_w = int(t20["delta_watts"])
            if t5.get("delta_watts") is not None and t5.get("previous_watts"):
                trend_5m_w = int(t5["delta_watts"])
            pheno = profile.get("phenotype") or {}
            growth_focus = pheno.get("growth_focus")
            bks = profile.get("recent_breakthroughs") or []
            if bks:
                recent_pr_badge = bks[0].get("badge")
    except Exception:
        pass

    has_event = bool(active_plan and active_plan.get("days_until") is not None and int(active_plan.get("days_until", -1)) >= 0)
    event_title = active_plan.get("title") if has_event else prog.get("event_title")
    event_days = int(active_plan["days_until"]) if has_event else None

    chips: List[str] = []
    if has_session_prs:
        highlights = prs.get("highlights") or []
        for hl in highlights[:3]:
            icon_p = "🏆" if hl.get("scope") == "all_time" else "📈"
            chips.append(f"{icon_p} {hl.get('badge')}")
        extra_cnt = int(prs.get("total_pr_count") or 0) - min(3, len(highlights))
        if extra_cnt > 0:
            chips.append(f"+{extra_cnt} more PR{'s' if extra_cnt > 1 else ''}")

    chips.extend([
        f"{phase} • Wk {current_week}/{total_weeks}",
        f"Weekly {weekly_tss_actual}/{weekly_tss_target} TSS ({weekly_tss_pct}%)",
        f"FTP {ftp}W → {target_ftp}W" if ftp_gap > 0 else f"FTP Target {target_ftp}W Met",
    ])
    if has_event and event_days is not None:
        chips.append(f"{event_title}: {event_days}d out")
    elif trend_20m_w is not None and trend_20m_w != 0:
        chips.append(f"30d 20m Power {trend_20m_w:+d}W")
    if recent_pr_badge and not has_session_prs:
        chips.append(f"Recent: {recent_pr_badge}")

    parts: List[str] = []
    if has_session_prs and prs.get("summary_text"):
        parts.append(str(prs["summary_text"]))
    parts.append(
        f"Toward '{goal_title}' ({phase}, Week {current_week} of {total_weeks}), you're at {weekly_tss_actual}/{weekly_tss_target} TSS ({weekly_tss_pct}% vs. ~{expected_pct}% mid-week pace)."
    )
    if calculated_tss > 0:
        parts.append(f"This session contributed +{ride_share_pct}% of your weekly target. {phase_alignment}")
    else:
        parts.append(phase_alignment)

    if ftp_gap > 0:
        trend_note = ""
        if trend_20m_w is not None and trend_20m_w > 0:
            trend_note = f" (30d 20m power trending +{trend_20m_w}W)"
        elif trend_20m_w is not None and trend_20m_w < 0:
            trend_note = f" (30d 20m power {trend_20m_w}W vs. prior block)"
        parts.append(f"You remain {ftp_gap}W shy of your {target_ftp}W FTP goal{trend_note}.")
    if has_event and event_days is not None:
        parts.append(f"{event_days} days until {event_title}.")

    return {
        "status": pace_status,
        "color": color,
        "goal_title": goal_title,
        "phase": phase,
        "phase_focus": phase_focus,
        "current_week": current_week,
        "total_weeks": total_weeks,
        "days_remaining": days_remaining,
        "current_ftp": ftp,
        "target_ftp": target_ftp,
        "ftp_gap_w": ftp_gap,
        "weekly_tss_actual": weekly_tss_actual,
        "weekly_tss_target": weekly_tss_target,
        "weekly_tss_pct": weekly_tss_pct,
        "expected_weekly_pct": expected_pct,
        "this_ride_weekly_share_pct": ride_share_pct,
        "trend_20m_w": trend_20m_w,
        "trend_5m_w": trend_5m_w,
        "growth_focus": growth_focus,
        "recent_pr_badge": recent_pr_badge,
        "session_power_prs": prs if has_session_prs else None,
        "event_title": event_title,
        "event_days_until": event_days,
        "phase_alignment": phase_alignment,
        "chips": chips,
        "summary": " ".join(parts),
    }


def build_four_pillar_debrief(
    *,
    has_cycling: bool,
    primary_act: Optional[Dict[str, Any]],
    primary_watts: int,
    primary_pct_ftp: int,
    act_min: int,
    act_hr: int,
    act_max_hr: int,
    max_hr: int,
    calculated_tss: int,
    low_xss: float,
    high_xss: float,
    peak_xss: float,
    total_xss: float,
    battery_depleted_pct: float,
    workout_strain: float,
    workout_recovery: int,
    workout_hrv: float,
    today_recovery: int,
    today_hrv: float,
    sleep_score: int,
    acute_tss: int,
    program: Dict[str, Any],
    active_plan: Optional[Dict[str, Any]],
    day_cfg: Optional[Dict[str, Any]],
    prescribed_info: Dict[str, Any],
    is_today: bool,
    is_yesterday: bool,
    act_date_str: str,
    today: datetime.date,
    ftp: int,
    user_id: Optional[str] = None,
    streams: Optional[Dict[str, List[float]]] = None,
    evaluated_acts: Optional[List[Dict[str, Any]]] = None,
    custom_prompt: str = "",
) -> Dict[str, Any]:
    """Orchestrates all 4 non-circular debrief pillars into a single structured payload."""
    uid = user_id or get_current_user_id()
    weekly_tss_target = int((program or {}).get("weekly_tss_target") or 360)

    stream_metrics = compute_stream_analytics(streams, ftp=ftp) if (has_cycling and streams) else None

    avg_watts = float((primary_act or {}).get("average_watts") or 0.0)
    vi = round(primary_watts / avg_watts, 2) if (has_cycling and primary_watts > 0 and avg_watts > 20) else None
    planned_dur = prescribed_info.get("planned_duration_min")

    # Detect Spiderweb Power PRs set during this evaluated session (strictly user-isolated)
    session_power_prs: Dict[str, Any] = {
        "has_prs": False,
        "has_all_time_prs": False,
        "all_time_prs": [],
        "recent_30d_bests": [],
        "highlights": [],
        "goal_axes_achieved": [],
        "all_time_count": 0,
        "recent_30d_count": 0,
        "total_pr_count": 0,
        "peak_source": "none",
        "summary_text": "",
    }
    if has_cycling:
        sess_acts = evaluated_acts if evaluated_acts else ([primary_act] if primary_act else [])
        try:
            from app.services.power_profile_service import detect_session_spiderweb_prs
            session_power_prs = detect_session_spiderweb_prs(
                evaluated_acts=sess_acts,
                act_date_str=act_date_str,
                user_id=uid,
                primary_act=primary_act,
                primary_streams=streams,
            )
        except Exception:
            pass

    p1_phys = analyze_physiological_response(
        has_cycling=has_cycling,
        primary_watts=primary_watts,
        primary_pct_ftp=primary_pct_ftp,
        act_hr=act_hr,
        act_max_hr=act_max_hr,
        max_hr=max_hr,
        calculated_tss=calculated_tss,
        workout_strain=workout_strain,
        workout_recovery=workout_recovery,
        workout_hrv=workout_hrv,
        today_recovery=today_recovery,
        today_hrv=today_hrv,
        is_today=is_today,
        is_yesterday=is_yesterday,
        vi=vi,
        stream_metrics=stream_metrics,
        act_date_str=act_date_str,
        ftp=ftp,
        user_id=uid,
    )

    p2_readiness = analyze_readiness_fit(
        has_cycling=has_cycling,
        primary_pct_ftp=primary_pct_ftp,
        calculated_tss=calculated_tss,
        high_xss=high_xss,
        peak_xss=peak_xss,
        workout_recovery=workout_recovery,
        workout_hrv=workout_hrv,
        sleep_score=sleep_score,
        acute_tss=acute_tss,
        weekly_tss_target=weekly_tss_target,
        day_cfg=day_cfg,
        prescribed_source=str(prescribed_info.get("source") or ""),
        prescribed_title=str(prescribed_info.get("target_title") or ""),
        act_date_str=act_date_str,
        user_id=uid,
    )

    p3_execution = analyze_execution_nuances(
        has_cycling=has_cycling,
        primary_act=primary_act or {},
        primary_watts=primary_watts,
        act_min=act_min,
        planned_duration_min=planned_dur,
        low_xss=low_xss,
        high_xss=high_xss,
        peak_xss=peak_xss,
        total_xss=total_xss,
        battery_depleted_pct=battery_depleted_pct,
        stream_metrics=stream_metrics,
        ftp=ftp,
        custom_prompt=custom_prompt,
    )

    p4_goal = analyze_long_term_goal_progress(
        program=program,
        active_plan=active_plan,
        ftp=ftp,
        calculated_tss=calculated_tss,
        low_xss=low_xss,
        high_xss=high_xss,
        peak_xss=peak_xss,
        total_xss=total_xss,
        acute_tss=acute_tss,
        today=today,
        user_id=uid,
        session_power_prs=session_power_prs,
    )

    # Synthesize a non-circular headline takeaway badge prioritizing safety/readiness warnings,
    # then celebrating new Spiderweb Power PR breakthroughs when recovery/physiology are healthy.
    if p2_readiness["color"] == "rose":
        takeaway_badge = f"⚠️ {p2_readiness['status']}"
        takeaway_color = "rose"
    elif p1_phys["color"] == "rose":
        takeaway_badge = f"🫀 {p1_phys['status']}"
        takeaway_color = "rose"
    elif p2_readiness["color"] == "amber":
        takeaway_badge = f"⚡ {p2_readiness['status']}"
        takeaway_color = "amber"
    elif p1_phys["color"] == "amber":
        takeaway_badge = f"❤️ {p1_phys['status']}"
        takeaway_color = "amber"
    elif p3_execution["color"] == "amber":
        takeaway_badge = f"⚙️ {p3_execution['status']}"
        takeaway_color = "amber"
    elif session_power_prs.get("has_all_time_prs"):
        pr_n = int(session_power_prs.get("all_time_count") or 1)
        takeaway_badge = f"🏆 {pr_n} New Spiderweb PR{'s' if pr_n > 1 else ''}"
        takeaway_color = "emerald"
    elif p1_phys["color"] == "emerald" and p2_readiness["color"] == "emerald":
        takeaway_badge = f"✅ {p1_phys['status']}"
        takeaway_color = "emerald"
    else:
        takeaway_badge = f"🧭 {p2_readiness['status']}"
        takeaway_color = p2_readiness["color"]

    return {
        "physiological_response": p1_phys,
        "readiness_fit": p2_readiness,
        "execution_nuances": p3_execution,
        "goal_progress": p4_goal,
        "session_power_prs": session_power_prs,
        "has_stream_telemetry": bool(stream_metrics and stream_metrics.get("has_streams")),
        "is_erg_like": bool(p3_execution.get("is_erg_like")),
        "pacing_mode": p3_execution.get("pacing_mode", "outdoor"),
        "pacing_mode_label": p3_execution.get("pacing_mode_label", "Self-Paced"),
        "takeaway_badge": takeaway_badge,
        "takeaway_color": takeaway_color,
    }

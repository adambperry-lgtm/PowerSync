import datetime
from typing import Dict, Any, List, Optional
from app.database import (
    get_setting,
    set_setting,
    get_db_connection,
    get_current_user_id,
    get_athlete_date,
    get_active_target_plan,
)


def build_ftp_test_workout(
    protocol_type: str = "20m_coggan",
    ftp: int = 250,
    duration_min: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generates a structured FTP Test workout (Coggan 20-Min Standard or Progressive Ramp Test)
    with intervals, ZWO XML, Intervals.icu text, and 3-tier strain metrics.
    """
    from app.services.zwift_service import generate_zwo_xml, generate_intervals_icu_text, reconcile_workout_intervals
    from app.services.ai_coach import enrich_workout_strain

    proto = str(protocol_type or "20m_coggan").lower().strip()
    if proto in ("ramp", "ramp_test", "step"):
        dur = int(duration_min or 38)
        title = "Progressive Ramp FTP Test"
        focus_area = "FTP Assessment (Ramp Protocol)"
        estimated_tss = 48
        ai_rationale = (
            f"Progressive Ramp FTP Test calibrated to your current {ftp}W FTP: "
            f"10-min progressive warmup followed by 1-minute steps increasing +6% FTP per minute "
            f"until exhaustion. Your new FTP is ~75% of your best 1-minute step power."
        )
        steps = [
            {"type": "SteadyState", "duration_sec": 60, "power_pct": pct, "cadence": 92, "name": f"Ramp Step {idx + 1} ({pct}% FTP)"}
            for idx, pct in enumerate([55, 61, 67, 73, 79, 85, 91, 97, 103, 109, 115, 121, 127, 133, 139])
        ]
        intervals = [
            {"type": "Warmup", "duration_sec": 600, "power_low_pct": 45, "power_high_pct": 65, "cadence": 88, "name": "Progressive Warmup"},
            *steps,
            {"type": "Cooldown", "duration_sec": 480, "power_low_pct": 55, "power_high_pct": 38, "cadence": 82, "name": "Recovery Cooldown"},
        ]
        if dur != 38:
            intervals = reconcile_workout_intervals(intervals, dur, ftp=ftp)
        proto_key = "ramp_test"
    else:
        dur = int(duration_min or 55)
        title = "Coggan 20-Min Standard FTP Test"
        focus_area = "FTP Assessment (20m Time Trial)"
        estimated_tss = 68
        target_20m_w = round(ftp * 1.05)
        ai_rationale = (
            f"Standard Coggan 20-Min FTP Test protocol: includes a 12-min progressive warmup, "
            f"3x 1-min fast-pedal openers, a 5-min all-out anaerobic blowout (~110% FTP / {round(ftp * 1.10)}W) "
            f"to clear W' and prime oxygen kinetics, 8-min recovery spin, and a 20-min all-out TT "
            f"(target ~{target_20m_w}W). Multiply your 20-min average power by 0.95 for your new FTP."
        )
        intervals = [
            {"type": "Warmup", "duration_sec": 720, "power_low_pct": 45, "power_high_pct": 68, "cadence": 90, "name": "Progressive Warmup"},
            {
                "type": "Repeats",
                "repeat": 3,
                "on_duration_sec": 60,
                "off_duration_sec": 60,
                "on_power_pct": 100,
                "off_power_pct": 50,
                "cadence": 105,
                "cadence_rest": 85,
                "name": "3x 1m Fast-Pedal Openers",
            },
            {"type": "SteadyState", "duration_sec": 300, "power_pct": 110, "cadence": 95, "name": "5m Anaerobic Blowout"},
            {"type": "SteadyState", "duration_sec": 480, "power_pct": 50, "cadence": 85, "name": "8m Recovery Spin"},
            {"type": "SteadyState", "duration_sec": 1200, "power_pct": 105, "cadence": 94, "name": "20m All-Out FTP Test"},
            {"type": "Cooldown", "duration_sec": 420, "power_low_pct": 55, "power_high_pct": 38, "cadence": 82, "name": "Recovery Cooldown"},
        ]
        if dur != 55:
            intervals = reconcile_workout_intervals(intervals, dur, ftp=ftp)
        proto_key = "20m_coggan"

    workout_obj = {
        "id": "workout_primary",
        "option_type": "ftp_test",
        "protocol_type": proto_key,
        "badge": "🧪 Coach FTP Test",
        "badge_color": "magenta",
        "title": title,
        "description": f"Structured {title} calibrated to {ftp}W FTP",
        "focus_area": focus_area,
        "duration_minutes": dur,
        "estimated_tss": estimated_tss,
        "ai_rationale": ai_rationale,
        "intervals": intervals,
    }
    workout_obj["zwo_content"] = generate_zwo_xml(workout_obj, ftp)
    workout_obj["intervals_icu_text"] = generate_intervals_icu_text(workout_obj)
    return enrich_workout_strain(workout_obj, ftp)


def _infer_last_ftp_test_date(uid: str, activities: List[Dict[str, Any]]) -> Optional[str]:
    """
    Resolves the most recent FTP test date from explicit settings first,
    then falls back to scanning Strava activities and saved workouts for FTP/Ramp test titles.
    """
    explicit = get_setting("ftp_last_tested_date", None, user_id=uid)
    if explicit:
        return str(explicit)[:10]

    keywords = ("ftp test", "ramp test", "20m test", "20-min test", "threshold test", "benchmark test")
    best_date: Optional[str] = None

    for act in activities or []:
        name = str(act.get("name") or "").lower()
        if any(k in name for k in keywords):
            d = str(act.get("start_date") or "")[:10]
            if d and (best_date is None or d > best_date):
                best_date = d

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT date, title FROM workouts WHERE user_id = ? ORDER BY date DESC LIMIT 40",
            (uid,),
        )
        for row in c.fetchall():
            t = str(row["title"] or "").lower()
            if any(k in t for k in keywords):
                d = str(row["date"] or "")[:10]
                if d and (best_date is None or d > best_date):
                    best_date = d
        conn.close()
    except Exception:
        pass

    return best_date


def _estimate_breakthrough_eftp(
    activities: List[Dict[str, Any]],
    current_ftp: int,
    today: datetime.date,
    user_id: Optional[str] = None,
    mmp_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Scans recent cycling activities (last 30 days) for sustained high-power performances
    that suggest the athlete's current FTP setting may be underestimating true threshold.
    Prefers cached 1-Hz Strava stream MMP peaks (20m * 0.95 and 60m * 1.00) when available,
    falling back to ride-level NP / average watts when streams are not cached.
    """
    cutoff = (today - datetime.timedelta(days=30)).isoformat()
    best_eftp = current_ftp
    breakthrough_ride = None

    if mmp_map is None and user_id:
        try:
            from app.services.strava_service import get_cached_mmp_peaks_map
            mmp_map = get_cached_mmp_peaks_map(user_id=user_id)
        except Exception:
            mmp_map = {}
    mmp_map = mmp_map or {}

    for act in activities or []:
        d = str(act.get("start_date") or "")[:10]
        if d < cutoff:
            continue
        moving_sec = int(act.get("moving_time_sec") or act.get("moving_time") or 0)
        if moving_sec < 1200:  # need at least 20 minutes
            continue

        act_id = str(act.get("id") or "")
        act_mmp = mmp_map.get(act_id) if act_id else None

        est = 0
        ref_w = 0.0
        eff_dur_min = moving_sec // 60
        source = "summary"

        if isinstance(act_mmp, dict) and act_mmp.get("has_power_stream"):
            p_20m = int(act_mmp.get("20m") or 0)
            p_60m = int(act_mmp.get("60m") or 0)
            est_20 = round(p_20m * 0.95) if p_20m > 0 else 0
            est_60 = p_60m if p_60m > 0 else 0
            if est_20 >= est_60 and est_20 > 0:
                est = est_20
                ref_w = float(p_20m)
                eff_dur_min = 20
                source = "1hz_20m_stream"
            elif est_60 > 0:
                est = est_60
                ref_w = float(p_60m)
                eff_dur_min = 60
                source = "1hz_60m_stream"

        if est <= 0:
            np_w = float(act.get("weighted_average_watts") or 0.0)
            avg_w = float(act.get("average_watts") or 0.0)
            ref_w = np_w if np_w > 0 else avg_w
            if ref_w <= 0:
                continue

            # For 20–35 min hard efforts, 95% of NP/avg approximates FTP; for longer rides >= 45m, NP itself is a conservative floor
            if moving_sec <= 2400:
                est = round(ref_w * 0.95)
            elif moving_sec <= 3600:
                est = round(ref_w * 0.97)
            else:
                est = round(ref_w)

        if est > best_eftp:
            best_eftp = est
            breakthrough_ride = {
                "name": act.get("name") or "Recent Ride",
                "date": d,
                "watts": round(ref_w),
                "duration_min": eff_dur_min,
                "estimated_ftp": est,
                "source": source,
            }

    delta_w = best_eftp - current_ftp
    return {
        "estimated_ftp": best_eftp,
        "delta_watts": delta_w,
        "has_breakthrough": delta_w >= 4,
        "breakthrough_ride": breakthrough_ride,
    }


def evaluate_ftp_test_readiness(
    user_id: Optional[str] = None,
    activities: Optional[List[Dict[str, Any]]] = None,
    whoop_data: Optional[Dict[str, Any]] = None,
    program_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Analyzes training block progress, FTP staleness, recent power breakthroughs,
    Whoop physiological readiness, 3-tier strain fatigue clearance, and weekly
    schedule availability to determine if and when the athlete should do an FTP test.
    """
    uid = user_id or get_current_user_id()
    today = get_athlete_date(uid)
    today_iso = today.isoformat()
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid))
    is_travel_recovery = bool(get_setting("travel_recovery_week_active", False, user_id=uid))

    # 1. Load Activities if not provided
    if activities is None:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT 60",
            (uid,),
        )
        rows = c.fetchall()
        conn.close()
        activities = [dict(r) for r in rows] if rows else []

    # 2. Load Whoop Metrics if not provided
    if whoop_data is None:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1",
            (uid,),
        )
        w_row = c.fetchone()
        conn.close()
        if w_row:
            whoop_data = {
                "date": w_row["date"],
                "recovery_score": int(w_row["recovery_score"] or 50),
                "hrv_rmssd": float(w_row["hrv_rmssd"] or 45.0),
                "sleep_performance": int(w_row["sleep_performance"] or 80),
                "day_strain": float(w_row["day_strain"] or 0.0),
            }
        else:
            whoop_data = {"date": today_iso, "recovery_score": 65, "hrv_rmssd": 50.0, "sleep_performance": 80, "day_strain": 0.0}

    recovery_score = int(whoop_data.get("recovery_score") or 50)
    day_strain = float(whoop_data.get("day_strain") or 0.0)

    # 3. Trailing Strain & Load
    from app.services.strain_model_service import calculate_trailing_strain_systems
    from app.services.strava_service import get_strava_trailing_stats, resolve_strava_local_start
    from app.services.whoop_service import get_trailing_whoop_stats

    strain_systems = calculate_trailing_strain_systems(activities=activities, days=7, ftp=ftp)
    acute_high_xss = float(strain_systems.get("acute_48h", {}).get("high_xss", 0.0))
    yesterday_high_xss = float(strain_systems.get("yesterday", {}).get("high_xss", 0.0))

    strava_7d = get_strava_trailing_stats(activities=activities, days=7, user_id=uid)
    strava_28d = get_strava_trailing_stats(activities=activities, days=28, user_id=uid)
    yesterday_tss = int(strava_7d.get("yesterday_tss", 0))
    weekly_avg_tss_28d = round(int(strava_28d.get("total_tss", 0)) / 4.0)
    rides_28d = len([
        a for a in activities
        if (resolve_strava_local_start(a, user_id=uid) or str(a.get("start_date") or ""))[:10] >= (today - datetime.timedelta(days=28)).isoformat()
    ])

    whoop_trailing = get_trailing_whoop_stats(days=7, user_id=uid)
    yesterday_strain = float(whoop_trailing.get("yesterday_strain", 0.0))

    today_acts = [
        a for a in activities
        if (resolve_strava_local_start(a, user_id=uid) or str(a.get("start_date") or ""))[:10] == today_iso
    ]
    already_trained_today = bool(
        (sum(int(a.get("moving_time_sec") or 0) for a in today_acts) >= 1200 and day_strain >= 3.0)
        or day_strain >= 12.0
    )

    # 4. Program & Event Context
    if program_data is None:
        from app.services.program_service import get_current_program
        program_data = get_current_program(
            strava_weekly_tss=int(strava_7d.get("total_tss", 0)),
            strain_systems=strain_systems,
            user_id=uid,
        )

    phase = str(program_data.get("phase") or "Build Phase")
    progress_pct = int(program_data.get("progress_pct") or 0)
    current_week = int(program_data.get("current_week") or 1)
    total_weeks = int(program_data.get("total_weeks") or 8)
    has_specific_event = bool(program_data.get("has_specific_event"))
    days_remaining = int(program_data.get("days_remaining") or 30)

    # 5. Staleness & eFTP Breakthrough
    last_test_date = _infer_last_ftp_test_date(uid, activities)
    days_since_last_test: Optional[int] = None
    if last_test_date:
        try:
            days_since_last_test = max(0, (today - datetime.date.fromisoformat(last_test_date)).days)
        except Exception:
            days_since_last_test = None

    eftp_info = _estimate_breakthrough_eftp(activities, ftp, today, user_id=uid)

    # 6. Score the 4 Pillars (Total 0-100)
    # Pillar A: Block Timing & Staleness (0-30)
    if "Mastery" in phase or progress_pct >= 85:
        timing_score = 26
        timing_note = f"{phase} ({progress_pct}% through block) — ideal benchmark window."
    elif "Build" in phase and (current_week % 4 == 0 or progress_pct >= 55):
        timing_score = 22
        timing_note = f"Week {current_week}/{total_weeks} ({phase}) — mid/late-block checkpoint."
    elif "Specialty" in phase or "Peak" in phase:
        timing_score = 18
        timing_note = f"{phase} — useful to verify threshold before peak sharpening."
    else:
        timing_score = 11
        timing_note = f"Early {phase} (Week {current_week}/{total_weeks}) — still building base."

    if days_since_last_test is None:
        timing_score = min(30, timing_score + 4)
        staleness_note = "No prior FTP test recorded."
    elif days_since_last_test >= 42:
        timing_score = min(30, timing_score + 5)
        staleness_note = f"Last tested {days_since_last_test} days ago (stale)."
    elif days_since_last_test >= 28:
        timing_score = min(30, timing_score + 3)
        staleness_note = f"Last tested {days_since_last_test} days ago."
    else:
        staleness_note = f"Tested {days_since_last_test} days ago."

    # Pillar B: Progress & Breakthrough Signals (0-25)
    if eftp_info["has_breakthrough"]:
        progress_score = 24
        br = eftp_info["breakthrough_ride"]
        progress_note = (
            f"Breakthrough detected: ~{eftp_info['estimated_ftp']}W eFTP (+{eftp_info['delta_watts']}W) "
            f"from '{br['name']}' ({br['watts']}W for {br['duration_min']}m)."
        )
    elif rides_28d >= 10 or weekly_avg_tss_28d >= 180:
        progress_score = 17
        progress_note = f"Consistent block ({rides_28d} rides / ~{weekly_avg_tss_28d} TSS/wk over 28d)."
    elif rides_28d >= 5:
        progress_score = 12
        progress_note = f"Moderate consistency ({rides_28d} rides over 28d)."
    else:
        progress_score = 6
        progress_note = f"Low recent ride volume ({rides_28d} rides in 28d) — build consistency first."

    # Pillar C: Acute Readiness (0-25)
    if recovery_score > 66:
        readiness_score = 25
        readiness_note = f"Green Whoop recovery ({recovery_score}%) — autonomic system primed."
    elif recovery_score >= 50:
        readiness_score = 14
        readiness_note = f"Moderate Yellow recovery ({recovery_score}%) — sub-optimal for max effort."
    elif recovery_score >= 34:
        readiness_score = 7
        readiness_note = f"Low Yellow recovery ({recovery_score}%) — defer max testing."
    else:
        readiness_score = 0
        readiness_note = f"Red recovery ({recovery_score}%) — recovery priority, no testing."

    # Pillar D: Fatigue Clearance (0-20)
    if already_trained_today:
        fatigue_score = 2
        fatigue_note = "Already trained today — save max effort for a fresh day."
    elif acute_high_xss < 25.0 and yesterday_tss < 75 and yesterday_strain < 14.0:
        fatigue_score = 20
        fatigue_note = f"Fresh anaerobic battery (48h High XSS: {acute_high_xss:.1f}, yesterday {yesterday_tss} TSS)."
    elif acute_high_xss < 35.0 and yesterday_tss < 105:
        fatigue_score = 11
        fatigue_note = f"Residual fatigue present (48h High XSS: {acute_high_xss:.1f}, yesterday {yesterday_tss} TSS)."
    else:
        fatigue_score = 3
        fatigue_note = f"High acute fatigue (yesterday {yesterday_tss} TSS, 48h High XSS: {acute_high_xss:.1f})."

    total_score = max(0, min(100, timing_score + progress_score + readiness_score + fatigue_score))

    # 7. Determine Best Upcoming Window (Today + Next 3 Days) & Protocol
    from app.services.preferences_service import get_day_target_config
    from app.services.forecast_service import get_forecast_for_date

    candidate_windows: List[Dict[str, Any]] = []
    for offset in range(0, 4):
        d = today + datetime.timedelta(days=offset)
        d_iso = d.isoformat()
        cfg = get_day_target_config(d)
        is_rest = bool(cfg.get("is_default_rest") or cfg.get("is_directive_rest") or cfg.get("preferred_duration_min", 45) == 0)
        pref_dur = int(cfg.get("preferred_duration_min") or 45)

        if offset == 0:
            proj_rec = recovery_score
            usable = (not is_rest) and (not already_trained_today) and (proj_rec > 66) and (fatigue_score >= 12)
            day_label = "Today"
        else:
            fc = get_forecast_for_date(d_iso, user_id=uid)
            if fc:
                proj_rec = int(fc.get("projected_recovery") or 70)
                fc_rest = bool(fc.get("is_default_rest") or fc.get("is_directive_rest") or fc.get("duration_min") == 0)
                is_rest = is_rest or fc_rest
            else:
                # Simple physiological recovery rebound estimate if no forecast cached yet
                proj_rec = min(85, max(55, recovery_score + (12 if offset >= 2 else 8)))
            usable = (not is_rest) and (proj_rec >= 65)
            day_label = "Tomorrow" if offset == 1 else d.strftime("%A (%b %-d)")

        proto = "20m_coggan" if pref_dur >= 55 else "ramp_test"
        proto_dur = 55 if proto == "20m_coggan" else min(45, max(35, pref_dur))
        candidate_windows.append({
            "offset": offset,
            "date": d_iso,
            "day_label": day_label,
            "weekday": cfg.get("day_name", d.strftime("%A")),
            "projected_recovery": proj_rec,
            "is_rest": is_rest,
            "preferred_duration_min": pref_dur,
            "recommended_protocol": proto,
            "recommended_duration_min": proto_dur,
            "usable": usable,
        })

    best_window = next((w for w in candidate_windows if w["usable"]), None)
    if not best_window:
        # Fallback to first non-rest day
        best_window = next((w for w in candidate_windows if not w["is_rest"]), candidate_windows[0])

    # 8. Final Status & Coach Headline
    if is_travel_recovery:
        status = "HOLD"
        status_label = "Deload Week Active"
        headline = "Defer FTP Testing During Travel & Recovery Week"
        rationale = "Your Travel & Recovery deload week is active. Focus on restoration now and schedule an FTP test at the start of next week once fresh."
    elif has_specific_event and days_remaining <= 7:
        status = "DEFER_EVENT"
        status_label = f"T-{days_remaining} Event Taper"
        headline = f"Protect Freshness for {program_data.get('event_title', 'Target Event')}"
        rationale = f"With {days_remaining} days until your target event, an all-out FTP test would compromise taper freshness. Test after event recovery."
    elif days_since_last_test is not None and days_since_last_test < 14 and not eftp_info["has_breakthrough"]:
        status = "DEFER_RECENT"
        status_label = f"Tested {days_since_last_test}d Ago"
        headline = "Recent FTP Benchmark Still Valid"
        rationale = f"You tested {days_since_last_test} days ago. Give your body at least 3–4 weeks of progressive overload before re-testing."
    elif total_score >= 70 and candidate_windows[0]["usable"]:
        status = "PRIME_NOW"
        status_label = "Prime Window Today"
        headline = f"Ready for an FTP Test Today ({total_score}/100)"
        rationale = (
            f"Green Whoop recovery ({recovery_score}%), cleared acute fatigue, and {staleness_note.lower()} "
            f"{progress_note} Recommended: { 'Coggan 20-Min Standard FTP Test' if best_window['recommended_protocol'] == '20m_coggan' else 'Progressive Ramp FTP Test' }."
        )
    elif total_score >= 50 and best_window and best_window["offset"] > 0 and best_window["usable"]:
        status = "SOON"
        status_label = f"Best Window: {best_window['day_label']}"
        headline = f"Target {best_window['day_label']} for Your FTP Test"
        rationale = (
            f"Today isn't ideal ({readiness_note.rstrip('.')} / {fatigue_note.rstrip('.')}), "
            f"but {best_window['day_label']} projects ~{best_window['projected_recovery']}% recovery with {best_window['preferred_duration_min']}m available."
        )
    elif total_score >= 60 and best_window and best_window["usable"]:
        status = "SOON"
        status_label = f"Window: {best_window['day_label']}"
        headline = f"Good Window Opening {best_window['day_label']}"
        rationale = f"{timing_note} {progress_note} {fatigue_note}"
    else:
        status = "HOLD"
        status_label = "Keep Building"
        headline = "Keep Building Before Testing FTP"
        rationale = f"{readiness_note} {fatigue_note} {timing_note}"

    rec_proto = best_window["recommended_protocol"] if best_window else "20m_coggan"
    rec_dur = best_window["recommended_duration_min"] if best_window else 55
    rec_proto_label = "Coggan 20-Min FTP Test (55m)" if rec_proto == "20m_coggan" else f"Progressive Ramp Test ({rec_dur}m)"

    return {
        "status": status,
        "status_label": status_label,
        "readiness_score": total_score,
        "headline": headline,
        "rationale": rationale,
        "current_ftp": ftp,
        "estimated_ftp": eftp_info["estimated_ftp"],
        "eftp_delta_watts": eftp_info["delta_watts"],
        "has_breakthrough": eftp_info["has_breakthrough"],
        "breakthrough_ride": eftp_info["breakthrough_ride"],
        "last_test_date": last_test_date,
        "days_since_last_test": days_since_last_test,
        "recommended_window": best_window,
        "recommended_window_label": best_window["day_label"] if best_window else "Next Fresh Green Day",
        "recommended_protocol": rec_proto,
        "recommended_protocol_label": rec_proto_label,
        "recommended_duration_min": rec_dur,
        "pillars": {
            "block_timing": {"score": timing_score, "max": 30, "note": timing_note},
            "progress_signal": {"score": progress_score, "max": 25, "note": progress_note},
            "physiological_readiness": {"score": readiness_score, "max": 25, "note": readiness_note},
            "fatigue_clearance": {"score": fatigue_score, "max": 20, "note": fatigue_note},
        },
        "candidate_windows": candidate_windows,
    }


def record_ftp_test_result(
    new_ftp: int,
    protocol: str = "20m_coggan",
    test_date: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Records a completed FTP test result, updates athlete_ftp and ftp_last_tested_date,
    and re-synchronizes the athlete's Power Spiderweb goal.
    """
    uid = user_id or get_current_user_id()
    clean_ftp = max(80, min(600, int(new_ftp)))
    date_str = str(test_date or get_athlete_date(uid).isoformat())[:10]

    old_ftp = int(get_setting("athlete_ftp", 250, user_id=uid))
    set_setting("athlete_ftp", clean_ftp, user_id=uid)
    set_setting("ftp_last_tested_date", date_str, user_id=uid)
    set_setting("ftp_last_test_protocol", str(protocol or "20m_coggan"), user_id=uid)

    try:
        from app.services.power_profile_service import sync_spiderweb_goal_from_program
        sync_spiderweb_goal_from_program(user_id=uid)
    except Exception:
        pass

    return {
        "success": True,
        "old_ftp": old_ftp,
        "new_ftp": clean_ftp,
        "delta_watts": clean_ftp - old_ftp,
        "test_date": date_str,
        "protocol": protocol,
    }

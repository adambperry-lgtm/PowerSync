"""
3-Day WHOOP Recovery Forecast Backtest & Accuracy Analyzer
Replays PowerSync's rule-based 3-branch recovery heuristic AND a strictly
walk-forward Personalized Strain + HRV Mean-Reverting Candidate Model against
an athlete's historical `whoop_metrics` and `strava_activities` (scoped strictly
by user_id) to measure:
  - Day +1, Day +2, Day +3 MAE, RMSE, signed bias, WHOOP zone accuracy,
    and Forecast Confirmation rate (`is_forecast_valid_for_recovery`)
  - Workout prescription tier match rate (how often recovery errors would have
    changed the forecasted workout intensity zone)
  - Per-branch accuracy and predicted vs. actual recovery deltas
  - Honest benchmark comparisons (Candidate Model, Current Heuristic,
    Rolling 7d Mean, 50/50 Mean-Reversion, Naive Persistence)
  - 3x3 WHOOP zone confusion matrix (highlighting false-Green overreach risk)
  - Feature correlations with next-day recovery
"""

import datetime
import math
from typing import Dict, Any, List, Optional, Tuple

from app.database import (
    get_db_connection,
    get_current_user_id,
    get_setting,
    get_athlete_date,
)
from app.services.forecast_service import is_forecast_valid_for_recovery
from app.services.preferences_service import DEFAULT_COACHING_PREFERENCES
from app.services.review_coach import (
    predict_3day_recovery_heuristic,
    predict_3day_recovery_hybrid,
    get_activity_date_str,
)

WEEKDAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

BRANCH_META = {
    "trained_today_heavy": {
        "label": "Heavy Load Today",
        "rule": "Activity today & (strain ≥ 13.5 or suffer ≥ 60) → Live: −10..−12 drop (36–62%) + 21d baseline D+2/D+3",
    },
    "trained_yesterday_heavy": {
        "label": "Heavy Yesterday + Light Today",
        "rule": "Activity yesterday (strain ≥ 13.5 or suffer ≥ 40) & light today → Live: +26 rest (cap 82%) / +22 light (cap 76%)",
    },
    "standard": {
        "label": "Standard / Balanced",
        "rule": "All other days → Live: <8.5 easy rebound, 8.5–13.4 neutral mean-pull, ≥13.5 unlogged strain dip",
    },
}

def _recovery_zone(score: int) -> str:
    if score > 66:
        return "green"
    if score >= 34:
        return "yellow"
    return "red"


def _compute_origin_context(
    origin_dt: datetime.date,
    whoop_by_date: Dict[str, Dict[str, Any]],
    strava_by_date: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Computes strictly leak-free (<= origin_dt) personal baselines for day `origin_dt`:
      - 21-day personal rolling recovery mean
      - 7-day rolling recovery mean
      - 21-day mean WHOOP day strain & cycling duration
      - HRV % deviation vs. trailing 14-day HRV baseline
    """
    d_iso = origin_dt.isoformat()
    w_today = whoop_by_date.get(d_iso)
    if not w_today or w_today.get("recovery_score") is None:
        return None

    today_rec = float(w_today["recovery_score"])
    act_today = strava_by_date.get(d_iso)
    today_dur = float(act_today["moving_time_min"]) if act_today else 0.0

    recs_21: List[float] = []
    recs_7: List[float] = []
    strains_21: List[float] = []
    durs_21: List[float] = []
    hrvs_14: List[float] = []

    for lb in range(0, 21):
        prev_iso = (origin_dt - datetime.timedelta(days=lb)).isoformat()
        pw = whoop_by_date.get(prev_iso)
        pa = strava_by_date.get(prev_iso)
        if pw:
            if pw.get("recovery_score") is not None:
                val = float(pw["recovery_score"])
                recs_21.append(val)
                if lb < 7:
                    recs_7.append(val)
            if pw.get("day_strain") is not None:
                strains_21.append(float(pw["day_strain"]))
            if 0 < lb <= 14 and pw.get("hrv_rmssd") is not None:
                hrvs_14.append(float(pw["hrv_rmssd"]))
        durs_21.append(float(pa["moving_time_min"]) if pa else 0.0)

    personal_rec_mean = sum(recs_21) / len(recs_21) if recs_21 else today_rec
    rolling_7_mean = sum(recs_7) / len(recs_7) if recs_7 else today_rec
    mean_strain = sum(strains_21) / len(strains_21) if strains_21 else 10.5
    mean_dur = sum(durs_21) / len(durs_21) if durs_21 else 30.0

    if w_today.get("day_strain") is not None:
        today_strain = float(w_today["day_strain"])
    else:
        today_strain = min(18.0, 5.5 + (today_dur / 8.0)) if today_dur > 0 else mean_strain

    hrv_pct_diff = 0.0
    if w_today.get("hrv_rmssd") is not None and len(hrvs_14) >= 3:
        hrv_base = sum(hrvs_14) / len(hrvs_14)
        if hrv_base > 0:
            hrv_pct_diff = ((float(w_today["hrv_rmssd"]) - hrv_base) / hrv_base) * 100.0

    return {
        "personal_rec_mean": personal_rec_mean,
        "rolling_7_mean": rolling_7_mean,
        "mean_strain": mean_strain,
        "mean_dur": mean_dur,
        "today_strain": today_strain,
        "today_dur": today_dur,
        "hrv_pct_diff": hrv_pct_diff,
        "hrv_sample_count": len(hrvs_14),
    }


def predict_hybrid_candidate_3day(
    origin_dt: datetime.date,
    today_recovery: int,
    today_strain: float,
    workout_strain: float,
    is_today: bool,
    is_yesterday: bool,
    has_trained_today: bool,
    suffer_score: float,
    ctx: Dict[str, Any],
    weekly_schedule: Dict[str, Any],
    weekday_strain_hist: Dict[int, List[float]],
) -> List[int]:
    """Delegates directly to production `predict_3day_recovery_hybrid` for zero-drift backtesting."""
    out = predict_3day_recovery_hybrid(
        origin_dt=origin_dt,
        today_recovery=today_recovery,
        today_strain=today_strain,
        workout_strain=workout_strain,
        is_today=is_today,
        is_yesterday=is_yesterday,
        has_trained_today=has_trained_today,
        suffer_score=suffer_score,
        verdict="",
        personal_rec_mean=ctx["personal_rec_mean"],
        mean_strain=ctx["mean_strain"],
        hrv_pct_diff=ctx["hrv_pct_diff"],
        weekly_schedule=weekly_schedule,
        weekday_strain_hist=weekday_strain_hist,
    )
    return list(out["recoveries"])


def _workout_tier_for_day(
    target_date: datetime.date,
    recovery_score: int,
    weekly_schedule: Dict[str, Any],
) -> str:
    """
    Mirrors the workout-selection recovery thresholds in
    `build_preference_aligned_outlook_days` for a given weekday and recovery score.
    """
    w_key = WEEKDAY_KEYS[target_date.weekday()]
    sched = weekly_schedule.get(w_key) or DEFAULT_COACHING_PREFERENCES["weekly_schedule"].get(w_key, {})
    mode = sched.get("mode", "indoor_priority")
    is_default_rest = bool(sched.get("is_default_rest", False)) or (w_key == "saturday")

    if is_default_rest or mode == "rest_day":
        return "rest"

    if w_key == "sunday" or mode == "outdoor_or_long_indoor":
        return "endurance_full" if recovery_score >= 60 else "endurance_capped"

    if w_key in ("wednesday", "friday") or mode == "outdoor_priority":
        if recovery_score >= 66:
            return "sweet_spot"
        if recovery_score >= 45:
            return "tempo"
        return "active_recovery"

    # Monday, Tuesday, Thursday (indoor_priority)
    if recovery_score < 50:
        return "active_recovery"
    return "sweet_spot" if recovery_score >= 66 else "tempo"


def _pearson_r(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    if den_x <= 1e-9 or den_y <= 1e-9:
        return None
    return round(num / math.sqrt(den_x * den_y), 3)


def _summarize_records(
    records: List[Dict[str, Any]],
    pred_field: str = "predicted_recovery",
    zone_match_field: str = "zone_match",
    confirm_field: str = "forecast_confirmed",
    tier_match_field: str = "workout_tier_match",
) -> Dict[str, Any]:
    n = len(records)
    if n == 0:
        return {
            "count": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "zone_accuracy_pct": None,
            "confirmation_rate_pct": None,
            "within_10_pct": None,
            "workout_tier_match_pct": None,
            "avg_predicted": None,
            "avg_actual": None,
            "avg_pred_delta": None,
            "avg_actual_delta": None,
            "persistence_mae": None,
            "rolling_mean_mae": None,
            "mean_reversion_mae": None,
            "mae_vs_rolling_mean": None,
        }

    signed_errors = [r[pred_field] - r["actual_recovery"] for r in records]
    abs_errors = [abs(e) for e in signed_errors]
    sq_errors = [e ** 2 for e in signed_errors]

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)
    bias = sum(signed_errors) / n
    zone_acc = (sum(1 for r in records if r[zone_match_field]) / n) * 100.0
    confirm_rate = (sum(1 for r in records if r[confirm_field]) / n) * 100.0
    within_10 = (sum(1 for e in abs_errors if e <= 10) / n) * 100.0
    tier_match = (sum(1 for r in records if r[tier_match_field]) / n) * 100.0

    avg_pred = sum(r[pred_field] for r in records) / n
    avg_act = sum(r["actual_recovery"] for r in records) / n
    avg_pred_delta = sum(r[pred_field] - r["origin_recovery"] for r in records) / n
    avg_act_delta = sum(r["actual_recovery"] - r["origin_recovery"] for r in records) / n

    pers_mae = sum(abs(r["baseline_persistence"] - r["actual_recovery"]) for r in records) / n
    roll_mae = sum(abs(r["baseline_rolling_mean"] - r["actual_recovery"]) for r in records) / n
    mr_mae = sum(abs(r["baseline_mean_reversion"] - r["actual_recovery"]) for r in records) / n

    return {
        "count": n,
        "mae": round(mae, 1),
        "rmse": round(rmse, 1),
        "bias": round(bias, 1),
        "zone_accuracy_pct": round(zone_acc, 1),
        "confirmation_rate_pct": round(confirm_rate, 1),
        "within_10_pct": round(within_10, 1),
        "workout_tier_match_pct": round(tier_match, 1),
        "avg_predicted": round(avg_pred, 1),
        "avg_actual": round(avg_act, 1),
        "avg_pred_delta": round(avg_pred_delta, 1),
        "avg_actual_delta": round(avg_act_delta, 1),
        "persistence_mae": round(pers_mae, 1),
        "rolling_mean_mae": round(roll_mae, 1),
        "mean_reversion_mae": round(mr_mae, 1),
        "mae_vs_rolling_mean": round(mae - roll_mae, 1),
    }


def _build_confusion_matrix(
    records: List[Dict[str, Any]],
    pred_zone_field: str = "predicted_zone",
) -> Dict[str, Any]:
    zones = ["green", "yellow", "red"]
    matrix = {pz: {az: 0 for az in zones} for pz in zones}
    for r in records:
        pz = r[pred_zone_field]
        az = r["actual_zone"]
        if pz in matrix and az in matrix[pz]:
            matrix[pz][az] += 1

    pred_green_total = sum(matrix["green"].values())
    false_green = matrix["green"]["yellow"] + matrix["green"]["red"]
    false_green_to_red = matrix["green"]["red"]
    actual_red_total = sum(matrix[pz]["red"] for pz in zones)
    caught_red = matrix["red"]["red"]

    return {
        "matrix": matrix,
        "total": len(records),
        "predicted_green_total": pred_green_total,
        "false_green_count": false_green,
        "false_green_pct": round((false_green / pred_green_total) * 100.0, 1) if pred_green_total else 0.0,
        "false_green_to_red_count": false_green_to_red,
        "actual_red_total": actual_red_total,
        "caught_red_count": caught_red,
        "red_recall_pct": round((caught_red / actual_red_total) * 100.0, 1) if actual_red_total else None,
    }


def _build_baseline_comparison(
    by_horizon_records: Dict[int, List[Dict[str, Any]]],
    all_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    models = [
        ("candidate", "Calibrated Hybrid 3-Branch (Active Live)", "candidate_recovery"),
        ("heuristic", "Legacy 3-Branch Heuristic (v1)", "predicted_recovery"),
        ("rolling_mean", "Rolling 7-Day Personal Mean", "baseline_rolling_mean"),
        ("mean_reversion", "50/50 Mean-Reversion", "baseline_mean_reversion"),
        ("persistence", "Naive Persistence (Same as Today)", "baseline_persistence"),
    ]

    rows = []
    for key, label, field in models:
        entry: Dict[str, Any] = {"key": key, "label": label}
        for h in (1, 2, 3):
            recs = by_horizon_records[h]
            if recs:
                mae = sum(abs(r[field] - r["actual_recovery"]) for r in recs) / len(recs)
                bias = sum((r[field] - r["actual_recovery"]) for r in recs) / len(recs)
                z_acc = (
                    sum(1 for r in recs if _recovery_zone(int(round(r[field]))) == r["actual_zone"])
                    / len(recs)
                ) * 100.0
                conf = (
                    sum(
                        1
                        for r in recs
                        if is_forecast_valid_for_recovery(
                            {"projected_recovery": int(round(r[field])), "projected_zone": _recovery_zone(int(round(r[field])))},
                            r["actual_recovery"],
                        )[0]
                    )
                    / len(recs)
                ) * 100.0
                entry[f"day_{h}_mae"] = round(mae, 1)
                entry[f"day_{h}_bias"] = round(bias, 1)
                entry[f"day_{h}_zone_acc"] = round(z_acc, 1)
                entry[f"day_{h}_confirm_pct"] = round(conf, 1)
            else:
                entry[f"day_{h}_mae"] = None
                entry[f"day_{h}_bias"] = None
                entry[f"day_{h}_zone_acc"] = None
                entry[f"day_{h}_confirm_pct"] = None

        if all_records:
            overall_mae = sum(abs(r[field] - r["actual_recovery"]) for r in all_records) / len(all_records)
            overall_bias = sum((r[field] - r["actual_recovery"]) for r in all_records) / len(all_records)
            overall_z = (
                sum(1 for r in all_records if _recovery_zone(int(round(r[field]))) == r["actual_zone"])
                / len(all_records)
            ) * 100.0
            entry["overall_mae"] = round(overall_mae, 1)
            entry["overall_bias"] = round(overall_bias, 1)
            entry["overall_zone_acc"] = round(overall_z, 1)
        else:
            entry["overall_mae"] = None
            entry["overall_bias"] = None
            entry["overall_zone_acc"] = None

        rows.append(entry)
    return rows


def _generate_diagnostic_insights(
    d1_stats: Dict[str, Any],
    overall_stats: Dict[str, Any],
    by_branch: Dict[str, Any],
    d1_confusion: Dict[str, Any],
    correlations: List[Dict[str, Any]],
    candidate_d1: Optional[Dict[str, Any]] = None,
    candidate_overall: Optional[Dict[str, Any]] = None,
    candidate_d1_confusion: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    insights: List[Dict[str, str]] = []
    if not d1_stats or d1_stats.get("count", 0) < 3:
        insights.append({
            "severity": "info",
            "title": "Need More Historical WHOOP Days",
            "detail": "At least 5–14 days of consecutive WHOOP recovery records are recommended to reliably evaluate the 3-day forecast. Click 'Sync WHOOP History' to backfill older records.",
        })
        return insights

    active_d1 = candidate_d1 if (candidate_d1 and candidate_d1.get("mae") is not None) else d1_stats
    active_overall = candidate_overall if (candidate_overall and candidate_overall.get("mae") is not None) else overall_stats
    active_conf = candidate_d1_confusion or d1_confusion

    # 0. Active Live Hybrid vs. Legacy v1 Heuristic head-to-head
    if (
        candidate_d1
        and candidate_overall
        and candidate_d1.get("mae") is not None
        and d1_stats.get("mae") is not None
        and candidate_overall.get("mae") is not None
        and overall_stats.get("mae") is not None
    ):
        d1_delta = round(candidate_d1["mae"] - d1_stats["mae"], 1)
        all_delta = round(candidate_overall["mae"] - overall_stats["mae"], 1)
        z_heur = d1_stats.get("zone_accuracy_pct") or 0.0
        z_cand = candidate_d1.get("zone_accuracy_pct") or 0.0
        z_delta = round(z_cand - z_heur, 1)
        fg_heur = d1_confusion.get("false_green_pct", 0.0)
        fg_cand = (candidate_d1_confusion or {}).get("false_green_pct", 0.0)
        bias_verb = "reducing" if abs(candidate_d1["bias"]) < abs(d1_stats["bias"]) else "shifting"
        fg_verb = (
            "reducing" if fg_cand < fg_heur - 0.5
            else ("increasing" if fg_cand > fg_heur + 0.5 else "keeping")
        )
        beats_both = (d1_delta <= 0.0 and all_delta <= -0.5) or (d1_delta <= -0.5 and all_delta <= 0.0)
        if beats_both and z_delta >= -2.0:
            severity = "good"
            title = f"Active Hybrid Model Outperforms Legacy v1 (D+1 {d1_delta:+.1f} MAE, All 3d {all_delta:+.1f} MAE)"
        elif all_delta <= -0.5 or d1_delta <= -0.5:
            severity = "neutral"
            title = f"Active Hybrid Model vs. Legacy v1 (D+1 {d1_delta:+.1f} MAE, All 3d {all_delta:+.1f} MAE)"
        else:
            severity = "warning"
            title = f"Active Hybrid Model Trails Legacy v1 (D+1 {d1_delta:+.1f} MAE, All 3d {all_delta:+.1f} MAE)"

        insights.append({
            "severity": severity,
            "title": title,
            "detail": (
                f"Walk-forward out-of-sample: Day +1 MAE {candidate_d1['mae']} vs. {d1_stats['mae']} "
                f"(Zone Match {z_cand:.1f}% vs. {z_heur:.1f}%), All-3d MAE {candidate_overall['mae']} vs. {overall_stats['mae']}, "
                f"{bias_verb} Day +1 bias from {d1_stats['bias']:+.1f} to {candidate_d1['bias']:+.1f} "
                f"and {fg_verb} False-Green rate from {fg_heur:.0f}% to {fg_cand:.0f}%."
            ),
        })

    # 1. Active Live Model vs Rolling Mean baseline
    mae = active_d1["mae"]
    roll_mae = active_d1["rolling_mean_mae"]
    if mae is not None and roll_mae is not None:
        diff = round(mae - roll_mae, 1)
        if diff > 1.5:
            insights.append({
                "severity": "warning",
                "title": f"Active Model Trails Personal Baseline by +{diff} pts MAE",
                "detail": (
                    f"On Day +1 predictions (n={active_d1['count']}), the active Hybrid model averages {mae} pts error vs. "
                    f"{roll_mae} pts for simply predicting your rolling 7-day average recovery."
                ),
            })
        elif diff < -1.5:
            insights.append({
                "severity": "good",
                "title": f"Active Hybrid Model Beats Personal Baseline by {abs(diff)} pts MAE",
                "detail": (
                    f"On Day +1 predictions (n={active_d1['count']}), the active Hybrid model averages {mae} pts error vs. "
                    f"{roll_mae} pts for your rolling 7-day personal mean (All-3d MAE {active_overall['mae']} vs. {active_overall['rolling_mean_mae']})."
                ),
            })
        else:
            insights.append({
                "severity": "neutral",
                "title": "Active Hybrid Model Performs Roughly On Par with Rolling Mean",
                "detail": (
                    f"Day +1 MAE is {mae} pts compared to {roll_mae} pts for your rolling 7-day average "
                    f"(difference {diff:+.1f} pts across {active_d1['count']} days)."
                ),
            })

    # 2. Systematic bias check (Active Live Model)
    bias = active_d1["bias"]
    if bias is not None and abs(bias) >= 4.0:
        direction = "over-predicts (too optimistic)" if bias > 0 else "under-predicts (too conservative)"
        insights.append({
            "severity": "warning",
            "title": f"Active Model Systematic Bias: {bias:+.1f} pts on Day +1",
            "detail": (
                f"The active Hybrid model consistently {direction} your next-day WHOOP recovery "
                f"(avg predicted {active_d1['avg_predicted']}% vs. actual {active_d1['avg_actual']}%)."
            ),
        })

    # 3. False-Green overreach check (Active Live Model)
    fg_count = active_conf.get("false_green_count", 0)
    fg_pct = active_conf.get("false_green_pct", 0.0)
    pred_green = active_conf.get("predicted_green_total", 0)
    if pred_green >= 3 and fg_pct >= 30.0:
        insights.append({
            "severity": "warning",
            "title": f"Active Model False-Green Rate: {fg_pct:.0f}% ({fg_count}/{pred_green} Green Calls)",
            "detail": (
                f"When the forecast projected Green (>66%) for tomorrow, actual WHOOP recovery landed in Yellow or Red "
                f"{fg_count} times ({active_conf.get('false_green_to_red_count', 0)} Red)."
            ),
        })

    # 4. Largest-error regime (Active Live Model)
    branch_candidates = [
        (b_key, b_data)
        for b_key, b_data in by_branch.items()
        if b_data.get("candidate_day_1", {}).get("count", 0) >= 3 and b_data.get("candidate_day_1", {}).get("mae") is not None
    ]
    if branch_candidates:
        _, worst = max(branch_candidates, key=lambda kv: kv[1]["candidate_day_1"]["mae"])
        wd1 = worst["candidate_day_1"]
        insights.append({
            "severity": "info",
            "title": f"Largest Error Regime (Active Model): {worst['label']} ({wd1['mae']} MAE)",
            "detail": (
                f"Triggered {wd1['count']} times: active Hybrid projected avg {wd1['avg_pred_delta']:+.1f} pts change next day, "
                f"while your actual WHOOP recovery changed by {wd1['avg_actual_delta']:+.1f} pts (bias {wd1['bias']:+.1f})."
            ),
        })

    # 5. Strongest empirical signal for next-day recovery
    valid_corrs = [c for c in correlations if c.get("r_next_day_recovery") is not None]
    if valid_corrs:
        strongest = max(valid_corrs, key=lambda c: abs(c["r_next_day_recovery"]))
        r_val = strongest["r_next_day_recovery"]
        if abs(r_val) >= 0.15:
            sign_word = "positively" if r_val > 0 else "negatively"
            insights.append({
                "severity": "good" if abs(r_val) >= 0.3 else "info",
                "title": f"Strongest Predictor of Next-Day Recovery: {strongest['label']} (r = {r_val:+.2f})",
                "detail": (
                    f"Across {strongest['sample_count']} paired days, {strongest['label']} correlates {sign_word} "
                    f"with tomorrow's WHOOP recovery (delta correlation r = {strongest['r_next_day_delta']:+.2f})."
                ),
            })

    return insights


def run_recovery_forecast_backtest(
    user_id: Optional[str] = None,
    days: int = 90,
) -> Dict[str, Any]:
    """
    Walk-forward historical backtest comparing:
      1. PowerSync's current 3-branch WHOOP recovery heuristic
      2. A strictly out-of-sample Personalized Strain + HRV Mean-Reverting Candidate Model
      3. Standard statistical baselines (Rolling 7d Mean, 50/50 Mean-Reversion, Persistence)
    Strictly isolated to `user_id`.
    """
    uid = user_id or get_current_user_id()
    days = max(7, min(365, int(days or 90)))
    today_dt = get_athlete_date(user_id=uid)
    cutoff_dt = today_dt - datetime.timedelta(days=days)
    # Fetch extra prior history for leak-free rolling baselines and walk-forward candidate warmup
    fetch_start_iso = (cutoff_dt - datetime.timedelta(days=45)).isoformat()

    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        """
        SELECT date, recovery_score, hrv_rmssd, resting_heart_rate,
               sleep_performance, sleep_duration_hours, day_strain
        FROM whoop_metrics
        WHERE user_id = ? AND date >= ?
        ORDER BY date ASC
        """,
        (uid, fetch_start_iso),
    )
    whoop_rows = [dict(r) for r in c.fetchall()]

    c.execute(
        """
        SELECT id, name, sport_type, start_date, moving_time_sec,
               suffer_score, weighted_average_watts, average_watts, kilojoules, raw_json
        FROM strava_activities
        WHERE user_id = ? AND substr(start_date, 1, 10) >= ?
        ORDER BY start_date ASC
        """,
        (uid, (cutoff_dt - datetime.timedelta(days=46)).isoformat()),
    )
    strava_rows = [dict(r) for r in c.fetchall()]
    conn.close()

    # Index WHOOP by ISO date
    whoop_by_date: Dict[str, Dict[str, Any]] = {}
    for row in whoop_rows:
        d_str = str(row.get("date") or "")[:10]
        if d_str:
            whoop_by_date[d_str] = row

    # Group Strava activities by athlete-local calendar date
    strava_by_date: Dict[str, Dict[str, Any]] = {}
    for act in strava_rows:
        d_str = get_activity_date_str(act, user_id=uid)
        if not d_str:
            continue
        bucket = strava_by_date.setdefault(
            d_str,
            {"count": 0, "suffer_score": 0.0, "moving_time_min": 0.0, "kilojoules": 0.0},
        )
        bucket["count"] += 1
        bucket["suffer_score"] += float(act.get("suffer_score") or 0.0)
        bucket["moving_time_min"] += float(act.get("moving_time_sec") or 0.0) / 60.0
        bucket["kilojoules"] += float(act.get("kilojoules") or 0.0)

    # Load user's weekly schedule preferences for workout-tier impact analysis
    stored_prefs = get_setting("coaching_preferences", None, user_id=uid)
    weekly_schedule = (
        stored_prefs.get("weekly_schedule", DEFAULT_COACHING_PREFERENCES["weekly_schedule"])
        if isinstance(stored_prefs, dict)
        else DEFAULT_COACHING_PREFERENCES["weekly_schedule"]
    )

    valid_whoop_dates = sorted(
        d for d, w in whoop_by_date.items() if w.get("recovery_score") is not None
    )

    # Precompute strictly leak-free per-day candidate contexts (<= origin_dt)
    origin_ctx_by_date: Dict[str, Dict[str, Any]] = {}
    for d_iso in valid_whoop_dates:
        try:
            odt = datetime.date.fromisoformat(d_iso)
        except ValueError:
            continue
        ctx = _compute_origin_context(odt, whoop_by_date, strava_by_date)
        if ctx:
            origin_ctx_by_date[d_iso] = ctx

    cutoff_iso = cutoff_dt.isoformat()
    window_whoop_dates = [d for d in valid_whoop_dates if d >= cutoff_iso]

    by_horizon_records: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}
    branch_records: Dict[str, Dict[int, List[Dict[str, Any]]]] = {
        b: {1: [], 2: [], 3: []} for b in BRANCH_META
    }
    branch_trigger_counts: Dict[str, int] = {b: 0 for b in BRANCH_META}

    # Feature correlation accumulators (origin day t features vs day t+1 actual recovery)
    feature_pairs: Dict[str, List[Tuple[float, float, float]]] = {
        "today_recovery": [],
        "day_strain": [],
        "hrv_rmssd": [],
        "hrv_vs_14d_baseline": [],
        "resting_heart_rate": [],
        "sleep_performance": [],
        "sleep_duration_hours": [],
        "strava_suffer_score": [],
        "strava_duration_min": [],
    }

    # Maintain running weekday strain histories strictly <= origin_dt for D+2/D+3 propagation
    weekday_strain_hist: Dict[int, List[float]] = {wd: [] for wd in range(7)}
    for pre_iso in valid_whoop_dates:
        if pre_iso >= cutoff_iso:
            break
        try:
            pdt = datetime.date.fromisoformat(pre_iso)
        except ValueError:
            continue
        pw = whoop_by_date[pre_iso]
        if pw.get("day_strain") is not None:
            weekday_strain_hist[pdt.weekday()].append(float(pw["day_strain"]))

    timeline: List[Dict[str, Any]] = []
    origin_days_evaluated = 0
    strava_matched_days = 0
    latest_ctx: Optional[Dict[str, Any]] = None

    for d_iso in window_whoop_dates:
        try:
            origin_dt = datetime.date.fromisoformat(d_iso)
        except ValueError:
            continue

        w_today = whoop_by_date[d_iso]
        today_rec = int(round(float(w_today["recovery_score"])))
        today_strain = float(w_today.get("day_strain") or 0.0)

        yest_iso = (origin_dt - datetime.timedelta(days=1)).isoformat()
        act_today = strava_by_date.get(d_iso)
        act_yest = strava_by_date.get(yest_iso)
        has_trained_today = bool(act_today and act_today["count"] > 0)
        if has_trained_today:
            strava_matched_days += 1

        # Update weekday strain history with day `origin_dt` (observed today, <= origin_dt)
        if w_today.get("day_strain") is not None:
            weekday_strain_hist[origin_dt.weekday()].append(float(w_today["day_strain"]))

        # Mirror `build_daily_review_and_outlook_local` activity-context resolution
        if has_trained_today:
            is_today = True
            is_yesterday = False
            workout_strain = today_strain
            suffer_score = act_today["suffer_score"]
        elif act_yest and act_yest["count"] > 0:
            is_today = False
            is_yesterday = True
            w_yest = whoop_by_date.get(yest_iso)
            workout_strain = float(w_yest.get("day_strain") or 0.0) if w_yest else 12.0
            suffer_score = act_yest["suffer_score"]
        else:
            is_today = False
            is_yesterday = False
            workout_strain = 0.0
            suffer_score = 0.0

        pred_out = predict_3day_recovery_heuristic(
            today_recovery=today_rec,
            today_strain=today_strain,
            workout_strain=workout_strain,
            is_today=is_today,
            is_yesterday=is_yesterday,
            has_trained_today=has_trained_today,
            suffer_score=suffer_score,
            verdict="",
        )
        branch = pred_out["branch"]
        preds = pred_out["recoveries"]

        # Calibrated Hybrid 3-Branch + Personal Baseline Candidate (strictly <= origin_dt)
        ctx = origin_ctx_by_date.get(d_iso)
        if ctx:
            cand_preds = predict_hybrid_candidate_3day(
                origin_dt=origin_dt,
                today_recovery=today_rec,
                today_strain=today_strain,
                workout_strain=workout_strain,
                is_today=is_today,
                is_yesterday=is_yesterday,
                has_trained_today=has_trained_today,
                suffer_score=suffer_score,
                ctx=ctx,
                weekly_schedule=weekly_schedule,
                weekday_strain_hist=weekday_strain_hist,
            )
            latest_ctx = ctx
        else:
            cand_preds = list(preds)

        # Leak-free trailing 7-day personal recovery mean & 14-day HRV baseline
        trailing_recs = []
        trailing_hrvs = []
        for lookback in range(0, 14):
            prev_iso = (origin_dt - datetime.timedelta(days=lookback)).isoformat()
            prev_w = whoop_by_date.get(prev_iso)
            if not prev_w:
                continue
            if lookback < 7 and prev_w.get("recovery_score") is not None:
                trailing_recs.append(float(prev_w["recovery_score"]))
            if lookback > 0 and prev_w.get("hrv_rmssd") is not None:
                trailing_hrvs.append(float(prev_w["hrv_rmssd"]))

        rolling_mean = int(round(sum(trailing_recs) / len(trailing_recs))) if trailing_recs else today_rec
        mean_reversion = int(round(0.5 * today_rec + 0.5 * rolling_mean))

        any_horizon_matched = False
        for h in (1, 2, 3):
            target_dt = origin_dt + datetime.timedelta(days=h)
            target_iso = target_dt.isoformat()
            w_target = whoop_by_date.get(target_iso)
            if not w_target or w_target.get("recovery_score") is None:
                continue

            any_horizon_matched = True
            actual_rec = int(round(float(w_target["recovery_score"])))
            actual_zone = _recovery_zone(actual_rec)
            actual_tier = _workout_tier_for_day(target_dt, actual_rec, weekly_schedule)

            # Current 3-Branch Heuristic evaluation
            pred_rec = int(preds[h - 1])
            err = pred_rec - actual_rec
            pred_zone = _recovery_zone(pred_rec)
            zone_match = pred_zone == actual_zone
            confirmed, _ = is_forecast_valid_for_recovery(
                {"projected_recovery": pred_rec, "projected_zone": pred_zone},
                actual_rec,
            )
            pred_tier = _workout_tier_for_day(target_dt, pred_rec, weekly_schedule)
            tier_match = pred_tier == actual_tier

            # Candidate Model evaluation
            cand_rec = int(cand_preds[h - 1])
            cand_err = cand_rec - actual_rec
            cand_zone = _recovery_zone(cand_rec)
            cand_zone_match = cand_zone == actual_zone
            cand_confirmed, _ = is_forecast_valid_for_recovery(
                {"projected_recovery": cand_rec, "projected_zone": cand_zone},
                actual_rec,
            )
            cand_tier = _workout_tier_for_day(target_dt, cand_rec, weekly_schedule)
            cand_tier_match = cand_tier == actual_tier

            rec_item = {
                "origin_date": d_iso,
                "target_date": target_iso,
                "horizon": h,
                "branch": branch,
                "branch_label": pred_out["branch_label"],
                "origin_recovery": today_rec,
                "origin_strain": round(today_strain, 1),
                "origin_suffer_score": round(suffer_score, 1),
                "predicted_recovery": pred_rec,
                "actual_recovery": actual_rec,
                "error": err,
                "abs_error": abs(err),
                "predicted_zone": pred_zone,
                "actual_zone": actual_zone,
                "zone_match": zone_match,
                "forecast_confirmed": confirmed,
                "predicted_workout_tier": pred_tier,
                "actual_workout_tier": actual_tier,
                "workout_tier_match": tier_match,
                "candidate_recovery": cand_rec,
                "candidate_error": cand_err,
                "candidate_abs_error": abs(cand_err),
                "candidate_zone": cand_zone,
                "candidate_zone_match": cand_zone_match,
                "candidate_confirmed": cand_confirmed,
                "candidate_workout_tier": cand_tier,
                "candidate_workout_tier_match": cand_tier_match,
                "baseline_persistence": today_rec,
                "baseline_rolling_mean": rolling_mean,
                "baseline_mean_reversion": mean_reversion,
            }

            by_horizon_records[h].append(rec_item)
            branch_records[branch][h].append(rec_item)

            if h == 1:
                timeline.append(rec_item)
                # Accumulate correlations with Day +1 actual recovery & delta
                delta_d1 = float(actual_rec - today_rec)
                act_f = float(actual_rec)
                feature_pairs["today_recovery"].append((float(today_rec), act_f, delta_d1))
                if w_today.get("day_strain") is not None:
                    feature_pairs["day_strain"].append((float(w_today["day_strain"]), act_f, delta_d1))
                if w_today.get("hrv_rmssd") is not None:
                    hrv_now = float(w_today["hrv_rmssd"])
                    feature_pairs["hrv_rmssd"].append((hrv_now, act_f, delta_d1))
                    if len(trailing_hrvs) >= 3:
                        hrv_base = sum(trailing_hrvs) / len(trailing_hrvs)
                        if hrv_base > 0:
                            hrv_pct_diff = ((hrv_now - hrv_base) / hrv_base) * 100.0
                            feature_pairs["hrv_vs_14d_baseline"].append((hrv_pct_diff, act_f, delta_d1))
                if w_today.get("resting_heart_rate") is not None:
                    feature_pairs["resting_heart_rate"].append((float(w_today["resting_heart_rate"]), act_f, delta_d1))
                if w_today.get("sleep_performance") is not None:
                    feature_pairs["sleep_performance"].append((float(w_today["sleep_performance"]), act_f, delta_d1))
                if w_today.get("sleep_duration_hours") is not None:
                    feature_pairs["sleep_duration_hours"].append((float(w_today["sleep_duration_hours"]), act_f, delta_d1))
                today_suffer = act_today["suffer_score"] if act_today else 0.0
                today_dur = act_today["moving_time_min"] if act_today else 0.0
                feature_pairs["strava_suffer_score"].append((today_suffer, act_f, delta_d1))
                feature_pairs["strava_duration_min"].append((today_dur, act_f, delta_d1))

        if any_horizon_matched:
            origin_days_evaluated += 1
            branch_trigger_counts[branch] += 1

    all_records = by_horizon_records[1] + by_horizon_records[2] + by_horizon_records[3]

    by_horizon = {
        "day_1": _summarize_records(by_horizon_records[1]),
        "day_2": _summarize_records(by_horizon_records[2]),
        "day_3": _summarize_records(by_horizon_records[3]),
        "overall": _summarize_records(all_records),
    }

    candidate_by_horizon = {
        "day_1": _summarize_records(
            by_horizon_records[1],
            pred_field="candidate_recovery",
            zone_match_field="candidate_zone_match",
            confirm_field="candidate_confirmed",
            tier_match_field="candidate_workout_tier_match",
        ),
        "day_2": _summarize_records(
            by_horizon_records[2],
            pred_field="candidate_recovery",
            zone_match_field="candidate_zone_match",
            confirm_field="candidate_confirmed",
            tier_match_field="candidate_workout_tier_match",
        ),
        "day_3": _summarize_records(
            by_horizon_records[3],
            pred_field="candidate_recovery",
            zone_match_field="candidate_zone_match",
            confirm_field="candidate_confirmed",
            tier_match_field="candidate_workout_tier_match",
        ),
        "overall": _summarize_records(
            all_records,
            pred_field="candidate_recovery",
            zone_match_field="candidate_zone_match",
            confirm_field="candidate_confirmed",
            tier_match_field="candidate_workout_tier_match",
        ),
    }

    by_branch: Dict[str, Any] = {}
    for b_key, meta in BRANCH_META.items():
        b_all = branch_records[b_key][1] + branch_records[b_key][2] + branch_records[b_key][3]
        trig = branch_trigger_counts[b_key]
        by_branch[b_key] = {
            "key": b_key,
            "label": meta["label"],
            "rule": meta["rule"],
            "trigger_count": trig,
            "trigger_share_pct": round((trig / origin_days_evaluated) * 100.0, 1) if origin_days_evaluated else 0.0,
            "day_1": _summarize_records(branch_records[b_key][1]),
            "day_2": _summarize_records(branch_records[b_key][2]),
            "day_3": _summarize_records(branch_records[b_key][3]),
            "overall": _summarize_records(b_all),
            "candidate_day_1": _summarize_records(
                branch_records[b_key][1],
                pred_field="candidate_recovery",
                zone_match_field="candidate_zone_match",
                confirm_field="candidate_confirmed",
                tier_match_field="candidate_workout_tier_match",
            ),
            "candidate_overall": _summarize_records(
                b_all,
                pred_field="candidate_recovery",
                zone_match_field="candidate_zone_match",
                confirm_field="candidate_confirmed",
                tier_match_field="candidate_workout_tier_match",
            ),
        }

    baselines = _build_baseline_comparison(by_horizon_records, all_records)
    confusion_d1 = _build_confusion_matrix(by_horizon_records[1], pred_zone_field="predicted_zone")
    confusion_overall = _build_confusion_matrix(all_records, pred_zone_field="predicted_zone")
    candidate_confusion_d1 = _build_confusion_matrix(by_horizon_records[1], pred_zone_field="candidate_zone")
    candidate_confusion_overall = _build_confusion_matrix(all_records, pred_zone_field="candidate_zone")

    def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None:
            return None
        return round(a - b, 1)

    candidate_vs_heuristic = {
        "day_1_mae_delta": _diff(candidate_by_horizon["day_1"]["mae"], by_horizon["day_1"]["mae"]),
        "day_2_mae_delta": _diff(candidate_by_horizon["day_2"]["mae"], by_horizon["day_2"]["mae"]),
        "day_3_mae_delta": _diff(candidate_by_horizon["day_3"]["mae"], by_horizon["day_3"]["mae"]),
        "overall_mae_delta": _diff(candidate_by_horizon["overall"]["mae"], by_horizon["overall"]["mae"]),
        "day_1_zone_acc_delta": _diff(candidate_by_horizon["day_1"]["zone_accuracy_pct"], by_horizon["day_1"]["zone_accuracy_pct"]),
        "day_1_confirm_delta": _diff(candidate_by_horizon["day_1"]["confirmation_rate_pct"], by_horizon["day_1"]["confirmation_rate_pct"]),
        "day_1_tier_match_delta": _diff(candidate_by_horizon["day_1"]["workout_tier_match_pct"], by_horizon["day_1"]["workout_tier_match_pct"]),
        "day_1_false_green_delta": _diff(candidate_confusion_d1["false_green_pct"], confusion_d1["false_green_pct"]),
    }

    learned_profile = {
        "model_type": "hybrid_3branch_personal_baseline",
        "training_samples": origin_days_evaluated,
        "personal_baseline_recovery": round(latest_ctx["personal_rec_mean"], 1) if latest_ctx else None,
        "personal_baseline_strain": round(latest_ctx["mean_strain"], 1) if latest_ctx else None,
        "personal_baseline_duration_min": round(latest_ctx["mean_dur"], 0) if latest_ctx else None,
        "heavy_drop_range": "-10 to -12 pts (floor 36%)",
        "full_rest_cap": "82% (<5 strain) / 76% light",
        "standard_split": "<8.5 easy rebound • 8.5–13.4 neutral • ≥13.5 dip",
        "horizon_decay": "D+2/D+3 revert to 21d mean + weekday load",
    }

    feature_labels = {
        "today_recovery": "Today's WHOOP Recovery (%)",
        "day_strain": "Today's WHOOP Day Strain",
        "hrv_rmssd": "Today's HRV (ms)",
        "hrv_vs_14d_baseline": "HRV vs. 14d Baseline (%)",
        "resting_heart_rate": "Resting Heart Rate (bpm)",
        "sleep_performance": "Sleep Performance (%)",
        "sleep_duration_hours": "Sleep Duration (hrs)",
        "strava_suffer_score": "Strava Relative Effort",
        "strava_duration_min": "Strava Training Duration (min)",
    }
    feature_correlations: List[Dict[str, Any]] = []
    for f_key, label in feature_labels.items():
        triples = feature_pairs[f_key]
        xs = [t[0] for t in triples]
        ys_rec = [t[1] for t in triples]
        ys_delta = [t[2] for t in triples]
        r_rec = _pearson_r(xs, ys_rec)
        r_delta = _pearson_r(xs, ys_delta)
        feature_correlations.append({
            "key": f_key,
            "label": label,
            "sample_count": len(triples),
            "r_next_day_recovery": r_rec,
            "r_next_day_delta": r_delta,
        })
    feature_correlations.sort(
        key=lambda item: abs(item["r_next_day_recovery"]) if item["r_next_day_recovery"] is not None else -1.0,
        reverse=True,
    )

    insights = _generate_diagnostic_insights(
        d1_stats=by_horizon["day_1"],
        overall_stats=by_horizon["overall"],
        by_branch=by_branch,
        d1_confusion=confusion_d1,
        correlations=feature_correlations,
        candidate_d1=candidate_by_horizon["day_1"],
        candidate_overall=candidate_by_horizon["overall"],
        candidate_d1_confusion=candidate_confusion_d1,
    )

    d1_count = candidate_by_horizon["day_1"]["count"]
    return {
        "success": True,
        "lookback_days": days,
        "active_model_name": "Calibrated Hybrid 3-Branch + Personal Baseline",
        "data_coverage": {
            "whoop_days_in_window": len(window_whoop_dates),
            "origin_days_evaluated": origin_days_evaluated,
            "day_1_pairs": d1_count,
            "total_prediction_pairs": len(all_records),
            "strava_matched_days": strava_matched_days,
            "start_date": window_whoop_dates[0] if window_whoop_dates else None,
            "end_date": window_whoop_dates[-1] if window_whoop_dates else None,
            "sufficient_data": d1_count >= 5,
        },
        "summary": {
            "day_1_mae": candidate_by_horizon["day_1"]["mae"],
            "day_1_rmse": candidate_by_horizon["day_1"]["rmse"],
            "day_1_bias": candidate_by_horizon["day_1"]["bias"],
            "day_1_zone_accuracy_pct": candidate_by_horizon["day_1"]["zone_accuracy_pct"],
            "day_1_confirmation_rate_pct": candidate_by_horizon["day_1"]["confirmation_rate_pct"],
            "day_1_workout_tier_match_pct": candidate_by_horizon["day_1"]["workout_tier_match_pct"],
            "day_1_rolling_mean_mae": candidate_by_horizon["day_1"]["rolling_mean_mae"],
            "day_1_mae_vs_baseline": candidate_by_horizon["day_1"]["mae_vs_rolling_mean"],
            "day_1_false_green_pct": candidate_confusion_d1["false_green_pct"],
            "overall_mae": candidate_by_horizon["overall"]["mae"],
            "overall_zone_accuracy_pct": candidate_by_horizon["overall"]["zone_accuracy_pct"],
            "overall_confirmation_rate_pct": candidate_by_horizon["overall"]["confirmation_rate_pct"],
        },
        "legacy_summary": {
            "day_1_mae": by_horizon["day_1"]["mae"],
            "day_1_rmse": by_horizon["day_1"]["rmse"],
            "day_1_bias": by_horizon["day_1"]["bias"],
            "day_1_zone_accuracy_pct": by_horizon["day_1"]["zone_accuracy_pct"],
            "day_1_confirmation_rate_pct": by_horizon["day_1"]["confirmation_rate_pct"],
            "day_1_workout_tier_match_pct": by_horizon["day_1"]["workout_tier_match_pct"],
            "day_1_false_green_pct": confusion_d1["false_green_pct"],
            "overall_mae": by_horizon["overall"]["mae"],
        },
        "candidate_model": {
            "is_active": True,
            "name": "Calibrated Hybrid 3-Branch + Personal Baseline",
            "description": "Active live forecast model: calibrated -10..-12 heavy drops (36% floor), full-rest rebounds (up to 82%), strain-gated Standard days, and personal 21d baseline mean-reversion on Days +2/+3.",
            "by_horizon": candidate_by_horizon,
            "confusion_matrix": {
                "day_1": candidate_confusion_d1,
                "overall": candidate_confusion_overall,
            },
            "vs_heuristic": candidate_vs_heuristic,
            "learned_profile": learned_profile,
        },
        "by_horizon": by_horizon,
        "by_branch": by_branch,
        "baselines": baselines,
        "confusion_matrix": {
            "day_1": confusion_d1,
            "overall": confusion_overall,
        },
        "feature_correlations": feature_correlations,
        "insights": insights,
        "timeline": timeline[-90:],
    }

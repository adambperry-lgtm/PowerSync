import json
from unittest.mock import MagicMock, patch

from app.database import get_db_connection, init_db, set_setting
from app.routers.power import get_spiderweb_streams_status_endpoint
from app.services.power_profile_service import calculate_activity_peak_powers
from app.services.strava_service import (
    compute_mmp_peaks_from_streams,
    get_cached_mmp_peaks_map,
    get_strava_stream_backfill_status,
    save_activity_mmp_peaks,
    sync_missing_power_streams,
)


def _ensure_user(uid: str):
    init_db()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (id, email, name, picture) VALUES (?, ?, ?, '')",
        (uid, f"{uid}@example.com", uid),
    )
    conn.commit()
    conn.close()


def _insert_activity(uid: str, act_id: str, start_date: str = "2026-11-20T10:00:00Z", avg_w: float = 200.0):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO strava_activities (
            user_id, id, name, sport_type, start_date, moving_time_sec,
            distance_meters, total_elevation_gain, average_watts, weighted_average_watts,
            average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
        ) VALUES (?, ?, ?, 'Ride', ?, 3600, 30000, 300, ?, ?, 145, 175, 60, 720, '{}')
        """,
        (uid, act_id, f"Ride {act_id}", start_date, avg_w, avg_w + 15.0),
    )
    conn.commit()
    conn.close()


def test_compute_mmp_peaks_exact_1hz_and_pause_zero_padding():
    # 100s at 200W, then a 10s sprint at 600W, then 100s pause (time gap), then 1200s at 250W
    time_arr = list(range(0, 110)) + list(range(210, 1410))
    watts_arr = [200] * 100 + [600] * 10 + [250] * 1200

    peaks = compute_mmp_peaks_from_streams({"time": {"data": time_arr}, "watts": {"data": watts_arr}})
    assert peaks is not None
    assert peaks["5s"] == 600
    assert peaks["30s"] >= 333  # 10*600 + 20*200 = 10000 / 30 = 333
    assert peaks["20m"] == 250
    assert peaks["60m"] == 0  # total span < 3600s
    # Monotonicity
    assert peaks["5s"] >= peaks["30s"] >= peaks["1m"] >= peaks["5m"] >= peaks["20m"]


def test_calculate_activity_peak_powers_prefers_cached_mmp_streams():
    act = {
        "id": "12345",
        "sport_type": "Ride",
        "name": "Easy Z2 + 1m Sprint",
        "moving_time_sec": 3600,
        "average_watts": 165.0,
        "weighted_average_watts": 175.0,
    }
    est = calculate_activity_peak_powers(act, ftp=250)
    exact = calculate_activity_peak_powers(
        act,
        ftp=250,
        mmp_peaks={
            "has_power_stream": True,
            "5s": 980,
            "30s": 620,
            "1m": 490,
            "5m": 340,
            "20m": 265,
            "60m": 210,
        },
    )
    assert exact["5s"] == 980
    assert exact["1m"] == 490
    assert exact["5m"] == 340
    assert exact["20m"] == 265
    assert exact["1m"] != est["1m"]


def test_sync_missing_power_streams_local_cache_and_rate_limit_and_isolation():
    uid_a = "usr_test_mmp_a"
    uid_b = "usr_test_mmp_b"
    _ensure_user(uid_a)
    _ensure_user(uid_b)

    # Clean up prior test rows
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM strava_activities WHERE user_id IN (?, ?)", (uid_a, uid_b))
    c.execute("DELETE FROM strava_activity_streams WHERE user_id IN (?, ?)", (uid_a, uid_b))
    c.execute("DELETE FROM strava_activity_mmp_peaks WHERE user_id IN (?, ?)", (uid_a, uid_b))
    conn.commit()
    conn.close()

    _insert_activity(uid_a, "10001", "2026-11-22T10:00:00Z")
    _insert_activity(uid_a, "10002", "2026-11-21T10:00:00Z")
    _insert_activity(uid_b, "20001", "2026-11-22T10:00:00Z")

    # Pre-seed strava_activity_streams for 10002 -> should be computed locally with 0 network calls
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO strava_activity_streams (user_id, activity_id, streams_json) VALUES (?, ?, ?)",
        (uid_a, "10002", json.dumps({"time": list(range(120)), "watts": [300] * 120})),
    )
    conn.commit()
    conn.close()

    set_setting("strava_tokens", {"access_token": "valid_test_token_12345"}, user_id=uid_a)
    set_setting("strava_stream_backfill_status", {}, user_id=uid_a)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"time": {"data": list(range(60))}, "watts": {"data": [450] * 60}}
    mock_resp.headers = {"X-ReadRateLimit-Usage": "175,500", "X-ReadRateLimit-Limit": "200,2000"}

    with patch("app.services.strava_service.requests.get", return_value=mock_resp) as mock_get:
        res = sync_missing_power_streams(user_id=uid_a, max_per_run=10)

    assert mock_get.call_count == 1  # Only 10001 hit network; 10002 used local cache
    assert res["total_eligible"] == 2
    assert res["synced_count"] == 2
    assert res["stream_backed_count"] == 2
    assert res["remaining_count"] == 0

    mmp_a = get_cached_mmp_peaks_map(uid_a)
    mmp_b = get_cached_mmp_peaks_map(uid_b)
    assert mmp_a["10001"]["1m"] == 450
    assert mmp_a["10002"]["1m"] == 300
    assert "10001" not in mmp_b
    assert get_strava_stream_backfill_status(uid_b)["synced_count"] == 0


def test_spiderweb_streams_status_endpoint_isolated():
    uid = "usr_test_mmp_ep"
    _ensure_user(uid)
    save_activity_mmp_peaks(uid, "99999", {"5s": 800, "30s": 500, "1m": 400, "5m": 310, "20m": 260, "60m": 220, "sample_count": 3600})
    _insert_activity(uid, "99999", "2026-11-23T10:00:00Z")

    mock_req = MagicMock()
    with patch("app.routers.power.get_current_user_id", return_value=uid):
        data = get_spiderweb_streams_status_endpoint(mock_req)
    assert data["total_eligible"] >= 1
    assert data["synced_count"] >= 1


def test_12_axis_power_skills_spiderweb_profile():
    from app.services.power_profile_service import get_power_spiderweb_profile, RADAR_DURATIONS

    # 3600s ride with a 15s sprint at 700W, 2m effort at 380W, and steady 240W
    watts_arr = [700] * 15 + [380] * 120 + [240] * 3465
    peaks = compute_mmp_peaks_from_streams({"time": {"data": list(range(3600))}, "watts": {"data": watts_arr}})
    assert peaks is not None
    assert peaks["15s"] == 700
    assert peaks["2m"] >= 380
    assert peaks["30m"] >= 240
    assert peaks["60m"] >= 240

    uid = "usr_test_mmp_12ax"
    _ensure_user(uid)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM strava_activities WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM strava_activity_mmp_peaks WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()

    _insert_activity(uid, "88801", "2026-11-24T10:00:00Z", avg_w=245.0)
    save_activity_mmp_peaks(uid, "88801", peaks)

    profile = get_power_spiderweb_profile(user_id=uid, timeframe="30d")
    axes = profile["axes"]
    assert len(axes) == 12
    assert [a["key"] for a in axes] == [d["key"] for d in RADAR_DURATIONS]
    assert axes[0]["key"] == "15s" and axes[0]["zone_group"] == "anaerobic" and axes[0]["current_watts"] == 700
    assert axes[3]["key"] == "2m" and axes[3]["zone_group"] == "vo2"
    assert axes[8]["key"] == "20m" and axes[8]["zone_group"] == "threshold"

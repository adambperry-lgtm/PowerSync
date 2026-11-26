import datetime
import json
from fastapi.testclient import TestClient

from app.main import app
from app.database import (
    init_db,
    create_or_get_dev_user,
    create_session,
    save_coach_chat_message,
    get_coach_chat_messages,
    get_upcoming_scheduled_workouts,
    get_setting,
    set_setting,
    get_athlete_date,
)
from app.services.coach_chat_service import _persist_coach_scheduled_workout


def _create_authed_client(email: str) -> tuple[TestClient, str, str]:
    init_db()
    user = create_or_get_dev_user(email=email, name="Rider")
    token = create_session(user["id"])
    client = TestClient(app)
    client.cookies.set("powersync_session", token)
    return client, user["id"], token


def test_cross_device_scheduled_workout_unification():
    client_phone, uid, token = _create_authed_client("cross_device_1@example.com")
    # Simulate a second browser window on Mac using the same user session
    client_mac = TestClient(app)
    client_mac.cookies.set("powersync_session", token)

    today = get_athlete_date(uid)
    tomorrow_iso = (today + datetime.timedelta(days=1)).isoformat()

    # Seed stale cached_daily_debrief before scheduling
    set_setting(
        "cached_daily_debrief",
        {
            "version": 3,
            "signature": f"{today.isoformat()}||",
            "review": {"success": True, "forward_outlook": [{"day_offset": 1, "title": "Old Cached Plan"}]},
        },
        user_id=uid,
    )

    # Save a coach chat message proposing a scheduled workout (as DS Coach would on phone)
    proposed = {
        "action_type": "schedule_workout",
        "title": "Sweet Spot Aerobic Builder",
        "target_date": tomorrow_iso,
        "duration_minutes": 45,
        "estimated_tss": 42,
        "focus_area": "Sweet Spot",
    }
    msg_id = save_coach_chat_message(
        role="model",
        content="I've prepared a 45-min Sweet Spot session for tomorrow.",
        proposed_action=proposed,
        user_id=uid,
    )
    assert msg_id > 0

    # Apply the action from Phone
    res = client_phone.post(
        "/api/chat/apply-action",
        json={
            "action_type": "schedule_workout",
            "action_data": proposed,
            "message_id": msg_id,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["target_date"] == tomorrow_iso

    # Verify Mac browser sees it in /api/workouts/scheduled
    sched_res = client_mac.get("/api/workouts/scheduled")
    assert sched_res.status_code == 200
    sched_list = sched_res.json()["scheduled_workouts"]
    assert any(
        str(w.get("date", ""))[:10] == tomorrow_iso and w.get("title") == "Sweet Spot Aerobic Builder"
        for w in sched_list
    )

    # Verify Mac browser sees already_applied=True in /api/chat/history
    hist_res = client_mac.get("/api/chat/history")
    assert hist_res.status_code == 200
    msgs = hist_res.json()["messages"]
    matching = [m for m in msgs if m.get("id") == msg_id]
    assert len(matching) == 1
    assert matching[0]["proposed_action"]["already_applied"] is True

    # Verify cached_daily_debrief was invalidated so Mac gets fresh 3-day outlook
    assert get_setting("cached_daily_debrief", None, user_id=uid) is None
    debrief_res = client_mac.get("/api/review/daily-debrief")
    assert debrief_res.status_code == 200
    outlook = debrief_res.json().get("outlook_days", [])
    tomorrow_cards = [d for d in outlook if d.get("target_date") == tomorrow_iso]
    assert len(tomorrow_cards) == 1
    assert tomorrow_cards[0].get("is_coach_scheduled") is True
    assert "Sweet Spot Aerobic Builder" in tomorrow_cards[0].get("title", "")


def test_persist_coach_scheduled_workout_saves_to_sqlite_and_isolates_users():
    client_a, uid_a, _ = _create_authed_client("user_a_sched@example.com")
    client_b, uid_b, _ = _create_authed_client("user_b_sched@example.com")

    today = get_athlete_date(uid_a)
    target_iso = (today + datetime.timedelta(days=2)).isoformat()

    proposed = {
        "action_type": "schedule_workout",
        "title": "Threshold Over-Unders",
        "target_date": target_iso,
        "duration_minutes": 45,
        "estimated_tss": 46,
        "focus_area": "Threshold",
    }
    _persist_coach_scheduled_workout(proposed, target_iso, user_id=uid_a, ftp=260)

    # Saved in SQLite workouts table for user A
    upcoming_a = get_upcoming_scheduled_workouts(today.isoformat(), user_id=uid_a)
    assert any(w.get("title") == "Threshold Over-Unders" and str(w.get("date"))[:10] == target_iso for w in upcoming_a)

    # User B must NOT see User A's scheduled workout
    res_b = client_b.get("/api/workouts/scheduled")
    assert res_b.status_code == 200
    assert res_b.json()["scheduled_workouts"] == []

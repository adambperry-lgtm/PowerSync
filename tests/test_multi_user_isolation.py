import os
import sys
import unittest
import threading
import time
import json
from typing import Any, Dict, Optional
import requests

# Ensure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import (
    init_db,
    get_db_connection,
    set_current_user_context,
    reset_current_user_context,
    get_current_user_id,
    set_setting,
    get_setting,
    save_target_plan,
    get_active_target_plan,
    save_scheduled_workout,
    get_scheduled_workout_for_date,
    create_or_get_dev_user,
    create_session,
    get_user_by_session,
    delete_session
)
from app.routers.dashboard import get_dashboard_data
from app.routers.settings import get_settings_endpoint, update_settings_endpoint, SettingsUpdate
from app.routers.plans import get_active_plan, save_plan, TargetPlanRequest
from app.routers.workouts import (
    generate_workout,
    WorkoutGenerateRequest,
    get_current_workout,
    select_workout_option,
    WorkoutSelectRequest
)

class TestMultiUserDirectAndIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_database_user_and_session_management(self):
        """Verify user creation, sessions, and session lookups."""
        user_a = create_or_get_dev_user("test.alice@powersync.test", "Alice Sprinter")
        self.assertEqual(user_a["email"], "test.alice@powersync.test")
        self.assertEqual(user_a["name"], "Alice Sprinter")
        self.assertTrue(user_a["id"].startswith("usr_"))

        user_b = create_or_get_dev_user("test.bob@powersync.test", "Bob Climber")
        self.assertEqual(user_b["email"], "test.bob@powersync.test")
        self.assertNotEqual(user_a["id"], user_b["id"])

        # Create session
        token_a = create_session(user_a["id"])
        self.assertTrue(len(token_a) >= 32)
        sess_user_a = get_user_by_session(token_a)
        self.assertIsNotNone(sess_user_a)
        self.assertEqual(sess_user_a["id"], user_a["id"])

        # Delete session
        delete_session(token_a)
        self.assertIsNone(get_user_by_session(token_a))

    def test_02_database_settings_strict_isolation(self):
        """Verify settings set for User A do not bleed into User B or default."""
        user_a = create_or_get_dev_user("iso.alice@powersync.test", "Iso Alice")
        user_b = create_or_get_dev_user("iso.bob@powersync.test", "Iso Bob")

        # Set settings under User A context
        set_current_user_context(user_a["id"])
        set_setting("athlete_ftp", 325, user_id=user_a["id"])
        set_setting("intervals_athlete_id", "i_alice_999", user_id=user_a["id"])

        # Set settings under User B context
        set_current_user_context(user_b["id"])
        set_setting("athlete_ftp", 215, user_id=user_b["id"])
        set_setting("intervals_athlete_id", "i_bob_111", user_id=user_b["id"])

        # Read back as User A
        set_current_user_context(user_a["id"])
        self.assertEqual(get_setting("athlete_ftp"), 325)
        self.assertEqual(get_setting("intervals_athlete_id"), "i_alice_999")

        # Read back as User B
        set_current_user_context(user_b["id"])
        self.assertEqual(get_setting("athlete_ftp"), 215)
        self.assertEqual(get_setting("intervals_athlete_id"), "i_bob_111")

        # Reset context
        set_current_user_context("usr_default")

    def test_03_target_plans_strict_isolation(self):
        """Verify target plans are isolated per athlete."""
        user_a = create_or_get_dev_user("target.alice@powersync.test", "Target Alice")
        user_b = create_or_get_dev_user("target.bob@powersync.test", "Target Bob")

        # Alice creates a target plan
        set_current_user_context(user_a["id"])
        plan_id = save_target_plan(
            {
                "title": "Haute Route Alps",
                "target_date": "2026-08-25",
                "distance_miles": 120.0,
                "elevation_gain_ft": 12500,
                "target_tss": 450,
                "route_description": "Col du Galibier climb"
            },
            user_id=user_a["id"]
        )
        self.assertTrue(plan_id.startswith("plan_"))

        # Alice sees her plan
        plan_a = get_active_target_plan(user_id=user_a["id"])
        self.assertIsNotNone(plan_a)
        self.assertEqual(plan_a["title"], "Haute Route Alps")

        # Bob queries active plan -> MUST BE NONE
        set_current_user_context(user_b["id"])
        plan_b = get_active_target_plan(user_id=user_b["id"])
        self.assertIsNone(plan_b, "Bob must not see Alice's target plan")

    def test_04_scheduled_workouts_strict_isolation(self):
        """Verify coach-scheduled workouts are strictly isolated per athlete."""
        user_a = create_or_get_dev_user("sched.alice@powersync.test", "Sched Alice")
        user_b = create_or_get_dev_user("sched.bob@powersync.test", "Sched Bob")

        target_date = "2026-10-31"
        workout_data = {
            "title": "Alice's Sweet Spot Intervals",
            "duration_minutes": 60,
            "estimated_tss": 68
        }
        save_scheduled_workout(workout_data, target_date, user_id=user_a["id"])

        # Alice sees her workout
        set_current_user_context(user_a["id"])
        w_a = get_scheduled_workout_for_date(target_date, user_id=user_a["id"])
        self.assertIsNotNone(w_a)
        self.assertEqual(w_a["title"], "Alice's Sweet Spot Intervals")

        # Bob queries the same date -> MUST BE NONE
        set_current_user_context(user_b["id"])
        w_b = get_scheduled_workout_for_date(target_date, user_id=user_b["id"])
        self.assertIsNone(w_b, "Bob must not see Alice's scheduled workout")

    def test_05_workout_caches_and_generation_isolation(self):
        """Verify in-memory workout caches and generation are scoped per user."""
        user_a = create_or_get_dev_user("cache.alice@powersync.test", "Cache Alice")
        user_b = create_or_get_dev_user("cache.bob@powersync.test", "Cache Bob")

        # Alice generates a 45m workout
        set_current_user_context(user_a["id"])
        gen_a = generate_workout(WorkoutGenerateRequest(duration_min=45))
        self.assertEqual(gen_a["active_workout"]["duration_minutes"], 45)

        # Bob generates a 90m workout
        set_current_user_context(user_b["id"])
        gen_b = generate_workout(WorkoutGenerateRequest(duration_min=90))
        self.assertEqual(gen_b["active_workout"]["duration_minutes"], 90)

        # Alice checks current workout
        set_current_user_context(user_a["id"])
        curr_a = get_current_workout()
        self.assertEqual(curr_a["active_workout"]["duration_minutes"], 45)

        # Bob checks current workout
        set_current_user_context(user_b["id"])
        curr_b = get_current_workout()
        self.assertEqual(curr_b["active_workout"]["duration_minutes"], 90)

    def test_06_dashboard_athlete_scoping(self):
        """Verify dashboard returns the active user profile and scoped athlete data."""
        user_a = create_or_get_dev_user("dash.alice@powersync.test", "Dash Alice")
        set_current_user_context(user_a["id"])
        set_setting("athlete_ftp", 295, user_id=user_a["id"])

        dash_a = get_dashboard_data()
        self.assertEqual(dash_a["athlete"]["ftp"], 295)
        self.assertIn("user", dash_a)
        self.assertEqual(dash_a["user"]["email"], "dash.alice@powersync.test")

        # Switch to Bob
        user_b = create_or_get_dev_user("dash.bob@powersync.test", "Dash Bob")
        set_current_user_context(user_b["id"])
        set_setting("athlete_ftp", 220, user_id=user_b["id"])

    def test_07_whoop_and_strava_metrics_isolation(self):
        """Verify Whoop and Strava database rows inserted by Athlete A are invisible to Athlete B."""
        user_a = create_or_get_dev_user("metrics.alice@powersync.test", "Metrics Alice")
        user_b = create_or_get_dev_user("metrics.bob@powersync.test", "Metrics Bob")

        conn = get_db_connection()
        c = conn.cursor()
        # Insert Whoop recovery row for Alice
        c.execute("""
            INSERT OR REPLACE INTO whoop_metrics (user_id, date, recovery_score, hrv_rmssd, sleep_performance, day_strain)
            VALUES (?, '2026-10-15', 88, 72.5, 94, 14.8)
        """, (user_a["id"],))

        # Insert Strava activity for Alice
        c.execute("""
            INSERT OR REPLACE INTO strava_activities (user_id, id, name, sport_type, distance_meters, moving_time_sec, total_elevation_gain, suffer_score, average_watts, weighted_average_watts, start_date)
            VALUES (?, '99001122', 'Alice Epic Mountain Pass', 'Ride', 85000.0, 10800, 1850.0, 120, 220, 245, '2026-10-15T09:00:00Z')
        """, (user_a["id"],))
        conn.commit()

        # Alice queries Whoop
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (user_a["id"],))
        row_a = c.fetchone()
        self.assertIsNotNone(row_a)
        self.assertEqual(int(row_a["recovery_score"]), 88)

        # Bob queries Whoop -> MUST BE NONE
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 1", (user_b["id"],))
        row_b = c.fetchone()
        self.assertIsNone(row_b, "Bob must not see Alice's whoop metrics")

        # Alice queries Strava activities
        c.execute("SELECT * FROM strava_activities WHERE user_id = ?", (user_a["id"],))
        acts_a = c.fetchall()
        self.assertEqual(len(acts_a), 1)
        self.assertEqual(acts_a[0]["name"], "Alice Epic Mountain Pass")

        # Bob queries Strava activities -> MUST BE EMPTY
        c.execute("SELECT * FROM strava_activities WHERE user_id = ?", (user_b["id"],))
        acts_b = c.fetchall()
        self.assertEqual(len(acts_b), 0, "Bob must not see Alice's strava activities")
        conn.close()

    def test_08_bearer_token_authorization(self):
        """Verify Authorization: Bearer <session_token> works seamlessly with full user context."""
        from app.main import app
        user = create_or_get_dev_user("bearer.test@powersync.test", "Bearer Athlete")
        token = create_session(user["id"])

        client = ASGIClient(app)
        # Request with Bearer header (no cookies)
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["email"], "bearer.test@powersync.test")
        self.assertFalse(me_resp.json()["is_guest"])

class ASGIClient:
    """Lightweight in-process ASGI test client supporting cookies and JSON payloads."""
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def request(self, method: str, path: str, json_data: Any = None, headers: Dict[str, str] = None):
        import asyncio
        import urllib.parse
        return asyncio.run(self._async_request(method, path, json_data, headers))

    async def _async_request(self, method: str, path: str, json_data: Any = None, headers: Dict[str, str] = None):
        import urllib.parse
        parsed = urllib.parse.urlparse(path)
        raw_headers = []
        if headers:
            for k, v in headers.items():
                raw_headers.append((k.lower().encode(), v.encode()))

        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode("utf-8")
            raw_headers.append((b"content-type", b"application/json"))

        if self.cookies:
            cookie_hdr = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            raw_headers.append((b"cookie", cookie_hdr.encode()))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "path": parsed.path,
            "raw_path": parsed.path.encode(),
            "query_string": parsed.query.encode(),
            "headers": raw_headers,
            "server": ("testserver", 80),
        }

        response_body = []
        response_headers = {}
        response_status = [200]

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                response_status[0] = message["status"]
                for k, v in message.get("headers", []):
                    k_str = k.decode().lower()
                    v_str = v.decode()
                    response_headers[k_str] = v_str
                    if k_str == "set-cookie":
                        # Parse simple cookie name=val
                        parts = v_str.split(";", 1)[0].split("=", 1)
                        if len(parts) == 2:
                            self.cookies[parts[0].strip()] = parts[1].strip()
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))

        await self.app(scope, receive, send)

        res_bytes = b"".join(response_body)
        class ResponseWrapper:
            def __init__(self, status, headers, content):
                self.status_code = status
                self.headers = headers
                self.content = content
            def json(self):
                return json.loads(self.content.decode("utf-8"))
        return ResponseWrapper(response_status[0], response_headers, res_bytes)

    def get(self, path: str, headers: Dict[str, str] = None):
        return self.request("GET", path, headers=headers)

    def post(self, path: str, json: Any = None, headers: Dict[str, str] = None):
        return self.request("POST", path, json_data=json, headers=headers)

class TestMultiUserHTTPServer(unittest.TestCase):
    def test_01_http_sessions_and_cookie_isolation(self):
        """Verify HTTP cookies isolate sessions and data across independent requests."""
        from app.main import app
        client_a = ASGIClient(app)
        client_b = ASGIClient(app)

        # User A logs in via dev-login
        r_a = client_a.post("/api/auth/dev-login", json={
            "email": "http.alice@powersync.test",
            "name": "HTTP Alice"
        })
        self.assertEqual(r_a.status_code, 200)
        self.assertIn("powersync_session", client_a.cookies)

        # User B logs in via dev-login
        r_b = client_b.post("/api/auth/dev-login", json={
            "email": "http.bob@powersync.test",
            "name": "HTTP Bob"
        })
        self.assertEqual(r_b.status_code, 200)
        self.assertIn("powersync_session", client_b.cookies)

        # Verify /api/auth/me for each
        me_a = client_a.get("/api/auth/me").json()
        me_b = client_b.get("/api/auth/me").json()
        self.assertEqual(me_a["email"], "http.alice@powersync.test")
        self.assertEqual(me_b["email"], "http.bob@powersync.test")
        self.assertNotEqual(me_a["id"], me_b["id"])

        # User A updates settings
        s_resp_a = client_a.post("/api/settings", json={
            "athlete_ftp": 330,
            "intervals_athlete_id": "i_http_alice"
        })
        self.assertEqual(s_resp_a.status_code, 200)

        # User B updates settings
        s_resp_b = client_b.post("/api/settings", json={
            "athlete_ftp": 210,
            "intervals_athlete_id": "i_http_bob"
        })
        self.assertEqual(s_resp_b.status_code, 200)

        # Verify User A's settings via GET /api/settings
        res_settings_a = client_a.get("/api/settings").json()
        self.assertEqual(res_settings_a["athlete_ftp"], 330)
        self.assertEqual(res_settings_a["intervals_athlete_id"], "i_http_alice")

        # Verify User B's settings via GET /api/settings
        res_settings_b = client_b.get("/api/settings").json()
        self.assertEqual(res_settings_b["athlete_ftp"], 210)
        self.assertEqual(res_settings_b["intervals_athlete_id"], "i_http_bob")

        # Confirm zero leakage across HTTP sessions
        self.assertNotEqual(res_settings_a["athlete_ftp"], res_settings_b["athlete_ftp"])

        # User A logs out
        logout_res = client_a.post("/api/auth/logout")
        self.assertEqual(logout_res.status_code, 200)
        me_after_logout = client_a.get("/api/auth/me").json()
        self.assertTrue(me_after_logout.get("is_guest", False) or me_after_logout.get("id") == "usr_default")

    def test_02_claim_default_history_endpoint(self):
        """Verify claim-default-data imports settings and history from usr_default into active account."""
        from app.main import app
        from app.database import set_setting

        # Seed usr_default with a distinct custom setting
        set_setting("athlete_ftp", 288, user_id="usr_default")
        set_setting("intervals_athlete_id", "i_legacy_777", user_id="usr_default")

        # New user logs in
        client = ASGIClient(app)
        client.post("/api/auth/dev-login", json={"email": "claim.test@powersync.test", "name": "Claim Athlete"})

        # Claim default history
        claim_res = client.post("/api/auth/claim-default-data")
        self.assertEqual(claim_res.status_code, 200)
        self.assertTrue(claim_res.json()["success"])

        # Check settings for this user -> should now have inherited 288W and i_legacy_777
        settings = client.get("/api/settings").json()
        self.assertEqual(settings["athlete_ftp"], 288)
        self.assertEqual(settings["intervals_athlete_id"], "i_legacy_777")

if __name__ == "__main__":
    unittest.main()

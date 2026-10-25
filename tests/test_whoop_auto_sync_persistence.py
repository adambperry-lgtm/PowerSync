import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import (
    init_db,
    get_db_connection,
    set_current_user_context,
    get_current_user_id,
    set_setting,
    get_setting,
    get_athlete_date,
    DEFAULT_USER_ID,
    GUEST_USER_ID
)
from app.routers.dashboard import get_dashboard_data
from app.services.whoop_service import fetch_latest_whoop_metrics
from app.main import app
from tests.test_multi_user_isolation import ASGIClient

class TestWhoopAutoSyncAndPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        set_current_user_context(DEFAULT_USER_ID)

    def test_01_whoop_fetch_and_date_mapping(self):
        """Verify Whoop multi-endpoint data maps correctly to athlete's local today date."""
        today = get_athlete_date()
        today_iso = today.isoformat()
        yesterday_iso = (today - datetime.timedelta(days=1)).isoformat()

        # Mock tokens
        set_setting("whoop_tokens", {
            "access_token": "mock_whoop_access_token_123",
            "refresh_token": "mock_refresh_token_123"
        }, user_id=DEFAULT_USER_ID)

        # Mock responses from Whoop API
        mock_rec_response = MagicMock()
        mock_rec_response.status_code = 200
        mock_rec_response.json.return_value = {
            "records": [
                {
                    "cycle_id": 99901,
                    "sleep_id": 88801,
                    "created_at": f"{today_iso}T11:15:00.000Z",
                    "score_state": "SCORED",
                    "score": {
                        "recovery_score": 82,
                        "resting_heart_rate": 51,
                        "hrv_rmssd_milli": 68.4
                    }
                },
                {
                    "cycle_id": 99900,
                    "sleep_id": 88800,
                    "created_at": f"{yesterday_iso}T11:00:00.000Z",
                    "score_state": "SCORED",
                    "score": {
                        "recovery_score": 65,
                        "resting_heart_rate": 56,
                        "hrv_rmssd_milli": 45.2
                    }
                }
            ]
        }

        mock_sleep_response = MagicMock()
        mock_sleep_response.status_code = 200
        mock_sleep_response.json.return_value = {
            "records": [
                {
                    "id": 88801,
                    "cycle_id": 99901,
                    "start": f"{yesterday_iso}T23:30:00.000Z",
                    "end": f"{today_iso}T07:15:00.000Z",
                    "nap": False,
                    "score": {
                        "sleep_performance_percentage": 91,
                        "stage_summary": {
                            "total_in_bed_time_milli": 28800000 # 8.0 hrs
                        }
                    }
                }
            ]
        }

        mock_cycle_response = MagicMock()
        mock_cycle_response.status_code = 200
        mock_cycle_response.json.return_value = {
            "records": [
                {
                    "id": 99901,
                    "start": f"{today_iso}T04:44:21.090Z",
                    "end": None, # in progress cycle for today
                    "score": {
                        "strain": 17.7
                    }
                },
                {
                    "id": 99900,
                    "start": f"{yesterday_iso}T03:03:25.450Z",
                    "end": f"{today_iso}T04:44:21.090Z", # ended early morning today
                    "score": {
                        "strain": 4.5
                    }
                }
            ]
        }

        def fake_requests_get(url, headers=None, timeout=10):
            if "/recovery" in url:
                return mock_rec_response
            elif "/activity/sleep" in url:
                return mock_sleep_response
            elif "/cycle" in url:
                return mock_cycle_response
            r = MagicMock()
            r.status_code = 404
            return r

        with patch("requests.get", side_effect=fake_requests_get):
            res = fetch_latest_whoop_metrics(user_id=DEFAULT_USER_ID)

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("date"), today_iso)
        self.assertEqual(res.get("recovery_score"), 82)
        self.assertEqual(res.get("hrv_rmssd"), 68.4)
        self.assertEqual(res.get("resting_heart_rate"), 51)
        self.assertEqual(res.get("sleep_performance"), 91)
        self.assertEqual(res.get("sleep_duration_hours"), 8.0)
        self.assertEqual(res.get("day_strain"), 17.7)

        # Verify persisted in SQLite for both DEFAULT_USER_ID and GUEST_USER_ID
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? AND date = ?", (DEFAULT_USER_ID, today_iso))
        row_def = c.fetchone()
        self.assertIsNotNone(row_def)
        self.assertEqual(int(row_def["recovery_score"]), 82)
        self.assertEqual(float(row_def["day_strain"]), 17.7)

        # Verify yesterday's strain is 4.5, not overwritten by today's or overwriting today's
        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? AND date = ?", (DEFAULT_USER_ID, yesterday_iso))
        row_yest = c.fetchone()
        self.assertIsNotNone(row_yest)
        self.assertEqual(float(row_yest["day_strain"]), 4.5)

        c.execute("SELECT * FROM whoop_metrics WHERE user_id = ? AND date = ?", (GUEST_USER_ID, today_iso))
        row_guest = c.fetchone()
        self.assertIsNotNone(row_guest)
        self.assertEqual(int(row_guest["recovery_score"]), 82)
        conn.close()

    def test_02_dashboard_returns_persisted_data_on_page_exit_and_reload(self):
        """Verify that exiting page and reloading displays stored data with is_today=True without re-prompting."""
        today_iso = get_athlete_date().isoformat()
        set_current_user_context(DEFAULT_USER_ID)

        # Directly get dashboard data
        dash = get_dashboard_data()
        self.assertIn("whoop", dash)
        whoop = dash["whoop"]
        self.assertTrue(whoop["is_today"])
        self.assertEqual(whoop["date"], today_iso)
        self.assertEqual(whoop["recovery_score"], 82)
        self.assertEqual(whoop["day_strain"], 17.7)
        self.assertEqual(whoop["recovery_zone"], "green")
        self.assertTrue(dash["integrations"]["whoop"]["connected"])

        # Simulate unauthenticated guest visitor (e.g. mobile Safari tab reopen)
        client = ASGIClient(app)
        dash_guest = client.get("/api/dashboard").json()
        self.assertIn("whoop", dash_guest)
        # Must return the athlete's real persisted metrics, NOT mock data
        self.assertEqual(dash_guest["whoop"]["recovery_score"], 82)
        self.assertEqual(dash_guest["whoop"]["day_strain"], 17.7)
        self.assertTrue(dash_guest["integrations"]["whoop"]["connected"])

    def test_03_oauth_callback_sets_persistent_session_cookie(self):
        """Verify Whoop OAuth callback issues powersync_session cookie and session_token query param."""
        with patch("app.routers.auth.exchange_whoop_code") as mock_ex, \
             patch("app.routers.auth.fetch_latest_whoop_metrics") as mock_fetch:
            mock_ex.return_value = {"success": True, "token_info": {"access_token": "tok_xyz"}}
            mock_fetch.return_value = {"success": True}

            client = ASGIClient(app)
            resp = client.get("/api/auth/whoop/callback?code=mock_code_123")
            self.assertEqual(resp.status_code, 302)
            loc = resp.headers.get("location", "")
            self.assertIn("whoop_connected=1", loc)
            self.assertIn("session_token=", loc)
            self.assertIn("powersync_session", client.cookies)

if __name__ == "__main__":
    unittest.main()

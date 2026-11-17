import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Point DATABASE_PATH to a temporary file before importing app modules
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_PATH"] = _tmp_db.name

from app.database import init_db, get_db_connection, get_setting, set_setting
from app.services.strava_service import (
    extract_strava_id,
    _upsert_strava_activities,
    exchange_strava_code,
    refresh_strava_token,
)
from app.services.coach_tools import (
    tool_search_strava_activities,
    tool_get_strava_activity_details,
)


class TestStrava64BitIds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(_tmp_db.name):
            os.unlink(_tmp_db.name)

    def test_extract_strava_id_prefers_id_str(self):
        # 64-bit ID exceeding JS Number.MAX_SAFE_INTEGER (9007199254740991)
        big_id_str = "9223372036854775807"
        # Simulate a case where numeric id was rounded/different vs id_str
        payload = {"id": 9223372036854775800, "id_str": big_id_str}
        self.assertEqual(extract_strava_id(payload), big_id_str)

    def test_extract_strava_id_fallback_to_id(self):
        payload = {"id": 9007199254740995}
        self.assertEqual(extract_strava_id(payload), "9007199254740995")
        self.assertEqual(extract_strava_id({"id": 12345, "id_str": ""}), "12345")
        self.assertEqual(extract_strava_id({}), "")

    def test_upsert_and_query_64bit_activity_id(self):
        uid = "usr_test_64bit"
        big_id_str = "9223372036854775801"
        activities = [
            {
                "id": 9223372036854775801,
                "id_str": big_id_str,
                "name": "64-Bit Century Ride",
                "sport_type": "Ride",
                "start_date": "2026-11-16T14:00:00Z",
                "moving_time": 3600,
                "distance": 40000.0,
                "total_elevation_gain": 450.0,
                "average_watts": 210.0,
                "weighted_average_watts": 225.0,
                "average_heartrate": 148.0,
                "max_heartrate": 172.0,
                "suffer_score": 85.0,
                "kilojoules": 756.0,
            }
        ]
        saved = _upsert_strava_activities(activities, uid)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["id"], big_id_str)

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM strava_activities WHERE user_id = ? AND id = ?", (uid, big_id_str))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], big_id_str)

        search_res = tool_search_strava_activities(query="64-Bit", days_back=30, user_id=uid)
        self.assertEqual(search_res["count"], 1)
        self.assertEqual(search_res["activities"][0]["id"], big_id_str)

        with patch("app.services.coach_tools._fetch_strava_api_activity", return_value=None):
            detail = tool_get_strava_activity_details(activity_id=big_id_str, user_id=uid)
        self.assertTrue(detail["found"])
        self.assertEqual(detail["activity_id"], big_id_str)

    def test_oauth_athlete_64bit_id_str_preserved(self):
        uid = "usr_test_athlete_64bit"
        set_setting("strava_client_id", "test_cid", user_id=uid)
        set_setting("strava_client_secret", "test_csec", user_id=uid)
        big_athlete_id = 9007199254740999

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "token_type": "Bearer",
            "expires_at": 1900000000,
            "expires_in": 21600,
            "refresh_token": "ref_1",
            "access_token": "acc_1",
            "athlete": {
                "id": big_athlete_id,
                "username": "sixtyfourbit",
            },
        }

        with patch("app.services.strava_service.requests.post", return_value=mock_token_resp):
            res = exchange_strava_code("auth_code_123", user_id=uid)

        self.assertTrue(res["success"])
        stored = get_setting("strava_tokens", {}, user_id=uid)
        self.assertEqual(stored["athlete"]["id_str"], str(big_athlete_id))

        # Refresh response omits athlete; verify athlete metadata with id_str is preserved
        mock_refresh_resp = MagicMock()
        mock_refresh_resp.status_code = 200
        mock_refresh_resp.json.return_value = {
            "token_type": "Bearer",
            "expires_at": 1900021600,
            "expires_in": 21600,
            "refresh_token": "ref_2",
            "access_token": "acc_2",
        }
        with patch("app.services.strava_service.requests.post", return_value=mock_refresh_resp):
            new_acc = refresh_strava_token(user_id=uid)

        self.assertEqual(new_acc, "acc_2")
        refreshed_stored = get_setting("strava_tokens", {}, user_id=uid)
        self.assertEqual(refreshed_stored["athlete"]["id_str"], str(big_athlete_id))


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import (
    init_db,
    set_current_user_context,
    reset_current_user_context,
    create_session,
    save_coach_chat_message,
    get_coach_chat_messages,
    clear_coach_chat_messages,
    get_coach_conversation_memory,
    clear_coach_conversation_memory,
    DEFAULT_USER_ID,
    GUEST_USER_ID,
)
from app.main import app
from app.services.coach_chat_service import (
    handle_coach_chat,
    build_system_prompt,
    maybe_update_conversation_memory,
)
from tests.test_multi_user_isolation import ASGIClient


class TestCoachConversationMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        from app.database import get_db_connection
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (id, email, name, picture) VALUES ('usr_mem_test_a', 'mema@test.local', 'Mem User A', '')")
        c.execute("INSERT OR IGNORE INTO users (id, email, name, picture) VALUES ('usr_mem_test_b', 'memb@test.local', 'Mem User B', '')")
        conn.commit()
        conn.close()

    def setUp(self):
        self.user_a = "usr_mem_test_a"
        self.user_b = "usr_mem_test_b"
        for uid in (self.user_a, self.user_b, GUEST_USER_ID):
            clear_coach_chat_messages(user_id=uid)
            clear_coach_conversation_memory(user_id=uid)

    def tearDown(self):
        for uid in (self.user_a, self.user_b, GUEST_USER_ID):
            clear_coach_chat_messages(user_id=uid)
            clear_coach_conversation_memory(user_id=uid)

    def test_01_chat_messages_persist_and_restore_via_api(self):
        """Messages sent to POST /api/chat persist in SQLite and are returned by GET /api/chat/history."""
        tok_a = create_session(self.user_a)
        client_a = ASGIClient(app)
        client_a.cookies["powersync_session"] = tok_a

        res_post = client_a.post("/api/chat", json={
            "message": "My left knee feels a bit tight today, should I do an easy spin?",
            "history": []
        })
        self.assertEqual(res_post.status_code, 200)
        post_data = res_post.json()
        self.assertTrue(post_data["success"])

        res_hist = client_a.get("/api/chat/history")
        self.assertEqual(res_hist.status_code, 200)
        hist_data = res_hist.json()
        self.assertTrue(hist_data["success"])
        msgs = hist_data["messages"]
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("left knee", msgs[0]["content"])
        self.assertEqual(msgs[1]["role"], "model")
        self.assertEqual(msgs[1]["content"], post_data["reply"])

    def test_02_multi_user_isolation(self):
        """User A's chat history and memory are strictly isolated from User B and Guest."""
        tok_a = create_session(self.user_a)
        tok_b = create_session(self.user_b)

        client_a = ASGIClient(app)
        client_a.cookies["powersync_session"] = tok_a
        client_b = ASGIClient(app)
        client_b.cookies["powersync_session"] = tok_b
        guest_client = ASGIClient(app)

        client_a.post("/api/chat", json={"message": "Secret goal: 340W FTP by July", "history": []})

        hist_b = client_b.get("/api/chat/history").json()
        hist_guest = guest_client.get("/api/chat/history").json()

        self.assertEqual(hist_b["messages"], [])
        self.assertEqual(hist_guest["messages"], [])

    def test_03_long_term_memory_distillation_and_prompt_injection(self):
        """Older turns beyond the active window distill into coach_conversation_memory and inject into system prompt."""
        tok = set_current_user_context(self.user_a)
        try:
            for i in range(9):
                if i == 1:
                    save_coach_chat_message("user", "My right knee felt tight after yesterday's climbs.", user_id=self.user_a)
                elif i == 2:
                    save_coach_chat_message("user", "I am targeting a 100-mile Gran Fondo in October.", user_id=self.user_a)
                else:
                    save_coach_chat_message("user", f"Training check-in message #{i}", user_id=self.user_a)
                save_coach_chat_message("model", f"Coach guidance response #{i}", user_id=self.user_a)

            # 18 messages total -> 8 messages before the 10-message recent window should be distilled
            distilled = maybe_update_conversation_memory(self.user_a, api_key="")
            self.assertIsNotNone(distilled)

            mem = get_coach_conversation_memory(user_id=self.user_a)
            self.assertTrue(mem["summary"])
            self.assertGreater(mem["last_summarized_msg_id"], 0)
            self.assertTrue(
                any("knee" in f.lower() or "gran fondo" in f.lower() for f in mem["key_facts"]),
                f"Expected durable facts in memory, got: {mem['key_facts']}"
            )

            prompt = build_system_prompt({"athlete": {"ftp_watts": 250}}, memory=mem)
            self.assertIn("PERSISTENT CONVERSATION MEMORY", prompt)
            self.assertIn(mem["summary"], prompt)
        finally:
            reset_current_user_context(tok)

    def test_04_clear_history_preserves_or_clears_memory(self):
        """DELETE /api/chat/history preserves distilled memory by default, and clears it when clear_memory=true."""
        tok_a = create_session(self.user_a)
        client_a = ASGIClient(app)
        client_a.cookies["powersync_session"] = tok_a

        client_a.post("/api/chat", json={"message": "I prefer riding early morning before work and have a knee tweak.", "history": []})

        # Clear transcript only -> memory should be distilled & preserved
        res_clear = client_a.request("DELETE", "/api/chat/history")
        self.assertEqual(res_clear.status_code, 200)
        clear_data = res_clear.json()
        self.assertTrue(clear_data["success"])
        self.assertFalse(clear_data["cleared_memory"])
        self.assertTrue(clear_data["memory"]["summary"] or clear_data["memory"]["key_facts"])

        # Transcript is now empty
        hist_after = client_a.get("/api/chat/history").json()
        self.assertEqual(hist_after["messages"], [])
        self.assertTrue(hist_after["memory"]["summary"] or hist_after["memory"]["key_facts"])

        # Clear memory explicitly
        res_mem_clear = client_a.request("DELETE", "/api/chat/memory")
        self.assertEqual(res_mem_clear.status_code, 200)
        hist_final = client_a.get("/api/chat/history").json()
        self.assertEqual(hist_final["memory"]["summary"], "")
        self.assertEqual(hist_final["memory"]["key_facts"], [])


if __name__ == "__main__":
    unittest.main()

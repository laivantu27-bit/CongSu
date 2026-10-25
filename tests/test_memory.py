import tempfile
import unittest
from pathlib import Path

from assistant_desktop.memory import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def test_remembers_and_recalls_relevant_local_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.sqlite3")

            saved = store.remember_user_message("Tôi thích món phở.")

            self.assertEqual(saved, ["preference: món phở"])
            self.assertEqual(store.recall("Bạn thích món phở gì?"), saved)
            self.assertEqual(store.recall("Bạn nhớ điều gì về tôi?"), saved)
            self.assertEqual(store.list_memories(), saved)

    def test_does_not_store_sensitive_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.sqlite3")

            self.assertEqual(
                store.remember_user_message(
                    "Tôi thích phở, mật khẩu của tôi là abc123."
                ),
                [],
            )
            self.assertEqual(store.list_memories(), [])

    def test_manual_memory_rejects_secrets_and_clear_removes_all(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.sqlite3")
            store.add("Tôi đang học tiếng Việt")
            with self.assertRaisesRegex(ValueError, "nhạy cảm"):
                store.add("api-key: abc123")

            self.assertEqual(store.clear(), 1)
            self.assertEqual(store.list_memories(), [])

    def test_conversation_history_persists_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.sqlite3"
            store = MemoryStore(database)
            conversation_id = store.create_conversation()
            store.save_conversation_message(
                conversation_id, "user", "Tôi đang học Python"
            )
            store.save_conversation_message(
                conversation_id, "assistant", "Mình có thể cùng bạn học."
            )

            reopened_store = MemoryStore(database)
            self.assertEqual(
                reopened_store.load_conversation(conversation_id),
                [
                    {"role": "user", "content": "Tôi đang học Python"},
                    {"role": "assistant", "content": "Mình có thể cùng bạn học."},
                ],
            )
            self.assertEqual(
                reopened_store.list_conversations()[0]["title"],
                "Tôi đang học Python",
            )
            self.assertEqual(reopened_store.clear_conversations(), 1)
            self.assertEqual(reopened_store.list_conversations(), [])


if __name__ == "__main__":
    unittest.main()

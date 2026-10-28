from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from chat_storage import ChatStorage


class ChatStorageTests(unittest.TestCase):
    def test_exchanges_survive_reopening_with_exact_text_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "chat.sqlite3"
            query = "What's open?'); DROP TABLE chat_history; --"
            answer = "Welcome!\nIt's open — kumusta."
            ChatStorage(path).save(query, answer, 12.5, 0.75)
            second_id = ChatStorage(path).save("Next question", "Next answer", None, None)
            ChatStorage(path).set_feedback(second_id, "like")
            with closing(sqlite3.connect(path)) as connection:
                rows = connection.execute(
                    "SELECT user_query, llm_answer, tps, ttft, created_at, feedback "
                    "FROM chat_history ORDER BY id"
                ).fetchall()
            self.assertEqual(rows[0][:4], (query, answer, 12.5, 0.75))
            self.assertEqual(rows[1][:4], ("Next question", "Next answer", None, None))
            self.assertTrue(all(row[4].endswith("Z") for row in rows))
            self.assertEqual(rows[0][5], None)
            self.assertEqual(rows[1][5], "like")

    def test_feedback_can_be_changed_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = ChatStorage(Path(directory) / "chat.sqlite3")
            message_id = storage.save("Question", "Answer", None, None)
            self.assertTrue(storage.set_feedback(message_id, "dislike"))
            self.assertEqual(storage.list_recent()[0]["feedback"], "dislike")
            self.assertTrue(storage.set_feedback(message_id, None))
            self.assertIsNone(storage.list_recent()[0]["feedback"])
            self.assertFalse(storage.set_feedback(message_id + 99, "like"))

    def test_history_returns_recent_records_with_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = ChatStorage(Path(directory) / "chat.sqlite3")
            storage.save("First", "Answer 1", 10.5, 0.2)
            storage.save("Second", "Answer 2", None, None)
            records = storage.list_recent()
            self.assertEqual([item["user_query"] for item in records], ["Second", "First"])
            self.assertEqual(records[1]["tps"], 10.5)
            self.assertEqual(records[1]["ttft"], 0.2)
            self.assertIsNone(records[0]["tps"])


if __name__ == "__main__":
    unittest.main()

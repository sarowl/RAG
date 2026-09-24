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
            ChatStorage(path).save("Next question", "Next answer", None, None)
            with closing(sqlite3.connect(path)) as connection:
                rows = connection.execute(
                    "SELECT user_query, llm_answer, tps, ttft, created_at "
                    "FROM chat_history ORDER BY id"
                ).fetchall()
            self.assertEqual(rows[0][:4], (query, answer, 12.5, 0.75))
            self.assertEqual(rows[1][:4], ("Next question", "Next answer", None, None))
            self.assertTrue(all(row[4].endswith("Z") for row in rows))


if __name__ == "__main__":
    unittest.main()

"""SQLite persistence for completed chatbot exchanges."""

from contextlib import closing
from pathlib import Path
import sqlite3


class ChatStorage:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY,
                        created_at TEXT NOT NULL DEFAULT
                            (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                        user_query TEXT NOT NULL,
                        llm_answer TEXT NOT NULL,
                        tps REAL,
                        ttft REAL
                    )
                """)

    def save(
        self, user_query: str, llm_answer: str,
        tps: float | None, ttft: float | None,
    ) -> None:
        """Commit one exchange; TPS is tokens/sec and TTFT is seconds."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO chat_history (user_query, llm_answer, tps, ttft) "
                    "VALUES (?, ?, ?, ?)",
                    (user_query, llm_answer, tps, ttft),
                )

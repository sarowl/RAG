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
                        ttft REAL,
                        feedback TEXT CHECK (feedback IN ('like', 'dislike') OR feedback IS NULL)
                    )
                """)
            # Existing history databases predate message feedback.
            columns = {row[1] for row in connection.execute("PRAGMA table_info(chat_history)")}
            if "feedback" not in columns:
                connection.execute(
                    "ALTER TABLE chat_history ADD COLUMN feedback TEXT "
                    "CHECK (feedback IN ('like', 'dislike') OR feedback IS NULL)"
                )

    def save(
        self, user_query: str, llm_answer: str,
        tps: float | None, ttft: float | None,
    ) -> int:
        """Commit one exchange and return its ID; TPS is tokens/sec and TTFT is seconds."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO chat_history (user_query, llm_answer, tps, ttft) "
                    "VALUES (?, ?, ?, ?)",
                    (user_query, llm_answer, tps, ttft),
                )
                return cursor.lastrowid

    def set_feedback(self, message_id: int, feedback: str | None) -> bool:
        """Set or clear feedback for a saved assistant response."""
        if feedback not in ("like", "dislike", None):
            raise ValueError("Feedback must be like, dislike, or null.")
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                cursor = connection.execute(
                    "UPDATE chat_history SET feedback = ? WHERE id = ?",
                    (feedback, message_id),
                )
                return cursor.rowcount > 0

    def list_recent(self, limit: int = 500) -> list[dict]:
        """Return recent exchanges for the authenticated admin history view."""
        limit = max(1, min(int(limit), 1000))
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, created_at, user_query, llm_answer, tps, ttft, feedback "
                "FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

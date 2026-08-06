import sqlite3
import os
from typing import List, Dict, Any
import logging
from contextlib import closing
from ..security.crypto import crypto_manager

logger = logging.getLogger(__name__)


class SQLiteStore:
    def __init__(self, db_path: str = ".jarvis/memory.db"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            # WAL: concurrent readers + one writer; busy_timeout: retry up to
            # 5 s before raising SQLITE_BUSY (relevant under multiple workers).
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

    def _get_conn(self) -> sqlite3.Connection:
        """Open a connection with WAL + busy_timeout already set."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def add_message(self, role: str, content: str) -> None:
        try:
            with closing(self._get_conn()) as conn:
                with conn:
                    conn.execute(
                        "INSERT INTO messages (role, content) VALUES (?, ?)",
                        (role, crypto_manager.encrypt(content))
                    )
        except sqlite3.OperationalError as e:
            if "no such table: messages" in str(e):
                self._ensure_db()
                with closing(self._get_conn()) as conn:
                    with conn:
                        conn.execute(
                            "INSERT INTO messages (role, content) VALUES (?, ?)",
                            (role, crypto_manager.encrypt(content))
                        )
            else:
                raise

    def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with closing(self._get_conn()) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT role, content, timestamp FROM messages ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
                # Reverse to get chronological order
                results = []
                for row in reversed(cursor.fetchall()):
                    d = dict(row)
                    d['content'] = crypto_manager.decrypt(d['content'])
                    results.append(d)
                return results
        except sqlite3.OperationalError as e:
            if "no such table: messages" in str(e):
                self._ensure_db()
                return []
            raise

    def get_recent_messages_formatted(self, limit: int = 20) -> List[Dict[str, str]]:
        """Return recent messages in Ollama/OpenAI chat format: [{role, content}].
        
        Maps 'jarvis' role to 'assistant' as expected by the Ollama chat API.
        """
        raw = self.get_recent_messages(limit=limit)
        formatted = []
        for msg in raw:
            role = msg["role"]
            # Map 'jarvis' → 'assistant' for Ollama chat API compatibility
            if role == "jarvis":
                role = "assistant"
            formatted.append({"role": role, "content": msg["content"]})
        return formatted

    def clear_history(self) -> None:
        """Wipe all messages (useful for starting a new session)."""
        try:
            with closing(self._get_conn()) as conn:
                with conn:
                    conn.execute("DELETE FROM messages")
        except sqlite3.OperationalError as e:
            if "no such table: messages" in str(e):
                self._ensure_db()
            else:
                raise

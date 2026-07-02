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
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                # Enable WAL mode for concurrent access
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

    def add_message(self, role: str, content: str):
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute(
                        "INSERT INTO messages (role, content) VALUES (?, ?)",
                        (role, crypto_manager.encrypt(content))
                    )
        except sqlite3.OperationalError as e:
            if "no such table: messages" in str(e):
                self._ensure_db()
                with closing(sqlite3.connect(self.db_path)) as conn:
                    with conn:
                        conn.execute(
                            "INSERT INTO messages (role, content) VALUES (?, ?)",
                            (role, crypto_manager.encrypt(content))
                        )
            else:
                raise

    def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
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

    def clear_history(self):
        """Wipe all messages (useful for starting a new session)."""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("DELETE FROM messages")
        except sqlite3.OperationalError as e:
            if "no such table: messages" in str(e):
                self._ensure_db()
            else:
                raise

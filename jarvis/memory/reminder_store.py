import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any
from contextlib import closing
import logging

logger = logging.getLogger(__name__)

DB_PATH = ".jarvis/memory.db"


class ReminderStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT NOT NULL,
                        fire_at DATETIME NOT NULL,
                        fired INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

    def add_reminder(self, text: str, fire_at: datetime) -> int:
        """Add a new reminder. Returns the new reminder ID."""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    cursor = conn.execute(
                        "INSERT INTO reminders (text, fire_at) VALUES (?, ?)",
                        (text, fire_at.strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    return cursor.lastrowid  # type: ignore
        except sqlite3.OperationalError as e:
            if "no such table: reminders" in str(e):
                self._ensure_table()
                with closing(sqlite3.connect(self.db_path)) as conn:
                    with conn:
                        cursor = conn.execute(
                            "INSERT INTO reminders (text, fire_at) VALUES (?, ?)",
                            (text, fire_at.strftime("%Y-%m-%d %H:%M:%S"))
                        )
                        return cursor.lastrowid  # type: ignore
            raise

    def get_pending_reminders(self) -> List[Dict[str, Any]]:
        """Return reminders that are due now and have not yet fired."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM reminders WHERE fired = 0 AND fire_at <= ? ORDER BY fire_at",
                    (now,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            if "no such table: reminders" in str(e):
                self._ensure_table()
                return []
            raise

    def mark_fired(self, reminder_id: int):
        """Mark a reminder as fired so it won't repeat."""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
        except sqlite3.OperationalError as e:
            if "no such table: reminders" in str(e):
                self._ensure_table()
            else:
                raise

    def get_all_upcoming(self) -> List[Dict[str, Any]]:
        """Return all reminders that have not yet fired, ordered by time."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM reminders WHERE fired = 0 AND fire_at > ? ORDER BY fire_at",
                    (now,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            if "no such table: reminders" in str(e):
                self._ensure_table()
                return []
            raise

    def clear_all_pending(self):
        """Cancel all unfired reminders."""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("DELETE FROM reminders WHERE fired = 0")
        except sqlite3.OperationalError as e:
            if "no such table: reminders" in str(e):
                self._ensure_table()
            else:
                raise

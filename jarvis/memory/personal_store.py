import sqlite3
import os
import datetime
from typing import List, Dict, Any, Optional
from ..security.crypto import crypto_manager

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "personal.db"))

class PersonalStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Goals Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    progress INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'in_progress',
                    target_date TEXT,
                    created_at TEXT
                )
            ''')
            
            # Health Logs Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS health_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_date TEXT NOT NULL,
                    log_type TEXT NOT NULL,  -- 'sleep', 'exercise', 'diet'
                    value TEXT NOT NULL,     -- e.g. "8" for sleep hours, "run 5km"
                    notes TEXT
                )
            ''')
            
            # Financial Logs Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS financial_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_date TEXT NOT NULL,
                    log_type TEXT NOT NULL,  -- 'income', 'expense'
                    amount REAL NOT NULL,
                    category TEXT,
                    description TEXT
                )
            ''')
            
            # Memory Profile Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            
            conn.commit()

    # --- Goals ---
    def add_goal(self, title: str, description: str = "", target_date: str = "") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO goals (title, description, target_date, created_at) VALUES (?, ?, ?, ?)",
                (crypto_manager.encrypt(title), crypto_manager.encrypt(description), target_date, datetime.datetime.now().isoformat())
            )
            conn.commit()
            return cursor.lastrowid

    def update_goal_progress(self, goal_id: int, progress: int, status: str = 'in_progress'):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE goals SET progress = ?, status = ? WHERE id = ?",
                (progress, status, goal_id)
            )
            conn.commit()

    def get_goals(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM goals ORDER BY created_at DESC")
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d['title'] = crypto_manager.decrypt(d['title'])
                d['description'] = crypto_manager.decrypt(d['description'])
                results.append(d)
            return results

    # --- Health Logs ---
    def add_health_log(self, log_type: str, value: str, notes: str = "", log_date: str = None) -> int:
        if not log_date:
            log_date = datetime.datetime.now().date().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO health_logs (log_date, log_type, value, notes) VALUES (?, ?, ?, ?)",
                (log_date, log_type, crypto_manager.encrypt(value), crypto_manager.encrypt(notes))
            )
            conn.commit()
            return cursor.lastrowid

    def get_health_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM health_logs ORDER BY log_date DESC, id DESC LIMIT ?", (limit,))
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d['value'] = crypto_manager.decrypt(d['value'])
                d['notes'] = crypto_manager.decrypt(d['notes'])
                results.append(d)
            return results

    # --- Financial Logs ---
    def add_financial_log(self, log_type: str, amount: float, category: str, description: str = "", log_date: str = None) -> int:
        if not log_date:
            log_date = datetime.datetime.now().date().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO financial_logs (log_date, log_type, amount, category, description) VALUES (?, ?, ?, ?, ?)",
                (log_date, log_type, amount, crypto_manager.encrypt(category), crypto_manager.encrypt(description))
            )
            conn.commit()
            return cursor.lastrowid

    def get_financial_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM financial_logs ORDER BY log_date DESC, id DESC LIMIT ?", (limit,))
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d['category'] = crypto_manager.decrypt(d['category'])
                d['description'] = crypto_manager.decrypt(d['description'])
                results.append(d)
            return results

    # --- Memory Profile ---
    def set_memory(self, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO memory_profile (key, value) VALUES (?, ?)",
                (key, crypto_manager.encrypt(value))
            )
            conn.commit()

    def get_memory(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM memory_profile WHERE key = ?", (key,))
            row = cursor.fetchone()
            return crypto_manager.decrypt(row["value"]) if row else None

    def get_all_memory(self) -> Dict[str, str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM memory_profile")
            return {row["key"]: crypto_manager.decrypt(row["value"]) for row in cursor.fetchall()}

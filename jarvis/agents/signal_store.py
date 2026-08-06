"""
signal_store.py — SQLite persistence for JARVIS trading signals.

Stores all generated trading signals (real-time pushes and EOD digests)
in `personal.db` for queryability, self-auditing, and memory context.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = "personal.db"


class SignalStore:
    """Manages the trading_signals table in SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create trading_signals table if it doesn't exist."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trading_signals (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker           TEXT    NOT NULL,
                        action           TEXT    NOT NULL,
                        confidence_score INTEGER NOT NULL,
                        confidence_pct   REAL    NOT NULL,
                        signal_layers    TEXT    NOT NULL,
                        entry_price      REAL    NOT NULL,
                        stop_loss        REAL    NOT NULL,
                        target_price     REAL    NOT NULL,
                        horizon_days     INTEGER NOT NULL DEFAULT 4,
                        is_fo            INTEGER NOT NULL DEFAULT 0,
                        fo_flags         TEXT    DEFAULT '[]',
                        narrative        TEXT    DEFAULT '',
                        delivery         TEXT    NOT NULL,
                        qty_suggested    INTEGER DEFAULT 0,
                        capital_required REAL    DEFAULT 0.0,
                        risk_inr         REAL    DEFAULT 0.0,
                        created_at       TEXT    NOT NULL,
                        shadow_trade_id  INTEGER DEFAULT NULL
                    )
                """)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def add_signal(
        self,
        ticker: str,
        action: str,
        confidence_score: int,
        confidence_pct: float,
        signal_layers: List[str],
        entry_price: float,
        stop_loss: float,
        target_price: float,
        delivery: str,
        horizon_days: int = 4,
        is_fo: bool = False,
        fo_flags: Optional[List[str]] = None,
        narrative: str = "",
        qty_suggested: int = 0,
        capital_required: float = 0.0,
        risk_inr: float = 0.0,
        shadow_trade_id: Optional[int] = None,
    ) -> int:
        """Insert a new signal into the database. Returns inserted row ID."""
        created_at = datetime.now().isoformat()
        layers_json = json.dumps(signal_layers)
        fo_flags_json = json.dumps(fo_flags or [])

        try:
            with closing(self._get_conn()) as conn:
                with conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO trading_signals (
                            ticker, action, confidence_score, confidence_pct,
                            signal_layers, entry_price, stop_loss, target_price,
                            horizon_days, is_fo, fo_flags, narrative, delivery,
                            qty_suggested, capital_required, risk_inr,
                            created_at, shadow_trade_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ticker, action, confidence_score, confidence_pct,
                            layers_json, entry_price, stop_loss, target_price,
                            horizon_days, 1 if is_fo else 0, fo_flags_json,
                            narrative, delivery, qty_suggested, capital_required,
                            risk_inr, created_at, shadow_trade_id,
                        ),
                    )
                    row_id = cursor.lastrowid
                    logger.info(f"SignalStore: Saved signal #{row_id} for {ticker} ({action}, {delivery})")
                    return row_id
        except Exception as exc:
            logger.error(f"SignalStore: Failed to insert signal for {ticker}: {exc}")
            return -1

    def get_recent_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch most recent signals."""
        try:
            with closing(self._get_conn()) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM trading_signals ORDER BY id DESC LIMIT ?", (limit,)
                )
                results = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d["signal_layers"] = json.loads(d.get("signal_layers", "[]"))
                    d["fo_flags"] = json.loads(d.get("fo_flags", "[]"))
                    results.append(d)
                return results
        except Exception as exc:
            logger.error(f"SignalStore: Failed to fetch signals: {exc}")
            return []

    def has_recent_realtime_signal(self, ticker: str, action: str, within_hours: float = 4.0) -> bool:
        """Check if a real-time signal for this ticker+action was generated recently (deduplication)."""
        try:
            with closing(self._get_conn()) as conn:
                cursor = conn.execute(
                    """
                    SELECT created_at FROM trading_signals
                    WHERE ticker = ? AND action = ? AND delivery = 'realtime'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (ticker, action),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                last_time = datetime.fromisoformat(row[0])
                elapsed_hours = (datetime.now() - last_time).total_seconds() / 3600.0
                return elapsed_hours < within_hours
        except Exception:
            return False


signal_store = SignalStore()

"""
LatencyTracker — per-agent response time monitoring for JARVIS.

Tracks every agent call's latency in SQLite and surfaces regressions.
Dashboard can query GET /api/latency for a JSON summary.

Table: latency_log
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  timestamp   TEXT
  agent       TEXT
  model       TEXT
  latency_ms  REAL
  tokens_in   INTEGER (optional)
  tokens_out  INTEGER (optional)
"""
from __future__ import annotations
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "personal.db",
)


class LatencyTracker:
    """Tracks per-agent response latency."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS latency_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    agent       TEXT    NOT NULL,
                    model       TEXT    NOT NULL DEFAULT 'unknown',
                    latency_ms  REAL    NOT NULL,
                    tokens_in   INTEGER DEFAULT 0,
                    tokens_out  INTEGER DEFAULT 0
                )
            """)
            conn.commit()
            conn.close()
            logger.info("LatencyTracker: table ready ✓")
        except Exception as exc:
            logger.error(f"LatencyTracker._ensure_table error: {exc}")

    def record(
        self,
        agent: str,
        latency_ms: float,
        model: str = "unknown",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Log one agent call's latency."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO latency_log
                   (timestamp, agent, model, latency_ms, tokens_in, tokens_out)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.now().isoformat(), agent, model, latency_ms, tokens_in, tokens_out),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"LatencyTracker.record error: {exc}")

    @contextmanager
    def measure(self, agent: str, model: str = "unknown"):
        """Context manager for timing an agent call."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.record(agent, elapsed_ms, model)
            if elapsed_ms > 10000:
                logger.warning(f"⚠️ Latency regression: {agent} took {elapsed_ms:.0f}ms")

    def get_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Return per-agent latency summary for the last N hours."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT agent, model,
                          COUNT(*) as calls,
                          AVG(latency_ms) as avg_ms,
                          MAX(latency_ms) as max_ms,
                          MIN(latency_ms) as min_ms
                   FROM latency_log
                   WHERE timestamp > ?
                   GROUP BY agent, model
                   ORDER BY avg_ms DESC""",
                (cutoff,),
            ).fetchall()
            conn.close()
            return {"period_hours": hours, "agents": [dict(r) for r in rows]}
        except Exception as exc:
            logger.error(f"LatencyTracker.get_summary error: {exc}")
            return {"period_hours": hours, "agents": []}

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent raw latency entries."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM latency_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"LatencyTracker.get_recent error: {exc}")
            return []


# ── Global singleton ──────────────────────────────────────────────────────────

latency_tracker = LatencyTracker()

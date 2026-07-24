"""
AuditLog — persistent action audit trail for JARVIS.

Every autonomous action (file changes, code execution, notifications sent,
trade recommendations, watchdog triggers) is recorded here with its
reasoning so any action is reviewable after the fact.

Table schema (SQLite — personal.db):
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    timestamp   TEXT    — ISO 8601
    agent       TEXT    — which agent triggered this (Executor, Trading, Watchdog …)
    action_type TEXT    — execute_code | send_notification | trade_suggest | file_write | …
    details     TEXT    — human-readable description of the action
    reasoning   TEXT    — why JARVIS decided to take this action
    tier        TEXT    — read_only | propose_diff | execute_with_confirmation
    approved    INTEGER — 0=auto, 1=user approved, -1=user rejected, -2=killed
    result      TEXT    — outcome / error message
"""
from __future__ import annotations
import logging
import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "personal.db",
)


class AuditLog:
    """Thread-safe persistent action audit log backed by SQLite."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_table()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    agent       TEXT    NOT NULL,
                    action_type TEXT    NOT NULL,
                    details     TEXT    NOT NULL DEFAULT '',
                    reasoning   TEXT    NOT NULL DEFAULT '',
                    tier        TEXT    NOT NULL DEFAULT 'execute_with_confirmation',
                    approved    INTEGER NOT NULL DEFAULT 0,
                    result      TEXT    NOT NULL DEFAULT ''
                )
            """)
            conn.commit()
            conn.close()
            logger.info("AuditLog: table ready ✓")
        except Exception as exc:
            logger.error(f"AuditLog._ensure_table error: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def record(
        self,
        agent: str,
        action_type: str,
        details: str,
        reasoning: str = "",
        tier: str = "execute_with_confirmation",
        approved: int = 0,
        result: str = "",
    ) -> int:
        """
        Write one audit entry. Returns the new row id.

        approved codes:
            0  = auto-executed (within permitted tier)
            1  = explicitly approved by user
           -1  = rejected by user
           -2  = stopped by kill switch
        """
        ts = datetime.now().isoformat()
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """INSERT INTO audit_log
                   (timestamp, agent, action_type, details, reasoning, tier, approved, result)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, agent, action_type, details, reasoning, tier, approved, result),
            )
            row_id = cur.lastrowid
            conn.commit()
            conn.close()
            logger.info(
                f"[AUDIT] [{agent}] {action_type} | tier={tier} | approved={approved}"
            )
            return row_id
        except Exception as exc:
            logger.error(f"AuditLog.record error: {exc}")
            return -1

    def update_result(self, row_id: int, result: str, approved: int = 0) -> None:
        """Update the result and approval status of an existing audit entry."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE audit_log SET result = ?, approved = ? WHERE id = ?",
                (result, approved, row_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"AuditLog.update_result error: {exc}")

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent N audit entries."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"AuditLog.get_recent error: {exc}")
            return []

    def get_by_agent(self, agent: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent entries for a specific agent."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE agent = ? ORDER BY id DESC LIMIT ?",
                (agent, limit),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"AuditLog.get_by_agent error: {exc}")
            return []

    def format_for_display(self, entries: List[Dict[str, Any]]) -> str:
        """Format audit entries as readable text for Jay."""
        if not entries:
            return "No audit entries found."
        lines = ["📋 Action Audit Log:\n"]
        for e in entries:
            approved_str = {0: "auto", 1: "✅ approved", -1: "❌ rejected", -2: "🛑 killed"}.get(
                e.get("approved", 0), "unknown"
            )
            lines.append(
                f"[{e['timestamp'][:19]}] {e['agent']} → {e['action_type']} ({approved_str})\n"
                f"  Details  : {e['details'][:120]}\n"
                f"  Reasoning: {e['reasoning'][:120]}\n"
                f"  Result   : {e['result'][:120]}\n"
            )
        return "\n".join(lines)


# ── Global singleton ──────────────────────────────────────────────────────────

audit_log = AuditLog()

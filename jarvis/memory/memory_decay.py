"""
MemoryDecay — periodic stale memory review for JARVIS.

People change jobs, priorities shift, and relationships evolve.
This module surfaces older memories on a monthly cadence and asks Jay
whether each fact still holds — instead of memory only ever growing stale.

SQLite column added to vector store metadata: staleness_flag
Values: 'fresh' | 'stale' | 'confirmed' | 'updated'

Surfacing rules:
  • Monthly review (configurable cadence)
  • Only surfaces memories older than DECAY_THRESHOLD_DAYS
  • Surfaces during low-activity periods (not mid-conversation)
  • Max N_PER_REVIEW facts per session to avoid overwhelming Jay
"""
from __future__ import annotations
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "personal.db",
)

DECAY_THRESHOLD_DAYS = 30     # surface memories older than this
N_PER_REVIEW = 5              # max facts per review session
REVIEW_CADENCE_DAYS = 30      # how often to surface reviews


class MemoryDecay:
    """Manages staleness tracking and periodic review of long-term memories."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_tables()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory_items (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    content         TEXT    NOT NULL,
                    category        TEXT    NOT NULL DEFAULT 'fact',
                    source          TEXT    NOT NULL DEFAULT 'conversation',
                    created_at      TEXT    NOT NULL,
                    last_confirmed  TEXT,
                    staleness_flag  TEXT    NOT NULL DEFAULT 'fresh'
                        CHECK(staleness_flag IN ('fresh','stale','confirmed','updated')),
                    notes           TEXT    DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS memory_review_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    reviewed_at     TEXT    NOT NULL,
                    items_surfaced  INTEGER NOT NULL DEFAULT 0,
                    items_confirmed INTEGER NOT NULL DEFAULT 0,
                    items_updated   INTEGER NOT NULL DEFAULT 0,
                    items_staled    INTEGER NOT NULL DEFAULT 0
                );
            """)
            conn.commit()
            conn.close()
            logger.info("MemoryDecay: tables ready ✓")
        except Exception as exc:
            logger.error(f"MemoryDecay._ensure_tables error: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def store_memory(
        self,
        content: str,
        category: str = "fact",
        source: str = "conversation",
    ) -> int:
        """Store a new memory item."""
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """INSERT INTO memory_items (content, category, source, created_at)
                   VALUES (?, ?, ?, ?)""",
                (content, category, source, datetime.now().isoformat()),
            )
            row_id = cur.lastrowid
            conn.commit()
            conn.close()
            return row_id
        except Exception as exc:
            logger.error(f"MemoryDecay.store_memory error: {exc}")
            return -1

    def get_stale_candidates(self) -> List[Dict[str, Any]]:
        """Return memories older than DECAY_THRESHOLD_DAYS that are still 'fresh'."""
        cutoff = (datetime.now() - timedelta(days=DECAY_THRESHOLD_DAYS)).isoformat()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM memory_items
                   WHERE created_at < ?
                     AND staleness_flag = 'fresh'
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (cutoff, N_PER_REVIEW),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"MemoryDecay.get_stale_candidates error: {exc}")
            return []

    def should_run_review(self) -> bool:
        """Check if enough time has passed since the last review."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT reviewed_at FROM memory_review_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row is None:
                return True
            last = datetime.fromisoformat(row[0])
            return (datetime.now() - last).days >= REVIEW_CADENCE_DAYS
        except Exception:
            return True

    def mark_reviewed(self, item_id: int, new_flag: str, notes: str = "") -> None:
        """Update a memory item's staleness flag after Jay's review."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """UPDATE memory_items
                   SET staleness_flag = ?, last_confirmed = ?, notes = ?
                   WHERE id = ?""",
                (new_flag, datetime.now().isoformat(), notes, item_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"MemoryDecay.mark_reviewed error: {exc}")

    def log_review_session(
        self, surfaced: int, confirmed: int, updated: int, staled: int
    ) -> None:
        """Record that a review session happened."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO memory_review_log
                   (reviewed_at, items_surfaced, items_confirmed, items_updated, items_staled)
                   VALUES (?, ?, ?, ?, ?)""",
                (datetime.now().isoformat(), surfaced, confirmed, updated, staled),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"MemoryDecay.log_review_session error: {exc}")

    def format_review_prompt(self, candidates: List[Dict[str, Any]]) -> str:
        """Format stale memories as a review prompt for Jay."""
        if not candidates:
            return "All memories are up to date — no review needed right now."

        lines = [
            "🧠 Monthly Memory Review\n",
            f"I'd like to check if these {len(candidates)} facts still hold, Jay:\n",
        ]
        for i, item in enumerate(candidates, 1):
            age_days = (datetime.now() - datetime.fromisoformat(item["created_at"])).days
            lines.append(
                f"[{i}] {item['content'][:150]}\n"
                f"    Category: {item['category']} | Stored: {age_days} days ago\n"
            )
        lines.append(
            "\nFor each item, say 'still true', 'update it to ...', or 'mark stale'."
        )
        return "\n".join(lines)

    def get_all_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Retrieve all non-stale memories in a category."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM memory_items
                   WHERE category = ? AND staleness_flag != 'stale'
                   ORDER BY created_at DESC""",
                (category,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"MemoryDecay.get_all_by_category error: {exc}")
            return []


# ── Global singleton ──────────────────────────────────────────────────────────

memory_decay = MemoryDecay()

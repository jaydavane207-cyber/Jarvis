"""
RelationshipCircles — contact grouping and tone calibration for JARVIS.

Organises Jay's contacts into explicit relationship circles:
  family | college | work | friends | professional

Each circle has a tone profile:
  • family     → warm, casual, caring
  • college    → friendly, informal, nostalgic
  • work       → professional, precise, efficient
  • friends    → relaxed, fun, personal
  • professional → formal, respectful, concise

When JARVIS detects a contact name in context, it automatically adapts
tone and information sharing depth based on the contact's circle.
"""
from __future__ import annotations
import logging
import os
import sqlite3
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "personal.db",
)

CIRCLE_TONES: Dict[str, str] = {
    "family": "warm, casual, and caring — like talking to close family",
    "college": "friendly, informal, and nostalgic — old friends energy",
    "work": "professional, precise, and efficient — work context",
    "friends": "relaxed, fun, and personal — among close friends",
    "professional": "formal, respectful, and concise — professional contact",
    "other": "neutral and helpful",
}


class RelationshipCircles:
    """Manages Jay's relationship circles and contact-to-circle mapping."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_tables()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS relationship_circles (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    name    TEXT    NOT NULL UNIQUE,
                    tone    TEXT    NOT NULL DEFAULT 'neutral and helpful',
                    notes   TEXT    DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS circle_members (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_name TEXT   NOT NULL,
                    circle_name  TEXT   NOT NULL,
                    notes        TEXT   DEFAULT '',
                    UNIQUE(contact_name, circle_name)
                );
            """)
            # Seed default circles
            for circle_name, tone in CIRCLE_TONES.items():
                conn.execute(
                    "INSERT OR IGNORE INTO relationship_circles (name, tone) VALUES (?, ?)",
                    (circle_name, tone),
                )
            conn.commit()
            conn.close()
            logger.info("RelationshipCircles: tables ready ✓")
        except Exception as exc:
            logger.error(f"RelationshipCircles._ensure_tables error: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_contact(self, name: str, circle: str, notes: str = "") -> str:
        """Add a contact to a circle. Returns confirmation."""
        circle_lower = circle.lower()
        if circle_lower not in CIRCLE_TONES:
            circle_lower = "other"
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO circle_members (contact_name, circle_name, notes) VALUES (?, ?, ?)",
                (name.strip(), circle_lower, notes),
            )
            conn.commit()
            conn.close()
            return f"✅ {name} added to '{circle_lower}' circle."
        except Exception as exc:
            logger.error(f"RelationshipCircles.add_contact error: {exc}")
            return f"❌ Failed to add {name}."

    def get_circle(self, contact_name: str) -> Optional[str]:
        """Get which circle a contact belongs to."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT circle_name FROM circle_members WHERE LOWER(contact_name) = LOWER(?)",
                (contact_name,),
            ).fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as exc:
            logger.error(f"RelationshipCircles.get_circle error: {exc}")
            return None

    def get_tone(self, contact_name: str) -> str:
        """Get the tone profile for a contact based on their circle."""
        circle = self.get_circle(contact_name)
        return CIRCLE_TONES.get(circle or "other", CIRCLE_TONES["other"])

    def build_tone_directive(self, contact_name: str) -> str:
        """Build a system prompt directive for the active contact's tone."""
        circle = self.get_circle(contact_name)
        if not circle:
            return ""
        tone = CIRCLE_TONES.get(circle, CIRCLE_TONES["other"])
        return (
            f"\n\nCONTACT CONTEXT: The current conversation involves {contact_name} "
            f"(relationship: {circle}). Adapt your tone to be {tone}. "
            f"Calibrate information sharing depth accordingly."
        )

    def get_members(self, circle: str) -> List[Dict[str, Any]]:
        """Get all members of a circle."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM circle_members WHERE circle_name = ? ORDER BY contact_name",
                (circle.lower(),),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"RelationshipCircles.get_members error: {exc}")
            return []

    def get_all_circles_summary(self) -> str:
        """Format all circles and members as readable text."""
        lines = ["🔵 Relationship Circles:\n"]
        for circle in CIRCLE_TONES:
            members = self.get_members(circle)
            if members:
                names = ", ".join(m["contact_name"] for m in members)
                lines.append(f"  {circle.title():15} → {names}")
        return "\n".join(lines) if len(lines) > 1 else "No contacts in any circle yet."

    def detect_contact_in_message(self, message: str, known_contacts: List[str]) -> Optional[str]:
        """Scan message for a known contact name."""
        msg_lower = message.lower()
        for name in known_contacts:
            if name.lower() in msg_lower:
                return name
        return None


# ── Global singleton ──────────────────────────────────────────────────────────

relationship_circles = RelationshipCircles()

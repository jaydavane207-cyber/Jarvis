"""
ContactStore — SQLite-backed persistence for JARVIS Contact Manager.

Tables:
  contacts     — name, phone, email, relationship, notes, timestamps
  interactions — per-contact log of calls/chats/meetings with summaries

All methods are synchronous (called from CommunicationAgent which wraps
them before yielding to the async stream).
"""
from __future__ import annotations

import sqlite3
import os
import logging
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ..security.crypto import crypto_manager

logger = logging.getLogger(__name__)

_DB_PATH = ".jarvis/contacts.db"


class ContactStore:
    """Manages contact records and interaction history in a local SQLite DB."""

    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _ensure_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        name         TEXT    NOT NULL,
                        phone        TEXT,
                        email        TEXT,
                        relationship TEXT,
                        notes        TEXT,
                        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interactions (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                        type       TEXT    NOT NULL DEFAULT 'general',
                        summary    TEXT    NOT NULL,
                        timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Full-text index for fast name search
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_contacts_name
                    ON contacts (name COLLATE NOCASE)
                """)

    # ── Contact CRUD ───────────────────────────────────────────────────────────

    def add_contact(
        self,
        name: str,
        phone: str = "",
        email: str = "",
        relationship: str = "",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Insert a new contact. Returns the newly created contact dict."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                cur = conn.execute(
                    """INSERT INTO contacts (name, phone, email, relationship, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, crypto_manager.encrypt(phone), crypto_manager.encrypt(email), relationship, crypto_manager.encrypt(notes)),
                )
                contact_id = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        logger.info(f"ContactStore: added contact #{contact_id} — {name}")
        d = dict(row)
        d['phone'] = crypto_manager.decrypt(d['phone'])
        d['email'] = crypto_manager.decrypt(d['email'])
        d['notes'] = crypto_manager.decrypt(d['notes'])
        return d

    def update_contact(
        self,
        contact_id: int,
        **fields,
    ) -> Optional[Dict[str, Any]]:
        """Update one or more fields of a contact. Returns updated record or None."""
        allowed = {"name", "phone", "email", "relationship", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_contact(contact_id)
        
        # Encrypt sensitive fields before updating
        if "phone" in updates:
            updates["phone"] = crypto_manager.encrypt(updates["phone"])
        if "email" in updates:
            updates["email"] = crypto_manager.encrypt(updates["email"])
        if "notes" in updates:
            updates["notes"] = crypto_manager.encrypt(updates["notes"])

        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [contact_id]

        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                conn.execute(
                    f"UPDATE contacts SET {set_clause} WHERE id = ?", values
                )
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        logger.info(f"ContactStore: updated contact #{contact_id}")
        if row:
            d = dict(row)
            d['phone'] = crypto_manager.decrypt(d['phone'])
            d['email'] = crypto_manager.decrypt(d['email'])
            d['notes'] = crypto_manager.decrypt(d['notes'])
            return d
        return None

    def delete_contact(self, contact_id: int) -> bool:
        """Delete a contact and all their interactions. Returns True if deleted."""
        with closing(self._connect()) as conn:
            with conn:
                cur = conn.execute(
                    "DELETE FROM contacts WHERE id = ?", (contact_id,)
                )
        deleted = cur.rowcount > 0
        logger.info(f"ContactStore: delete contact #{contact_id} → {deleted}")
        return deleted

    def get_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a contact by ID. Returns None if not found."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        if row:
            d = dict(row)
            d['phone'] = crypto_manager.decrypt(d['phone'])
            d['email'] = crypto_manager.decrypt(d['email'])
            d['notes'] = crypto_manager.decrypt(d['notes'])
            return d
        return None

    def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Case-insensitive search across name, email, phone, relationship."""
        # Searching across encrypted fields won't work correctly with LIKE %query% directly in SQL. 
        # So we fetch all and filter in python.
        all_contacts = self.list_all()
        q = query.lower()
        results = []
        for c in all_contacts:
            if q in c['name'].lower() or \
               (c['email'] and q in c['email'].lower()) or \
               (c['phone'] and q in c['phone'].lower()) or \
               (c['relationship'] and q in c['relationship'].lower()):
                results.append(c)
        return results

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all contacts ordered alphabetically by name."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY name COLLATE NOCASE"
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d['phone'] = crypto_manager.decrypt(d['phone'])
            d['email'] = crypto_manager.decrypt(d['email'])
            d['notes'] = crypto_manager.decrypt(d['notes'])
            results.append(d)
        return results

    def get_dormant_contacts(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return important contacts (clients, friends) with no interactions in the last X days."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            # We want contacts where their latest interaction is older than `days`, 
            # OR they have no interactions at all but were created older than `days`.
            rows = conn.execute(
                """
                SELECT c.* 
                FROM contacts c
                LEFT JOIN (
                    SELECT contact_id, MAX(timestamp) as last_interaction
                    FROM interactions
                    GROUP BY contact_id
                ) i ON c.id = i.contact_id
                WHERE (c.relationship LIKE '%client%' OR c.relationship LIKE '%friend%')
                  AND (
                    (i.last_interaction IS NULL AND datetime(c.created_at) < datetime('now', '-' || ? || ' days'))
                    OR 
                    (i.last_interaction IS NOT NULL AND datetime(i.last_interaction) < datetime('now', '-' || ? || ' days'))
                  )
                """,
                (str(days), str(days))
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d['phone'] = crypto_manager.decrypt(d['phone'])
            d['email'] = crypto_manager.decrypt(d['email'])
            d['notes'] = crypto_manager.decrypt(d['notes'])
            results.append(d)
        return results

    # ── Interaction history ────────────────────────────────────────────────────

    def add_interaction(
        self,
        contact_id: int,
        summary: str,
        interaction_type: str = "general",
    ) -> Dict[str, Any]:
        """Log an interaction for a contact. Returns the new interaction dict."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                cur = conn.execute(
                    """INSERT INTO interactions (contact_id, type, summary)
                       VALUES (?, ?, ?)""",
                    (contact_id, interaction_type, crypto_manager.encrypt(summary)),
                )
                iid = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM interactions WHERE id = ?", (iid,)
            ).fetchone()
        logger.info(
            f"ContactStore: logged interaction #{iid} for contact #{contact_id}"
        )
        d = dict(row)
        d['summary'] = crypto_manager.decrypt(d['summary'])
        return d

    def get_interactions(
        self, contact_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Return most recent interactions for a contact, newest first."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM interactions WHERE contact_id = ?
                   ORDER BY timestamp DESC, id DESC LIMIT ?""",
                (contact_id, limit),
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d['summary'] = crypto_manager.decrypt(d['summary'])
            results.append(d)
        return results

    # ── Formatting helpers ─────────────────────────────────────────────────────

    def format_contact(self, c: Dict[str, Any], include_interactions: bool = False) -> str:
        """Return a human-readable contact card string."""
        lines = [
            f"📇 **{c['name']}** (ID: {c['id']})",
        ]
        if c.get("phone"):
            lines.append(f"  📞 {c['phone']}")
        if c.get("email"):
            lines.append(f"  ✉️  {c['email']}")
        if c.get("relationship"):
            lines.append(f"  🤝 {c['relationship']}")
        if c.get("notes"):
            lines.append(f"  📝 {c['notes']}")
        lines.append(f"  🕐 Added: {c.get('created_at', 'unknown')}")

        if include_interactions:
            interactions = self.get_interactions(c["id"], limit=5)
            if interactions:
                lines.append("\n  **Recent interactions:**")
                for i in interactions:
                    lines.append(
                        f"  • [{i['type'].upper()}] {i['timestamp'][:16]} — {i['summary']}"
                    )

        return "\n".join(lines)

    def format_list(self, contacts: List[Dict[str, Any]]) -> str:
        """Format a list of contacts as a compact directory."""
        if not contacts:
            return "No contacts found."
        lines = [f"📋 **Contact Directory** ({len(contacts)} contacts)\n"]
        for c in contacts:
            rel = f" ({c['relationship']})" if c.get("relationship") else ""
            email = f" — {c['email']}" if c.get("email") else ""
            phone = f" | {c['phone']}" if c.get("phone") else ""
            lines.append(f"• **{c['name']}**{rel}{email}{phone}  _(ID: {c['id']})_")
        return "\n".join(lines)

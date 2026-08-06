"""
ProtocolAgent — proactive Morning and Evening briefings for JARVIS.

Morning Protocol (fires at configured time, default 07:30 IST):
  • Persistent last-sent tracking in personal.db
  • Weekday vs Weekend awareness (omits stock digest on Sat/Sun)
  • Overnight trading signals via signal_store
  • Today's pending reminders via reminder_store
  • LLM synthesis with graceful fallback template if LLM fails
  • History logging in personal.db morning_briefings table
  • Missed-briefing catch-up logic (7:30 AM - 18:00 IST)

Evening Wind-Down (fires at configured time, default 21:00 IST):
  • Tomorrow's calendar / prep summary
  • Market close summary
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List

from ..config import settings
from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.kill_switch import kill_switch
from ..safety.audit_log import audit_log

logger = logging.getLogger(__name__)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "personal.db"))


class ProtocolAgent:
    """Manages proactive scheduled briefings for Jay."""

    DEFAULT_MORNING_TIME = time(7, 30)   # 07:30 IST
    DEFAULT_EVENING_TIME = time(21, 0)   # 21:00 IST

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._morning_time = self._parse_configured_time(
            getattr(settings, "morning_protocol_time", "07:30"), self.DEFAULT_MORNING_TIME
        )
        self._evening_time = self._parse_configured_time(
            getattr(settings, "evening_protocol_time", "21:00"), self.DEFAULT_EVENING_TIME
        )
        self._anomaly_false_positives_this_week = 0
        self._last_anomaly_week: Optional[int] = None

    def _parse_configured_time(self, val_str: str, default_t: time) -> time:
        try:
            parts = val_str.strip().split(":")
            return time(int(parts[0]), int(parts[1]))
        except Exception:
            return default_t

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS briefing_tracking (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS morning_briefings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT UNIQUE NOT NULL,
                        narrative TEXT NOT NULL,
                        signals_json TEXT,
                        reminders_json TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception as exc:
            logger.error(f"ProtocolAgent DB init error: {exc}")

    # ── Persistence Helpers (#1, #7) ─────────────────────────────────────────

    def get_last_morning_date(self) -> Optional[str]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM briefing_tracking WHERE key = 'last_morning_date'")
                row = cursor.fetchone()
                return row["value"] if row else None
        except Exception as exc:
            logger.error(f"Error fetching last morning date: {exc}")
            return None

    def set_last_morning_date(self, date_str: str):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO briefing_tracking (key, value) VALUES ('last_morning_date', ?)",
                    (date_str,)
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"Error setting last morning date: {exc}")

    def save_briefing_history(self, date_str: str, narrative: str, signals: list, reminders: list):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO morning_briefings (date, narrative, signals_json, reminders_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (date_str, narrative, json.dumps(signals), json.dumps(reminders), datetime.now().isoformat())
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"Error saving briefing history: {exc}")

    def get_briefing_by_date(self, date_str: str) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM morning_briefings WHERE date = ?", (date_str,))
                row = cursor.fetchone()
                if row:
                    return {
                        "date": row["date"],
                        "narrative": row["narrative"],
                        "signals": json.loads(row["signals_json"] or "[]"),
                        "reminders": json.loads(row["reminders_json"] or "[]"),
                        "created_at": row["created_at"],
                    }
        except Exception as exc:
            logger.error(f"Error reading briefing for date {date_str}: {exc}")
        return None

    def get_latest_briefing(self) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM morning_briefings ORDER BY date DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return {
                        "date": row["date"],
                        "narrative": row["narrative"],
                        "signals": json.loads(row["signals_json"] or "[]"),
                        "reminders": json.loads(row["reminders_json"] or "[]"),
                        "created_at": row["created_at"],
                    }
        except Exception as exc:
            logger.error(f"Error reading latest briefing: {exc}")
        return None

    # ── Catch-up & Trigger Evaluation (#3) ───────────────────────────────────

    def should_trigger_morning(self, now_dt: datetime) -> bool:
        """Determines if a morning briefing should be delivered for now_dt."""
        today_str = now_dt.date().isoformat()
        last_sent = self.get_last_morning_date()
        if last_sent == today_str:
            return False

        current_time = now_dt.time()
        # Scheduled time match (or within current minute window)
        if current_time.hour == self._morning_time.hour and current_time.minute == self._morning_time.minute:
            return True

        # Missed briefing catch-up window: between morning_time and 18:00 IST
        cutoff_time = time(18, 0)
        if self._morning_time <= current_time < cutoff_time:
            return True

        return False

    # ── Data Gatherers with Fallbacks (#2, #5) ─────────────────────────────────

    def _fetch_overnight_trading_signals(self) -> List[Dict[str, Any]]:
        """Fetch trading signals generated since yesterday 15:30 IST."""
        try:
            from .signal_store import signal_store
            recent = signal_store.get_recent_signals(limit=20)
            cutoff = datetime.now() - timedelta(hours=24)
            filtered = []
            for s in recent:
                ts_str = s.get("created_at") or ""
                try:
                    dt = datetime.fromisoformat(ts_str)
                    if dt >= cutoff:
                        filtered.append(s)
                except Exception:
                    filtered.append(s)
            return filtered
        except Exception as exc:
            logger.error(f"Error fetching trading signals for briefing: {exc}")
            return []

    def _get_todays_reminders_list(self) -> List[str]:
        """Get today's pending reminder texts."""
        try:
            from ..memory.reminder_store import ReminderStore
            store = ReminderStore()
            reminders = store.get_pending_reminders()
            today_str = datetime.now().date().isoformat()
            today_rems = []
            for r in reminders:
                fa = r.get("fire_at") or ""
                if fa.startswith(today_str) or r.get("status") == "pending":
                    today_rems.append(r.get("text", ""))
            return today_rems
        except Exception as exc:
            logger.error(f"Error fetching reminders for briefing: {exc}")
            return []

    def _get_calendar_status(self) -> str:
        return "Google Calendar integration pending (dependency gap)."

    # ── Public Briefing Generation API ───────────────────────────────────────

    async def morning_briefing(self, llm: OllamaClient, voice_mode: str = "calm_male") -> Dict[str, Any]:
        """Generate structured Morning Protocol briefing payload."""
        now = datetime.now()
        today_str = now.date().isoformat()
        is_weekend = (now.weekday() >= 5)  # Sat=5, Sun=6 (#5)

        logger.info(f"ProtocolAgent: generating Morning Briefing (is_weekend={is_weekend})")

        # 1. Gather data safely with fallbacks (#2)
        signals = [] if is_weekend else self._fetch_overnight_trading_signals()
        reminders = self._get_todays_reminders_list()
        calendar_note = self._get_calendar_status()

        # 2. Build narrative prompt
        prompt = (
            f"Today is {now.strftime('%A, %d %B %Y')}. Time: {now.strftime('%I:%M %p')} IST.\n"
            f"Day type: {'Weekend (NSE/BSE Closed)' if is_weekend else 'Weekday'}.\n\n"
            f"Overnight Trading Signals: {len(signals)} available.\n"
            f"Pending Reminders: {len(reminders)} items ({', '.join(reminders[:3]) if reminders else 'None'}).\n"
            f"Calendar Note: {calendar_note}\n\n"
            "Deliver a warm, concise morning briefing for Jay in 2 short, plain spoken sentences. "
            "Do not use markdown formatting."
        )

        system = (
            get_jarvis_system_prompt(voice_mode)
            + "\n\nFor this request, you are delivering the MORNING PROTOCOL briefing. "
            "Be energetic, professional, and brief. Keep it under 2 plain spoken sentences."
        )

        # 3. LLM narrative call with fallback (#2)
        narrative = ""
        try:
            messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
            narrative = llm.chat(messages)
        except Exception as exc:
            logger.error(f"LLM narrative generation error: {exc}. Using fallback template.")
            if is_weekend:
                narrative = f"Good morning Jay. Happy weekend! You have {len(reminders)} pending reminder(s) for today."
            else:
                narrative = f"Good morning Jay. Systems are online. You have {len(reminders)} reminder(s) and {len(signals)} overnight trading signal(s)."

        if not narrative or len(narrative.strip()) == 0:
            narrative = f"Good morning Jay. You have {len(reminders)} reminder(s) today."

        # 4. Save persistence & history (#1, #7)
        self.save_briefing_history(today_str, narrative, signals, reminders)
        self.set_last_morning_date(today_str)

        audit_log.record(
            agent="ProtocolAgent",
            action_type="morning_briefing",
            details=f"Morning Protocol delivered for {today_str}",
            reasoning="Scheduled or catch-up morning trigger",
            tier="read_only",
            approved=0,
        )

        return {
            "date": today_str,
            "is_weekend": is_weekend,
            "narrative": narrative,
            "signals": signals,
            "reminders": reminders,
            "calendar_status": calendar_note,
        }

    async def evening_briefing(self, llm: OllamaClient, voice_mode: str = "calm_male") -> str:
        """Generate the evening wind-down briefing text."""
        logger.info("ProtocolAgent: generating Evening Briefing")

        market_close = await self._fetch_market_close()
        prompt = f"Today is {datetime.now().strftime('%A, %d %B %Y')}.\nMarket Close:\n{market_close}\nDeliver evening wind-down."
        system = get_jarvis_system_prompt(voice_mode) + "\nDeliver a calm 2-sentence evening wind-down."
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]

        try:
            return llm.chat(messages)
        except Exception as exc:
            logger.error(f"Evening briefing LLM error: {exc}")
            return "Good evening Jay. Systems are running nominal. Have a restful night."

    async def _fetch_market_close(self) -> str:
        return "NSE/BSE EOD digest logged."

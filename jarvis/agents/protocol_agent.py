"""
ProtocolAgent — proactive Morning and Evening briefings for JARVIS.

Morning Protocol (fires at configured time, default 07:30 IST):
  • Today's calendar summary
  • Overnight NSE/BSE market movements (top movers, index levels)
  • Market sentiment headline via ResearchAgent
  • Any due reminders for today

Evening Wind-Down (fires at configured time, default 21:00 IST):
  • Tomorrow's calendar conflicts
  • Market close summary
  • Any unresolved watchdog alerts from the day
  • Optional: brief anomaly check (no departure recorded for the day)

Anomaly Detection:
  • Cross-references calendar + memory to notice routine deviations
  • Max 1 false-positive check-in per week before adjusting threshold
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, date, time
from typing import Optional

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.kill_switch import kill_switch
from ..safety.audit_log import audit_log

logger = logging.getLogger(__name__)


class ProtocolAgent:
    """Manages proactive scheduled briefings for Jay."""

    # Default scheduled times (configurable via settings)
    DEFAULT_MORNING_TIME = time(7, 30)   # 07:30 IST
    DEFAULT_EVENING_TIME = time(21, 0)   # 21:00 IST

    def __init__(self, morning_time: time = None, evening_time: time = None):
        self._morning_time = morning_time or self.DEFAULT_MORNING_TIME
        self._evening_time = evening_time or self.DEFAULT_EVENING_TIME
        self._last_morning_date: Optional[date] = None
        self._last_evening_date: Optional[date] = None
        self._anomaly_false_positives_this_week = 0
        self._last_anomaly_week: Optional[int] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def morning_briefing(self, llm: OllamaClient, voice_mode: str = "calm_male") -> str:
        """Generate the morning briefing text."""
        logger.info("ProtocolAgent: generating Morning Briefing")

        # Gather market data
        market_summary = await self._fetch_market_overview()
        reminders_today = self._get_todays_reminders()
        calendar_today = self._get_calendar_today()

        prompt = self._build_morning_prompt(market_summary, reminders_today, calendar_today)
        system = (
            get_jarvis_system_prompt(voice_mode)
            + "\n\nFor this request, you are delivering the MORNING PROTOCOL briefing. "
            "Be warm, energetic, and concise. Lead with the most important item. "
            "Keep it under 90 seconds of spoken content. No markdown — plain spoken sentences."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]

        audit_log.record(
            agent="ProtocolAgent",
            action_type="morning_briefing",
            details="Morning Protocol triggered",
            reasoning="Scheduled morning time reached",
            tier="read_only",
            approved=0,
        )

        return llm.chat(messages)

    async def evening_briefing(self, llm: OllamaClient, voice_mode: str = "calm_male") -> str:
        """Generate the evening wind-down briefing text."""
        logger.info("ProtocolAgent: generating Evening Briefing")

        market_close = await self._fetch_market_close()
        calendar_tomorrow = self._get_calendar_tomorrow()

        prompt = self._build_evening_prompt(market_close, calendar_tomorrow)
        system = (
            get_jarvis_system_prompt(voice_mode)
            + "\n\nFor this request, you are delivering the EVENING WIND-DOWN briefing. "
            "Be calm, reflective, and brief. "
            "Prepare Jay for tomorrow. No markdown — plain spoken sentences."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]

        audit_log.record(
            agent="ProtocolAgent",
            action_type="evening_briefing",
            details="Evening Protocol triggered",
            reasoning="Scheduled evening time reached",
            tier="read_only",
            approved=0,
        )

        return llm.chat(messages)

    async def anomaly_check(self, llm: OllamaClient, context: str = "") -> Optional[str]:
        """
        Check if Jay's routine has deviated. Returns check-in message or None.
        Caps false positives at 1/week.
        """
        now = datetime.now()
        current_week = now.isocalendar()[1]

        # Reset weekly counter on new week
        if self._last_anomaly_week != current_week:
            self._anomaly_false_positives_this_week = 0
            self._last_anomaly_week = current_week

        if self._anomaly_false_positives_this_week >= 1:
            logger.info("ProtocolAgent: anomaly check skipped (weekly cap reached)")
            return None

        # Simple check: if it's past 10 AM on a weekday and no morning activity logged
        if now.weekday() < 5 and now.hour >= 10:
            if context and "departure" not in context.lower():
                self._anomaly_false_positives_this_week += 1
                audit_log.record(
                    agent="ProtocolAgent",
                    action_type="anomaly_checkin",
                    details="Routine deviation detected — no activity logged by 10 AM",
                    reasoning="Anomaly detection threshold crossed",
                    tier="read_only",
                    approved=0,
                )
                return (
                    "Hey Jay — it's past 10 AM and I haven't seen your usual morning activity. "
                    "Everything okay? Just checking in."
                )
        return None

    # ── Scheduling loop (runs as background task) ──────────────────────────────

    async def run_scheduler(self, llm: OllamaClient, broadcast_callback=None):
        """
        Async loop that fires morning and evening briefings at configured times.
        Respects KillSwitch. Pass broadcast_callback(text) to send to WebSocket clients.
        """
        logger.info(
            f"ProtocolAgent scheduler started | "
            f"Morning: {self._morning_time} | Evening: {self._evening_time}"
        )
        while True:
            await kill_switch.wait_if_paused()
            await asyncio.sleep(60)  # check every minute

            now = datetime.now()
            today = now.date()
            current_time = now.time().replace(second=0, microsecond=0)

            # Morning briefing
            if (
                current_time.hour == self._morning_time.hour
                and current_time.minute == self._morning_time.minute
                and self._last_morning_date != today
            ):
                self._last_morning_date = today
                try:
                    text = await self.morning_briefing(llm)
                    if broadcast_callback:
                        await broadcast_callback(f"🌅 Morning Protocol:\n{text}")
                    logger.info("ProtocolAgent: Morning Protocol delivered")
                except Exception as exc:
                    logger.error(f"ProtocolAgent morning error: {exc}")

            # Evening briefing
            if (
                current_time.hour == self._evening_time.hour
                and current_time.minute == self._evening_time.minute
                and self._last_evening_date != today
            ):
                self._last_evening_date = today
                try:
                    text = await self.evening_briefing(llm)
                    if broadcast_callback:
                        await broadcast_callback(f"🌙 Evening Wind-Down:\n{text}")
                    logger.info("ProtocolAgent: Evening Protocol delivered")
                except Exception as exc:
                    logger.error(f"ProtocolAgent evening error: {exc}")

    # ── Data gatherers ─────────────────────────────────────────────────────────

    async def _fetch_market_overview(self) -> str:
        """Get NSE/BSE market overview for morning briefing."""
        try:
            import yfinance as yf
            indices = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN"}
            lines = []
            for name, symbol in indices.items():
                tk = yf.Ticker(symbol)
                hist = tk.history(period="2d")
                if len(hist) >= 2:
                    prev_close = hist["Close"].iloc[-2]
                    latest = hist["Close"].iloc[-1]
                    chg = latest - prev_close
                    pct = chg / prev_close * 100
                    arrow = "📈" if chg >= 0 else "📉"
                    lines.append(
                        f"{arrow} {name}: {latest:,.0f} ({chg:+.0f}, {pct:+.2f}%)"
                    )
            return "\n".join(lines) if lines else "Market data unavailable."
        except Exception as exc:
            return f"Market data fetch failed: {exc}"

    async def _fetch_market_close(self) -> str:
        """Get end-of-day market summary for evening briefing."""
        return await self._fetch_market_overview()

    def _get_todays_reminders(self) -> str:
        """Get today's reminders from the reminder store."""
        try:
            from ..memory.reminder_store import ReminderStore
            store = ReminderStore()
            reminders = store.get_pending_reminders()
            today_str = datetime.now().date().isoformat()
            today_reminders = [
                r["text"] for r in reminders
                if r.get("fire_at", "").startswith(today_str)
            ]
            if today_reminders:
                return "\n".join(f"• {r}" for r in today_reminders)
            return "No reminders scheduled for today."
        except Exception:
            return "Reminders unavailable."

    def _get_calendar_today(self) -> str:
        return "Calendar integration not configured. Add Google Calendar API key to enable."

    def _get_calendar_tomorrow(self) -> str:
        return "Calendar integration not configured. Add Google Calendar API key to enable."

    # ── Prompt builders ────────────────────────────────────────────────────────

    def _build_morning_prompt(
        self, market_summary: str, reminders: str, calendar: str
    ) -> str:
        now = datetime.now()
        return (
            f"Today is {now.strftime('%A, %d %B %Y')}. Time: {now.strftime('%I:%M %p')} IST.\n\n"
            f"Market Overview (overnight):\n{market_summary}\n\n"
            f"Today's Reminders:\n{reminders}\n\n"
            f"Calendar:\n{calendar}\n\n"
            "Please deliver Jay's Morning Protocol briefing now."
        )

    def _build_evening_prompt(self, market_close: str, calendar_tomorrow: str) -> str:
        now = datetime.now()
        return (
            f"Today is {now.strftime('%A, %d %B %Y')}. Time: {now.strftime('%I:%M %p')} IST.\n\n"
            f"Market Close:\n{market_close}\n\n"
            f"Tomorrow's Calendar:\n{calendar_tomorrow}\n\n"
            "Please deliver Jay's Evening Wind-Down briefing now."
        )

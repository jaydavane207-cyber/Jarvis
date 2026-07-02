import re
from datetime import datetime, timedelta
from ..memory.reminder_store import ReminderStore
import logging

logger = logging.getLogger(__name__)


class ReminderAgent:
    """Handles natural language reminder commands and stores them in SQLite."""

    def __init__(self):
        self.store = ReminderStore()

    def handle(self, message: str) -> str:
        """Synchronous reminder handler called by AgentRouter.route()."""
        msg_lower = message.lower()

        # ── List upcoming reminders ──────────────────────────────────────────
        if any(k in msg_lower for k in [
            "what are my reminder", "show reminder", "list reminder",
            "upcoming reminder", "my reminder", "do i have any reminder"
        ]):
            return self._list_reminders()

        # ── Cancel / clear all ───────────────────────────────────────────────
        elif any(k in msg_lower for k in [
            "cancel all", "clear all reminder", "delete all reminder",
            "remove all reminder", "cancel reminder"
        ]):
            self.store.clear_all_pending()
            return "Very well, Jay. All pending reminders have been cancelled."

        # ── Parse a new reminder ─────────────────────────────────────────────
        else:
            fire_at = self._parse_time(message)
            if fire_at:
                reminder_text = self._extract_reminder_text(message)
                rid = self.store.add_reminder(reminder_text, fire_at)
                time_str = fire_at.strftime("%I:%M %p")
                delta = fire_at - datetime.now()
                total_seconds = int(delta.total_seconds())
                if total_seconds < 3600:
                    delta_str = f"in {total_seconds // 60} minute(s)"
                else:
                    delta_str = f"in {total_seconds // 3600} hour(s)"
                return (
                    f"Understood, Jay. I've set a reminder to \"{reminder_text}\" "
                    f"at {time_str} ({delta_str}). Reminder #{rid} is active."
                )
            else:
                return (
                    "I wasn't able to determine the time for that reminder, Jay. "
                    "Try phrases like:\n"
                    "  • \"Remind me in 10 minutes to take a break\"\n"
                    "  • \"Remind me at 6 PM to call mom\"\n"
                    "  • \"Set a timer for 30 minutes to check the oven\""
                )

    async def handle_stream(self, message: str):
        msg_lower = message.lower()
        reply = ""

        # ── List upcoming reminders ──────────────────────────────────────────
        if any(k in msg_lower for k in [
            "what are my reminder", "show reminder", "list reminder",
            "upcoming reminder", "my reminder", "do i have any reminder"
        ]):
            reply = self._list_reminders()

        # ── Cancel / clear all ───────────────────────────────────────────────
        elif any(k in msg_lower for k in [
            "cancel all", "clear all reminder", "delete all reminder",
            "remove all reminder", "cancel reminder"
        ]):
            self.store.clear_all_pending()
            reply = "Very well, Jay. All pending reminders have been cancelled."

        # ── Parse a new reminder ─────────────────────────────────────────────
        else:
            fire_at = self._parse_time(message)
            if fire_at:
                reminder_text = self._extract_reminder_text(message)
                rid = self.store.add_reminder(reminder_text, fire_at)
                time_str = fire_at.strftime("%I:%M %p")
                delta = fire_at - datetime.now()
                total_seconds = int(delta.total_seconds())
                if total_seconds < 3600:
                    delta_str = f"in {total_seconds // 60} minute(s)"
                else:
                    delta_str = f"in {total_seconds // 3600} hour(s)"
                reply = (
                    f"Understood, Jay. I've set a reminder to \"{reminder_text}\" "
                    f"at {time_str} ({delta_str}). Reminder #{rid} is active."
                )

            # ── Could not parse ──────────────────────────────────────────────────
            else:
                reply = (
                    "I wasn't able to determine the time for that reminder, Jay. "
                    "Try phrases like:\n"
                    "  • \"Remind me in 10 minutes to take a break\"\n"
                    "  • \"Remind me at 6 PM to call mom\"\n"
                    "  • \"Set a timer for 30 minutes to check the oven\""
                )
        
        yield reply


    # ── Time Parser ──────────────────────────────────────────────────────────

    def _parse_time(self, text: str) -> datetime | None:
        now = datetime.now()
        text_lower = text.lower()

        # Pattern: "in X seconds/minutes/hours" OR "for X seconds/minutes/hours"
        m = re.search(
            r'\b(?:in|for)\s+(\d+)\s+(seconds?|minutes?|hours?|mins?|secs?|hrs?)\b',
            text_lower
        )
        if m:
            amount = int(m.group(1))
            unit = m.group(2).rstrip('s')  # normalise: 'seconds' → 'second', 'minutes' → 'minute'
            if unit in ('second', 'sec'):
                return now + timedelta(seconds=amount)
            elif unit in ('minute', 'min'):
                return now + timedelta(minutes=amount)
            elif unit in ('hour', 'hr'):
                return now + timedelta(hours=amount)

        # Pattern: "tomorrow at ..."
        if 'tomorrow' in text_lower:
            m = re.search(r'tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text_lower)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                ampm = m.group(3)
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                fire_at = (now + timedelta(days=1)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                return fire_at

        # Pattern: "at H:MM AM/PM", "at H AM/PM", "at HH:MM" (24h)
        m = re.search(
            r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',
            text_lower
        )
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            ampm = m.group(3)
            if ampm == 'pm' and hour != 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            fire_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If time has already passed today, schedule for tomorrow
            if fire_at <= now:
                fire_at += timedelta(days=1)
            return fire_at

        return None

    # ── Reminder Text Extractor ──────────────────────────────────────────────

    def _extract_reminder_text(self, text: str) -> str:
        """Extract what the user wants to be reminded about."""
        # Remove "remind me" / "set a reminder" preamble
        cleaned = re.sub(
            r'(?:remind\s+me|set\s+(?:a\s+)?(?:reminder|alarm|timer))\s*',
            '', text, flags=re.IGNORECASE
        ).strip()

        # Remove leading time phrase: "in 10 minutes to ..." → "to ..."
        cleaned = re.sub(
            r'^in\s+\d+\s+\w+\s+', '', cleaned, flags=re.IGNORECASE
        ).strip()

        # Remove trailing time phrase: "... at 6 PM" or "... in 10 minutes"
        cleaned = re.sub(
            r'\s+(?:in\s+\d+\s+\w+|at\s+\d+(?::\d+)?\s*(?:am|pm)?)\s*$',
            '', cleaned, flags=re.IGNORECASE
        ).strip()

        # Remove leading "to "
        cleaned = re.sub(r'^to\s+', '', cleaned, flags=re.IGNORECASE).strip(' ,.')

        return cleaned if len(cleaned) > 1 else text

    # ── Reminder List Formatter ──────────────────────────────────────────────

    def _list_reminders(self) -> str:
        upcoming = self.store.get_all_upcoming()
        if not upcoming:
            return "You have no upcoming reminders, Jay."
        lines = [f"You have {len(upcoming)} upcoming reminder(s), Jay:"]
        for r in upcoming:
            try:
                fire_time = datetime.strptime(r['fire_at'], "%Y-%m-%d %H:%M:%S")
                time_str = fire_time.strftime("%I:%M %p")
            except Exception:
                time_str = r['fire_at']
            lines.append(f"  • [{time_str}] {r['text']}")
        return "\n".join(lines)

"""
KillSwitch — emergency pause for all JARVIS background agents.

A single command (voice or REST) immediately:
  - Sets the global paused flag
  - Signals all watchdog tasks to stop their polling loops
  - Prevents the ExecutorAgent from running any new code
  - Logs the kill action to AuditLog

Resume is equally instant. Both operations take effect within seconds.

Usage:
    from jarvis.safety.kill_switch import kill_switch

    kill_switch.pause(reason="User triggered emergency stop")
    kill_switch.is_paused   # True
    kill_switch.resume()
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class KillSwitch:
    """
    Global singleton that controls the run/pause state of all
    background JARVIS agents and watchdogs.
    """

    def __init__(self):
        self._paused: bool = False
        self._paused_at: Optional[str] = None
        self._pause_reason: Optional[str] = None
        self._resume_event = asyncio.Event()
        self._resume_event.set()          # initially running
        self._watchdog_tasks: list = []   # asyncio.Task references

    # ── Control API ───────────────────────────────────────────────────────────

    def pause(self, reason: str = "Kill switch activated") -> None:
        """
        Immediately pause all background agents and watchdogs.
        Takes effect synchronously — next polling cycle in every watchdog
        will see the flag and exit or sleep.
        """
        if not self._paused:
            self._paused = True
            self._paused_at = datetime.now().isoformat()
            self._pause_reason = reason
            self._resume_event.clear()
            logger.warning(f"🛑 KILL SWITCH ACTIVATED: {reason}")
            # Attempt to write to audit log (import lazily to avoid circular deps)
            try:
                from .audit_log import audit_log
                audit_log.record(
                    agent="KillSwitch",
                    action_type="pause_all",
                    details=f"All background agents paused. Reason: {reason}",
                    reasoning=reason,
                    tier="execute_with_confirmation",
                    approved=1,
                    result="Paused ✓",
                )
            except Exception:
                pass

    def resume(self) -> None:
        """Resume all background agents."""
        if self._paused:
            self._paused = False
            reason = self._pause_reason
            self._paused_at = None
            self._pause_reason = None
            self._resume_event.set()
            logger.info("✅ KILL SWITCH RELEASED — all agents resuming")
            try:
                from .audit_log import audit_log
                audit_log.record(
                    agent="KillSwitch",
                    action_type="resume_all",
                    details=f"All background agents resumed (was paused: {reason})",
                    reasoning="User issued resume command",
                    tier="execute_with_confirmation",
                    approved=1,
                    result="Resumed ✓",
                )
            except Exception:
                pass

    def toggle(self) -> str:
        """Toggle pause/resume. Returns current state string."""
        if self._paused:
            self.resume()
            return "resumed"
        else:
            self.pause(reason="Manual toggle")
            return "paused"

    # ── Async helpers for watchdogs ────────────────────────────────────────────

    async def wait_if_paused(self) -> None:
        """
        Await this inside any watchdog loop iteration.
        Blocks until kill switch is released.
        """
        if self._paused:
            logger.info("KillSwitch: watchdog sleeping — waiting for resume...")
            await self._resume_event.wait()

    def check(self) -> bool:
        """Synchronous check. Returns True if operations are allowed."""
        return not self._paused

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def is_paused(self) -> bool:
        return self._paused

    def status(self) -> dict:
        return {
            "paused": self._paused,
            "paused_at": self._paused_at,
            "pause_reason": self._pause_reason,
        }

    def status_text(self) -> str:
        if self._paused:
            return (
                f"🛑 JARVIS is paused. All background agents are stopped.\n"
                f"  Reason : {self._pause_reason}\n"
                f"  Since  : {self._paused_at}\n"
                f"  Say 'JARVIS resume' or POST /kill-switch/resume to restart."
            )
        return "✅ JARVIS is running normally. All agents are active."


# ── Global singleton ──────────────────────────────────────────────────────────

kill_switch = KillSwitch()

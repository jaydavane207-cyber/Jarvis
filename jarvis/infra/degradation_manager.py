"""
DegradationManager — graceful offline/degraded mode for JARVIS.

Defines what JARVIS can do offline (Ollama) vs online (Claude API):

OFFLINE (Ollama available):
  ✅ Smart home control (Home Assistant)
  ✅ Basic Q&A and conversation
  ✅ Reminder management
  ✅ Memory read (SQLite + ChromaDB)
  ✅ Executor (local code execution)
  ✅ Budget tracking (local SQLite)

ONLINE-ONLY (requires Claude API / internet):
  🌐 Web Research (DuckDuckGo)
  🌐 Trading analysis with live market data
  🌐 Earnings report ingestion (PDF download)
  🌐 Scam URL checking (VirusTotal)
  🌐 Morning/Evening Protocol (full market data)

On API failure, automatically switches affected agents to Ollama with
capability warning messages to Jay.
"""
from __future__ import annotations
import logging
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CapabilityMode(str, Enum):
    FULL = "full"           # Claude API + Internet
    DEGRADED = "degraded"   # Ollama only, no internet
    OFFLINE = "offline"     # No LLM at all (emergency fallback)


# Capability map — which mode each feature requires
CAPABILITY_MAP: Dict[str, CapabilityMode] = {
    "conversation":   CapabilityMode.DEGRADED,   # works on Ollama
    "smart_home":     CapabilityMode.DEGRADED,
    "reminders":      CapabilityMode.DEGRADED,
    "memory_read":    CapabilityMode.DEGRADED,
    "executor":       CapabilityMode.DEGRADED,
    "budget":         CapabilityMode.DEGRADED,
    "planning":       CapabilityMode.DEGRADED,
    "coding":         CapabilityMode.DEGRADED,
    "research":       CapabilityMode.FULL,
    "trading":        CapabilityMode.FULL,
    "earnings":       CapabilityMode.FULL,
    "scam_url_check": CapabilityMode.FULL,
    "protocol":       CapabilityMode.FULL,
    "watchdog":       CapabilityMode.FULL,
}


class DegradationManager:
    """Monitors API health and manages graceful degradation."""

    def __init__(self):
        self._current_mode = CapabilityMode.FULL
        self._last_check: Optional[datetime] = None
        self._failure_reason: Optional[str] = None
        self._consecutive_failures = 0

    # ── Mode management ────────────────────────────────────────────────────────

    def set_mode(self, mode: CapabilityMode, reason: str = "") -> None:
        if mode != self._current_mode:
            logger.warning(f"DegradationManager: switching to {mode.value} mode. Reason: {reason}")
            self._current_mode = mode
            self._failure_reason = reason

    def record_api_success(self) -> None:
        self._consecutive_failures = 0
        if self._current_mode == CapabilityMode.DEGRADED:
            self.set_mode(CapabilityMode.FULL, "API recovered")

    def record_api_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        self._last_check = datetime.now()
        if self._consecutive_failures >= 3:
            self.set_mode(
                CapabilityMode.DEGRADED,
                f"Claude API unavailable after {self._consecutive_failures} failures: {exc}",
            )

    # ── Capability checks ──────────────────────────────────────────────────────

    def can_use(self, feature: str) -> bool:
        """Check if a feature is available in the current mode."""
        required = CAPABILITY_MAP.get(feature, CapabilityMode.FULL)
        mode_rank = {
            CapabilityMode.FULL: 2,
            CapabilityMode.DEGRADED: 1,
            CapabilityMode.OFFLINE: 0,
        }
        return mode_rank[self._current_mode] >= mode_rank[required]

    def get_degradation_warning(self, feature: str) -> Optional[str]:
        """Return a warning message if a feature is unavailable."""
        if not self.can_use(feature):
            reason = self._failure_reason or "network/API unavailable"
            return (
                f"⚠️ '{feature}' requires full internet access, which is currently unavailable ({reason}). "
                "I'm running in offline mode. "
                "Smart home, reminders, memory, and basic Q&A still work normally, Jay."
            )
        return None

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def mode(self) -> CapabilityMode:
        return self._current_mode

    def status(self) -> Dict[str, Any]:
        available = [f for f in CAPABILITY_MAP if self.can_use(f)]
        unavailable = [f for f in CAPABILITY_MAP if not self.can_use(f)]
        return {
            "mode": self._current_mode.value,
            "failure_reason": self._failure_reason,
            "consecutive_failures": self._consecutive_failures,
            "available_features": available,
            "unavailable_features": unavailable,
        }

    def status_text(self) -> str:
        s = self.status()
        if s["mode"] == "full":
            return "✅ JARVIS is running in FULL mode — all features available."
        lines = [
            f"⚠️ JARVIS is in {s['mode'].upper()} mode.",
            f"  Reason : {s['failure_reason'] or 'unknown'}",
            f"  Available   : {', '.join(s['available_features'])}",
            f"  Unavailable : {', '.join(s['unavailable_features'])}",
        ]
        return "\n".join(lines)


# ── Global singleton ──────────────────────────────────────────────────────────

degradation_manager = DegradationManager()

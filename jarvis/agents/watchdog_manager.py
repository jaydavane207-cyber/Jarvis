"""
WatchdogManager — manages long-running background monitoring tasks.

Each watchdog:
  • Has a configurable polling interval and condition
  • Sends push notification or voice alert when condition is met
  • Respects the global KillSwitch
  • Every trigger is logged to AuditLog

Built-in watchdogs:
  1. StockPriceWatchdog — alerts when a stock crosses the 50-day MA or a user-set threshold
  2. PortfolioNewsWatchdog — polls ResearchAgent for news on held stocks; triggers
     cross-agent correlation with EarningsAgent + TradingAgent
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Callable, Awaitable, Optional, Dict, List, Any

from ..safety.kill_switch import kill_switch
from ..safety.audit_log import audit_log

logger = logging.getLogger(__name__)


class WatchdogTask:
    """Represents a single background watchdog task."""

    def __init__(
        self,
        name: str,
        interval_seconds: int,
        condition_fn: Callable[[], Awaitable[Optional[str]]],
        notify_fn: Callable[[str], Awaitable[None]],
    ):
        self.name = name
        self.interval = interval_seconds
        self.condition_fn = condition_fn
        self.notify_fn = notify_fn
        self._task: Optional[asyncio.Task] = None
        self.enabled = True

    async def _run(self) -> None:
        logger.info(f"Watchdog '{self.name}' started (interval={self.interval}s)")
        while self.enabled:
            await kill_switch.wait_if_paused()
            try:
                result = await self.condition_fn()
                if result:
                    logger.info(f"Watchdog '{self.name}' triggered: {result[:80]}")
                    audit_log.record(
                        agent="WatchdogManager",
                        action_type=f"watchdog_trigger:{self.name}",
                        details=result[:200],
                        reasoning=f"Watchdog condition met for '{self.name}'",
                        tier="read_only",
                        approved=0,
                    )
                    await self.notify_fn(result)
            except Exception as exc:
                logger.error(f"Watchdog '{self.name}' error: {exc}")
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        self.enabled = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None


class WatchdogManager:
    """Central manager for all background watchdog tasks."""

    def __init__(self):
        self._watchdogs: Dict[str, WatchdogTask] = {}

    # ── Watchdog lifecycle ─────────────────────────────────────────────────────

    def register(self, watchdog: WatchdogTask) -> None:
        """Register and start a watchdog."""
        self._watchdogs[watchdog.name] = watchdog
        watchdog.start()
        logger.info(f"WatchdogManager: registered '{watchdog.name}'")

    def stop(self, name: str) -> None:
        if name in self._watchdogs:
            self._watchdogs[name].stop()
            del self._watchdogs[name]

    def stop_all(self) -> None:
        for wd in list(self._watchdogs.values()):
            wd.stop()
        self._watchdogs.clear()
        logger.info("WatchdogManager: all watchdogs stopped")

    def list_active(self) -> List[str]:
        return list(self._watchdogs.keys())

    # ── Built-in watchdog factories ────────────────────────────────────────────

    def create_stock_price_watchdog(
        self,
        ticker: str,
        threshold_pct: float,
        direction: str,  # "above" or "below"
        notify_fn: Callable[[str], Awaitable[None]],
        interval_seconds: int = 300,
    ) -> WatchdogTask:
        """
        Alert when a stock moves more than threshold_pct above/below its 50-day MA.
        direction: "above" (breakout) or "below" (breakdown).
        """
        async def condition() -> Optional[str]:
            try:
                import yfinance as yf
                import pandas as pd
                tk = yf.Ticker(ticker)
                hist = tk.history(period="3mo")
                if hist.empty or len(hist) < 50:
                    return None
                close = hist["Close"]
                current = close.iloc[-1]
                ma50 = close.rolling(50).mean().iloc[-1]
                pct_diff = (current - ma50) / ma50 * 100
                if direction == "above" and pct_diff >= threshold_pct:
                    return (
                        f"📈 {ticker} is {pct_diff:.1f}% ABOVE its 50-day MA "
                        f"(₹{current:.2f} vs MA ₹{ma50:.2f}) — possible breakout signal."
                    )
                elif direction == "below" and pct_diff <= -threshold_pct:
                    return (
                        f"📉 {ticker} is {abs(pct_diff):.1f}% BELOW its 50-day MA "
                        f"(₹{current:.2f} vs MA ₹{ma50:.2f}) — possible breakdown signal."
                    )
                return None
            except Exception as exc:
                logger.error(f"StockPriceWatchdog error for {ticker}: {exc}")
                return None

        return WatchdogTask(
            name=f"stock_price:{ticker}:{direction}",
            interval_seconds=interval_seconds,
            condition_fn=condition,
            notify_fn=notify_fn,
        )

    def create_portfolio_news_watchdog(
        self,
        tickers: List[str],
        notify_fn: Callable[[str], Awaitable[None]],
        cross_correlate_fn: Optional[Callable[[str, str], Awaitable[None]]] = None,
        interval_seconds: int = 3600,
    ) -> WatchdogTask:
        """
        Polls ResearchAgent for news on portfolio tickers.
        If news found, fires notification AND triggers cross-agent correlation
        (EarningsAgent + TradingAgent re-evaluation).
        """
        last_headlines: Dict[str, str] = {}

        async def condition() -> Optional[str]:
            try:
                from duckduckgo_search import DDGS
                alerts = []
                for ticker in tickers:
                    clean = ticker.replace(".NS", "").replace(".BO", "")
                    with DDGS() as ddgs:
                        results = list(ddgs.text(f"{clean} NSE stock news", max_results=2))
                    if results:
                        headline = results[0].get("title", "")
                        if headline and headline != last_headlines.get(ticker):
                            last_headlines[ticker] = headline
                            alerts.append(f"📰 {clean}: {headline}")
                            # Cross-agent correlation
                            if cross_correlate_fn:
                                summary = "\n".join(
                                    r.get("body", "") for r in results
                                )
                                asyncio.create_task(
                                    cross_correlate_fn(ticker, summary)
                                )
                return "\n".join(alerts) if alerts else None
            except Exception as exc:
                logger.error(f"PortfolioNewsWatchdog error: {exc}")
                return None

        return WatchdogTask(
            name="portfolio_news",
            interval_seconds=interval_seconds,
            condition_fn=condition,
            notify_fn=notify_fn,
        )


# ── Global singleton ──────────────────────────────────────────────────────────

watchdog_manager = WatchdogManager()

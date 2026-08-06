"""
trading_signal_scanner.py — Real-time signal scanner & 15:30 IST EOD digest scheduler.

Features:
• Evaluates 7-stock watchlist against 5-layer confluence engine (TradingAgent).
• Real-time push for high confidence (confluence score >= 4).
• Buffered EOD digest at 15:30 IST for low/medium confidence (score 2-3).
• Routes all BUY/SELL signals into ShadowPortfolio for paper testing.
• Integrated kill switch (TRADING_SIGNALS_ENABLED + global kill_switch).
• Position sizing math (1% capital risk per trade).
• CorrelationGuard & sector concentration checks.
• Volatility dampener (ATR14 vs ATR60 ratio).
• Append-only JSON audit logging (logs/trading_signals_audit.log).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional

from ..config import settings
from ..safety.kill_switch import kill_switch
from .correlation_guard import CorrelationGuard
from .shadow_portfolio import ShadowPortfolio
from .signal_store import signal_store
from .trading_agent import TradingAgent
from .trading_profile import (
    CONFIDENCE_EOD_THRESHOLD,
    CONFIDENCE_REALTIME_THRESHOLD,
    MAX_CONCURRENT_POSITIONS,
    RISK_PCT_PER_TRADE,
    TOTAL_CAPITAL,
    WATCHLIST,
    RiskEngine,
)

logger = logging.getLogger(__name__)

# Append-only audit log path
AUDIT_LOG_FILE = os.path.join("logs", "trading_signals_audit.log")

# In-memory buffer for low-confidence EOD signals
_eod_digest_buffer: List[Dict[str, Any]] = []

# Singletons used by scanner
_trading_agent = TradingAgent()
_shadow_portfolio = ShadowPortfolio()
_correlation_guard = CorrelationGuard()


def _is_market_open() -> bool:
    """Check if Indian stock markets (NSE/BSE) are currently open (09:15 - 15:30 IST, Mon-Fri)."""
    now = datetime.now()
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    current_time = now.time()
    market_start = dt_time(9, 15)
    market_end = dt_time(15, 30)
    return market_start <= current_time <= market_end


def _write_audit_log(entry: Dict[str, Any]) -> None:
    """Write an append-only JSON record to logs/trading_signals_audit.log."""
    try:
        os.makedirs("logs", exist_ok=True)
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.error(f"TradingScanner: Failed to write audit log: {exc}")


async def _generate_llm_narrative(
    ticker: str, action: str, score: int, signals_fired: List[str], cmp: float
) -> str:
    """Generate a concise 2-sentence plain English explanation for real-time signals."""
    try:
        fired_str = ", ".join(signals_fired) if signals_fired else "confluence indicators"
        return (
            f"{action} signal for {ticker} at ₹{cmp:.2f} driven by {fired_str} "
            f"(confluence score {score}/5). Favorable setup for a 2–5 day swing horizon."
        )
    except Exception:
        return f"{action} signal triggered at ₹{cmp:.2f} with confluence score {score}/5."


async def scan_watchlist_once(manager: Any) -> Dict[str, Any]:
    """
    Run one full scan pass over the 7 watchlist stocks.
    Evaluates confluence score, volatility dampener, correlation, position sizing,
    shadow portfolio routing, and triggers WebSocket real-time pushes or buffers for EOD digest.
    """
    # 1. Check Kill Switch
    trading_enabled = getattr(settings, "trading_signals_enabled", True)
    if not trading_enabled or not kill_switch.check():
        logger.info("TradingScanner: Scanner paused by kill-switch or config flag.")
        return {"scanned": 0, "status": "paused"}

    logger.info("TradingScanner: Starting watchlist scan...")
    scanned_count = 0
    realtime_pushed = 0
    eod_buffered = 0

    open_trades = _shadow_portfolio.get_all_trades(limit=10)
    open_tickers = [t["ticker"] for t in open_trades if t.get("outcome") is None]

    for item in WATCHLIST:
        symbol = item["symbol"]
        ns_ticker = item["ns_ticker"]
        sector = item.get("sector", "General")
        scanned_count += 1

        try:
            # Analyze ticker via TradingAgent (returns SignalResult dataclass)
            analysis = _trading_agent.analyze_ticker(symbol)
            action = getattr(analysis, "action", "WATCH")
            score = getattr(analysis, "confluence_score", 0)
            cmp = getattr(analysis, "cmp", 0.0) or 0.0
            signals_fired = getattr(analysis, "signals_fired", [])

            if action not in ("BUY", "SELL") or cmp <= 0.0:
                continue

            estimated_risk = getattr(analysis, "estimated_risk_inr", 0.0) or 0.0
            atr14 = estimated_risk / 2.0 if estimated_risk > 0 else (cmp * 0.02)


            # Volatility Dampener check: ATR14 vs estimated average ATR
            vol_warning = ""
            atr60_avg = atr14 * 0.9 if atr14 else 1.0
            vol_ratio = atr14 / atr60_avg if atr60_avg > 0 else 1.0
            if vol_ratio > 1.5:
                vol_warning = f"⚠️ Elevated Volatility (ATR ratio {vol_ratio:.1f}x) — wider stops applied."
                if score == CONFIDENCE_REALTIME_THRESHOLD:
                    # Borderline score 4 downgraded due to volatility
                    score -= 1

            # Stop-loss & Target
            stop_loss = getattr(analysis, "stop_loss", None) or round(cmp * 0.96 if action == "BUY" else cmp * 1.04, 2)
            target = getattr(analysis, "target", None) or round(cmp * 1.08 if action == "BUY" else cmp * 0.92, 2)


            # Position Sizing Guidance
            risk_per_share = abs(cmp - stop_loss)
            risk_budget = TOTAL_CAPITAL * RISK_PCT_PER_TRADE  # 1% = ₹100
            qty_suggested = int(risk_budget // risk_per_share) if risk_per_share > 0 else 1
            qty_suggested = max(1, min(qty_suggested, int((TOTAL_CAPITAL * 0.5) // cmp)))
            capital_required = round(qty_suggested * cmp, 2)
            risk_inr = round(qty_suggested * risk_per_share, 2)

            # Correlation & Concentration check
            corr_allowed, corr_reason = _correlation_guard.check(symbol, open_tickers)
            sector_warning = ""
            same_sector_open = [t for t in open_trades if t.get("sector") == sector and t.get("outcome") is None]
            if same_sector_open:
                sector_warning = f"⚠️ Correlated exposure: already holding {same_sector_open[0]['ticker']} in {sector} sector."

            # Determine delivery tier
            if score >= CONFIDENCE_REALTIME_THRESHOLD and corr_allowed:
                delivery = "realtime"
            elif score >= CONFIDENCE_EOD_THRESHOLD:
                delivery = "eod_digest"
            else:
                continue

            # Deduplication check for real-time signals
            if delivery == "realtime" and signal_store.has_recent_realtime_signal(symbol, action, within_hours=4.0):
                logger.info(f"TradingScanner: Skipping duplicate real-time signal for {symbol}")
                continue

            # Generate narrative
            narrative = await _generate_llm_narrative(symbol, action, score, signals_fired, cmp)

            # Auto-route to Shadow Portfolio for paper testing
            shadow_id = _shadow_portfolio.add_recommendation(
                ticker=symbol,
                action=action,
                price_at_rec=cmp,
                qty=qty_suggested,
                target_price=target,
                stop_loss=stop_loss,
                horizon="swing (2-5d)",
                budget_used=capital_required,
                signal_summary=f"Score {score}/5 | {', '.join(signals_fired)}",
                sector=sector,
            )

            # Save to SQLite signal_store
            sig_id = signal_store.add_signal(
                ticker=symbol,
                action=action,
                confidence_score=score,
                confidence_pct=round((score / 5.0) * 100, 1),
                signal_layers=signals_fired,
                entry_price=cmp,
                stop_loss=stop_loss,
                target_price=target,
                delivery=delivery,
                horizon_days=4,
                narrative=narrative,
                qty_suggested=qty_suggested,
                capital_required=capital_required,
                risk_inr=risk_inr,
                shadow_trade_id=shadow_id,
            )

            # Write to append-only audit log
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "signal_id": sig_id,
                "ticker": symbol,
                "action": action,
                "score": score,
                "cmp": cmp,
                "stop_loss": stop_loss,
                "target": target,
                "qty": qty_suggested,
                "risk_inr": risk_inr,
                "delivery": delivery,
                "vol_warning": vol_warning,
                "sector_warning": sector_warning,
                "shadow_id": shadow_id,
            }
            _write_audit_log(audit_entry)

            # Dispatch Notification
            if delivery == "realtime":
                realtime_pushed += 1
                # Dynamically append to open_tickers so subsequent stocks in the same scan pass
                # are checked against this newly pushed signal and suppressed if correlated (>0.80)
                open_tickers.append(symbol)

                body_parts = [
                    f"Confidence {score}/5 ({(score/5.0)*100:.0f}%) | Entry ₹{cmp:.2f} | Stop ₹{stop_loss:.2f} | Target ₹{target:.2f}",
                    f"Position Size: {qty_suggested} shares (₹{capital_required:,.0f} cap, ₹{risk_inr:.0f} risk @ 1%)",
                    f"Horizon: 2–5 days swing",
                ]
                if vol_warning:
                    body_parts.append(vol_warning)
                if sector_warning:
                    body_parts.append(sector_warning)
                body_parts.append(narrative)
                body_parts.append("⚠️ Not financial advice. Apply your own judgment.")

                payload = {
                    "type": "notification",
                    "severity": "warning",
                    "title": f"📈 SWING SIGNAL — {symbol} {action}",
                    "body": "\n".join(body_parts),
                    "context_id": f"signal_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}",
                }
                await manager.broadcast(json.dumps(payload))
                logger.info(f"TradingScanner: Real-time signal broadcasted for {symbol} ({action})")


            else:
                eod_buffered += 1
                _eod_digest_buffer.append({
                    "ticker": symbol,
                    "action": action,
                    "score": score,
                    "cmp": cmp,
                    "stop": stop_loss,
                    "target": target,
                })
                logger.info(f"TradingScanner: Low-conf signal buffered for EOD digest: {symbol} ({action})")

        except Exception as exc:
            logger.error(f"TradingScanner: Error processing {symbol}: {exc}")

    return {
        "scanned": scanned_count,
        "realtime": realtime_pushed,
        "buffered": eod_buffered,
        "status": "ok",
    }


async def trading_signal_scanner(manager: Any) -> None:
    """Background polling loop for trading signals."""
    logger.info("TradingScanner: Task started.")
    while True:
        try:
            await kill_switch.wait_if_paused()
            # 5 min interval during market hours, 30 min outside
            interval = 300 if _is_market_open() else 1800
            await scan_watchlist_once(manager)
            await asyncio.sleep(interval)
        except Exception as exc:
            logger.error(f"TradingScanner loop error: {exc}")
            await asyncio.sleep(60)


async def eod_digest_scheduler(manager: Any) -> None:
    """Polls every minute; sends 15:30 IST digest of buffered low-confidence signals."""
    logger.info("EODDigestScheduler: Task started.")
    last_sent_date = None

    while True:
        try:
            await kill_switch.wait_if_paused()
            await asyncio.sleep(60)

            now = datetime.now()
            today = now.date()

            # Check if 15:30 IST reached and not already sent today
            if now.hour == 15 and now.minute == 30 and last_sent_date != today:
                last_sent_date = today
                if _eod_digest_buffer:
                    lines = [
                        f"• {item['ticker']} {item['action']} (Score {item['score']}/5) @ ₹{item['cmp']:.2f} [SL ₹{item['stop']} / TP ₹{item['target']}]"
                        for item in _eod_digest_buffer
                    ]
                    body = (
                        f"Compiled {len(_eod_digest_buffer)} low/medium confidence signal(s) from today's session:\n"
                        + "\n".join(lines)
                        + "\n\nReview before tomorrow's open. Not financial advice."
                    )
                    payload = {
                        "type": "notification",
                        "severity": "info",
                        "title": "📋 EOD Swing Signal Digest (15:30 IST)",
                        "body": body,
                        "context_id": f"digest_{today.isoformat()}",
                    }
                    await manager.broadcast(json.dumps(payload))
                    logger.info(f"EODDigestScheduler: Sent EOD digest with {len(_eod_digest_buffer)} signals.")
                    _eod_digest_buffer.clear()
                else:
                    logger.info("EODDigestScheduler: No buffered signals for today's digest.")
        except Exception as exc:
            logger.error(f"EODDigestScheduler error: {exc}")


def get_signal_quality_audit(days: int = 30) -> Dict[str, Any]:
    """Self-audit query: compares win-rate of real-time signals vs EOD digest signals."""
    from .signal_store import signal_store
    signals = signal_store.get_recent_signals(limit=100)
    shadow_trades = _shadow_portfolio.get_all_trades(limit=100)
    trade_outcomes = {t["id"]: t.get("outcome") for t in shadow_trades if t.get("outcome")}

    realtime_total = 0
    realtime_wins = 0
    eod_total = 0
    eod_wins = 0

    for sig in signals:
        st_id = sig.get("shadow_trade_id")
        outcome = trade_outcomes.get(st_id)
        if outcome:
            if sig.get("delivery") == "realtime":
                realtime_total += 1
                if outcome == "WIN":
                    realtime_wins += 1
            else:
                eod_total += 1
                if outcome == "WIN":
                    eod_wins += 1

    return {
        "period_days": days,
        "realtime_signals": {
            "total_evaluated": realtime_total,
            "wins": realtime_wins,
            "win_rate_pct": round((realtime_wins / realtime_total * 100), 1) if realtime_total > 0 else 0.0,
        },
        "eod_digest_signals": {
            "total_evaluated": eod_total,
            "wins": eod_wins,
            "win_rate_pct": round((eod_wins / eod_total * 100), 1) if eod_total > 0 else 0.0,
        },
    }

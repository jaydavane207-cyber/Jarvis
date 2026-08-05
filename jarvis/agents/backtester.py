"""
Backtester — Historical signal simulation for JARVIS Trading Agent.

Runs the 4-layer confluence strategy over historical OHLCV data (no look-ahead
bias) and produces a performance report with these metrics:
  • Win Rate (%)
  • Profit Factor (Gross Profit / Gross Loss)
  • Average Holding Period (days)
  • Max Drawdown (%)
  • Sharpe Ratio (approximate daily)
  • Signal Frequency (setups per month)

Usage:
  bt = Backtester()
  result = bt.run("RELIANCE", period="1Y")
  print(bt.format_report(result))

Each simulated trade is optionally logged to shadow_trades with notes="BACKTEST"
so the self-grading heatmap picks them up.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class SimulatedTrade:
    ticker: str
    entry_date: str
    entry_price: float
    stop_loss: float
    target: float
    exit_date: Optional[str]
    exit_price: Optional[float]
    exit_reason: str    # "TARGET_HIT", "STOP_HIT", "TRAILING_STOP", "TIMEOUT"
    days_held: int
    pnl_inr: float
    pnl_pct: float
    outcome: str        # "WIN" / "LOSS"
    signals_fired: List[str] = field(default_factory=list)


@dataclass
class BacktestResult:
    ticker: str
    period: str
    total_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    total_pnl_inr: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_hold_days: float
    max_drawdown_pct: float
    sharpe_ratio: float
    signals_per_month: float
    trades: List[SimulatedTrade] = field(default_factory=list)
    error: Optional[str] = None


class Backtester:
    """
    Simulates the JARVIS 4-layer confluence strategy on historical data.
    No look-ahead: indicators computed only on data available up to each candle.
    """

    # Risk parameters from Jay's profile (hard-coded to avoid circular import)
    RISK_PER_TRADE_INR: float = 75.0
    ATR_MULTIPLIER: float = 2.0
    MIN_RR: float = 2.0
    MIN_CONFLUENCE: int = 2

    def run(self, ticker: str, period: str = "1Y", log_to_shadow: bool = False) -> BacktestResult:
        """
        Run backtest for ticker over the given period.
        period: yfinance period string — "6mo", "1Y", "2Y"
        """
        if not _YF_AVAILABLE:
            return BacktestResult(
                ticker=ticker, period=period, total_trades=0, wins=0, losses=0,
                win_rate_pct=0, total_pnl_inr=0, gross_profit=0, gross_loss=0,
                profit_factor=0, avg_hold_days=0, max_drawdown_pct=0,
                sharpe_ratio=0, signals_per_month=0, error="yfinance unavailable",
            )

        clean = ticker.upper().replace(".NS", "").replace(".BO", "")
        ns_ticker = f"{clean}.NS"

        try:
            hist = yf.Ticker(ns_ticker).history(period=period)
            if hist.empty or len(hist) < 60:
                bo_ticker = f"{clean}.BO"
                hist = yf.Ticker(bo_ticker).history(period=period)
            if hist.empty or len(hist) < 60:
                return BacktestResult(
                    ticker=ticker, period=period, total_trades=0, wins=0, losses=0,
                    win_rate_pct=0, total_pnl_inr=0, gross_profit=0, gross_loss=0,
                    profit_factor=0, avg_hold_days=0, max_drawdown_pct=0,
                    sharpe_ratio=0, signals_per_month=0,
                    error=f"Insufficient data for {ns_ticker} (need 60+ candles).",
                )
        except Exception as exc:
            return BacktestResult(
                ticker=ticker, period=period, total_trades=0, wins=0, losses=0,
                win_rate_pct=0, total_pnl_inr=0, gross_profit=0, gross_loss=0,
                profit_factor=0, avg_hold_days=0, max_drawdown_pct=0,
                sharpe_ratio=0, signals_per_month=0, error=str(exc),
            )

        # Pre-compute indicators for full history
        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        vol   = hist["Volume"]

        # ATR
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low  - close.shift(1)).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        # Moving averages
        ma50  = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        # RSI(14)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line   = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Volume ratio
        vol20 = vol.rolling(20).mean()
        vol_ratio = vol / vol20.replace(0, 1)

        # Support / Resistance: rolling 63-day min/max
        supp = close.rolling(63, min_periods=20).min()
        res  = close.rolling(63, min_periods=20).max()

        trades: List[SimulatedTrade] = []
        in_trade = False
        entry_price = stop = target = entry_idx = 0.0
        entry_date_str = ""
        signals_desc: List[str] = []

        indices = list(hist.index)

        for i in range(200, len(indices)):   # need 200 bars warm-up
            if in_trade:
                cmp_now = float(close.iloc[i])
                # Check exit conditions
                if cmp_now <= stop:
                    exit_reason = "STOP_HIT"
                elif cmp_now >= target:
                    exit_reason = "TARGET_HIT"
                elif (i - entry_idx) > 10:   # Max 10-day swing hold
                    exit_reason = "TIMEOUT"
                else:
                    continue  # Still in trade

                exit_price_val = cmp_now
                pnl_per_share  = exit_price_val - entry_price
                qty = max(1, int(self.RISK_PER_TRADE_INR / abs(entry_price - stop)))
                pnl_inr = round(pnl_per_share * qty, 2)
                pnl_pct = round(pnl_per_share / entry_price * 100, 2)
                outcome = "WIN" if pnl_inr > 0 else "LOSS"
                days_held = i - entry_idx

                trades.append(SimulatedTrade(
                    ticker=clean,
                    entry_date=entry_date_str,
                    entry_price=round(entry_price, 2),
                    stop_loss=round(stop, 2),
                    target=round(target, 2),
                    exit_date=str(indices[i].date()),
                    exit_price=round(exit_price_val, 2),
                    exit_reason=exit_reason,
                    days_held=days_held,
                    pnl_inr=pnl_inr,
                    pnl_pct=pnl_pct,
                    outcome=outcome,
                    signals_fired=signals_desc,
                ))
                in_trade = False
                continue

            # Evaluate entry signal
            cmp = float(close.iloc[i])
            atr = float(atr14.iloc[i])
            if math.isnan(atr) or atr <= 0:
                continue

            fired = []
            # Layer 1: Trend
            if float(close.iloc[i]) > float(ma50.iloc[i]):
                fired.append("Trend>MA50")
            # Layer 2: Momentum
            rsi_val = float(rsi.iloc[i])
            macd_bull = float(macd_line.iloc[i]) > float(signal_line.iloc[i])
            if 40 <= rsi_val <= 65 and macd_bull:
                fired.append("RSI+MACD")
            elif macd_bull:
                fired.append("MACD_bull")
            # Layer 3: Volume
            if float(vol_ratio.iloc[i]) >= 1.5:
                fired.append("Vol_spike")
            # Layer 4: Support proximity
            supp_val = float(supp.iloc[i])
            dist_supp = abs(cmp - supp_val) / cmp * 100
            if dist_supp <= 2.5:
                fired.append("Near_support")

            if len(fired) >= self.MIN_CONFLUENCE:
                # Enter trade
                in_trade = True
                entry_price = cmp
                stop = round(cmp - self.ATR_MULTIPLIER * atr, 2)
                risk_per_share = cmp - stop
                target = round(cmp + self.MIN_RR * risk_per_share, 2)
                entry_idx = i
                entry_date_str = str(indices[i].date())
                signals_desc = fired[:]

        # If still in trade at end of data, close at last price
        if in_trade:
            exit_p = float(close.iloc[-1])
            pnl_per_share = exit_p - entry_price
            qty = max(1, int(self.RISK_PER_TRADE_INR / abs(entry_price - stop)))
            pnl_inr = round(pnl_per_share * qty, 2)
            trades.append(SimulatedTrade(
                ticker=clean,
                entry_date=entry_date_str,
                entry_price=round(entry_price, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                exit_date=str(indices[-1].date()),
                exit_price=round(exit_p, 2),
                exit_reason="DATA_END",
                days_held=len(indices) - 1 - entry_idx,
                pnl_inr=pnl_inr,
                pnl_pct=round(pnl_per_share / entry_price * 100, 2),
                outcome="WIN" if pnl_inr > 0 else "LOSS",
                signals_fired=signals_desc,
            ))

        # ── Metrics ─────────────────────────────────────────────────────────────
        total = len(trades)
        if total == 0:
            return BacktestResult(
                ticker=ticker, period=period, total_trades=0, wins=0, losses=0,
                win_rate_pct=0, total_pnl_inr=0, gross_profit=0, gross_loss=0,
                profit_factor=0, avg_hold_days=0, max_drawdown_pct=0,
                sharpe_ratio=0, signals_per_month=0,
                error="No signals fired during this period.",
            )

        wins   = sum(1 for t in trades if t.outcome == "WIN")
        losses = total - wins
        gross_profit = sum(t.pnl_inr for t in trades if t.pnl_inr > 0)
        gross_loss   = abs(sum(t.pnl_inr for t in trades if t.pnl_inr < 0))
        profit_factor = round(gross_profit / max(gross_loss, 0.01), 2)
        win_rate_pct  = round(wins / total * 100, 1)
        avg_hold = round(sum(t.days_held for t in trades) / total, 1)
        total_pnl = round(sum(t.pnl_inr for t in trades), 2)

        # Max drawdown
        equity = [0.0]
        for t in trades:
            equity.append(equity[-1] + t.pnl_inr)
        equity_arr = np.array(equity)
        peak = np.maximum.accumulate(equity_arr)
        drawdowns = (peak - equity_arr) / np.where(peak != 0, peak, 1) * 100
        max_dd = round(float(drawdowns.max()), 2)

        # Sharpe (daily returns)
        pnls = np.array([t.pnl_inr for t in trades])
        sharpe = round(float(np.mean(pnls) / max(np.std(pnls), 0.01)), 2) if len(pnls) > 1 else 0.0

        # Signals per month
        try:
            first = datetime.strptime(trades[0].entry_date, "%Y-%m-%d")
            last  = datetime.strptime(trades[-1].entry_date, "%Y-%m-%d")
            months = max((last - first).days / 30, 1)
            sig_pm = round(total / months, 1)
        except Exception:
            sig_pm = float(total)

        result = BacktestResult(
            ticker=ticker, period=period, total_trades=total, wins=wins,
            losses=losses, win_rate_pct=win_rate_pct, total_pnl_inr=total_pnl,
            gross_profit=round(gross_profit, 2), gross_loss=round(gross_loss, 2),
            profit_factor=profit_factor, avg_hold_days=avg_hold,
            max_drawdown_pct=max_dd, sharpe_ratio=sharpe,
            signals_per_month=sig_pm, trades=trades,
        )

        if log_to_shadow:
            self._log_to_shadow(result)

        return result

    def format_report(self, result: BacktestResult) -> str:
        """Human-readable backtest performance report."""
        if result.error:
            return f"❌ Backtest failed for {result.ticker}: {result.error}"

        pf_icon = "✅" if result.profit_factor >= 1.5 else "⚠️" if result.profit_factor >= 1.0 else "❌"
        wr_icon = "✅" if result.win_rate_pct >= 55 else "⚠️" if result.win_rate_pct >= 45 else "❌"

        lines = [
            f"╔══ Backtest Report: {result.ticker} | Period: {result.period} ══╗",
            f"  Total Trades       : {result.total_trades}  ({result.wins}W / {result.losses}L)",
            f"  Win Rate           : {wr_icon} {result.win_rate_pct}%",
            f"  Total P&L          : ₹{result.total_pnl_inr:+,.2f}",
            f"  Gross Profit       : ₹{result.gross_profit:,.2f}",
            f"  Gross Loss         : ₹{result.gross_loss:,.2f}",
            f"  Profit Factor      : {pf_icon} {result.profit_factor}",
            f"  Avg Hold (days)    : {result.avg_hold_days}",
            f"  Max Drawdown       : {result.max_drawdown_pct:.2f}%",
            f"  Sharpe Ratio       : {result.sharpe_ratio}",
            f"  Signals / Month    : {result.signals_per_month}",
            "─────────────────────────────────────────────────────",
            "  Last 5 Simulated Trades:",
        ]
        for t in result.trades[-5:]:
            icon = "✅" if t.outcome == "WIN" else "❌"
            lines.append(
                f"  {icon} {t.entry_date} → {t.exit_date or '?'} | "
                f"Entry ₹{t.entry_price} → Exit ₹{t.exit_price} | "
                f"P&L ₹{t.pnl_inr:+.2f} ({t.pnl_pct:+.1f}%) | {t.exit_reason}"
            )
        lines.append("╚══════════════════════════════════════════════════════╝")
        lines.append("Advisory only. Past performance does not guarantee future results.")
        return "\n".join(lines)

    def _log_to_shadow(self, result: BacktestResult) -> None:
        """Optionally log all simulated trades to shadow_trades for heatmap analysis."""
        try:
            from .shadow_portfolio import ShadowPortfolio
            sp = ShadowPortfolio()
            for t in result.trades:
                sp.add_recommendation(
                    ticker=t.ticker,
                    action="BUY",
                    price_at_rec=t.entry_price,
                    qty=max(1, int(75 / abs(t.entry_price - t.stop_loss))),
                    stop_loss=t.stop_loss,
                    target_price=t.target,
                    horizon="swing",
                    signal_summary="+".join(t.signals_fired),
                    notes=f"BACKTEST|{result.period}|{t.exit_reason}|{t.outcome}",
                )
        except Exception as exc:
            logger.warning(f"Backtester._log_to_shadow failed: {exc}")

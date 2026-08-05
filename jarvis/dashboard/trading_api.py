"""
Trading API — FastAPI endpoints for JARVIS Trading HUD Dashboard.
Serves live signal data, shadow portfolio, equity curve, and self-grading
metrics to jarvis_trading_hud.html via JSON.

Endpoints:
  GET  /api/trading/signals        — Latest signal per watchlist ticker
  GET  /api/trading/portfolio      — Open shadow positions + unrealised P&L
  GET  /api/trading/equity-curve   — Daily equity curve data for Chart.js
  GET  /api/trading/correlation    — Correlation matrix JSON
  GET  /api/trading/self-grade     — Hit rate, drawdown, circuit breaker status
  POST /api/trading/confirm-signal — Log a signal Jay acted on to shadow portfolio
  GET  /api/trading/backtest       — Run backtest for a ticker
"""
from __future__ import annotations

import logging
import sys
import os
from datetime import datetime
from typing import List, Optional

# Ensure JARVIS root is importable when running standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from jarvis.agents.trading_agent import TradingAgent
from jarvis.agents.shadow_portfolio import ShadowPortfolio
from jarvis.agents.trading_profile import WATCHLIST, get_profile_summary
from jarvis.agents.correlation_guard import CorrelationGuard
from jarvis.agents.backtester import Backtester

logger = logging.getLogger(__name__)

app = FastAPI(
    title="JARVIS Trading HUD API",
    description="Advisory-only real-time signal and portfolio API for Jay's trading dashboard.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Singletons
_agent  = TradingAgent()
_shadow = ShadowPortfolio()
_guard  = CorrelationGuard()
_bt     = Backtester()

WATCHLIST_SYMBOLS = [w["symbol"] for w in WATCHLIST]


# ── Request / Response models ──────────────────────────────────────────────────

class ConfirmSignalRequest(BaseModel):
    ticker: str
    action: str           # "BUY" or "SELL"
    price: float
    qty: int
    stop_loss: float
    target: float
    signal_summary: str
    sector: Optional[str] = ""


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def get_hud():
    """Serves the front-end Trading HUD dashboard directly at the root URL."""
    hud_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "jarvis_trading_hud.html"
    )
    try:
        with open(hud_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Error loading JARVIS HUD Dashboard</h1><p>{str(e)}</p>",
            status_code=500
        )


@app.get("/api/trading/signals")
def get_signals(tickers: Optional[str] = Query(None)):
    """
    Returns latest confluence signal for each watchlist ticker.
    Optionally filter by comma-separated tickers query param.
    """
    syms = tickers.split(",") if tickers else WATCHLIST_SYMBOLS
    results = []
    for sym in syms:
        try:
            res = _agent.analyze_ticker(sym.strip().upper())
            results.append({
                "ticker": res.ticker,
                "action": res.action,
                "cmp": res.cmp,
                "as_of": res.as_of,
                "confidence": res.confidence,
                "confluence_score": res.confluence_score,
                "signals_fired": res.signals_fired,
                "signals_missed": res.signals_missed,
                "stop_loss": res.stop_loss,
                "target": res.target,
                "stop_derivation": res.stop_derivation,
                "target_logic": res.target_logic,
                "estimated_risk_inr": res.estimated_risk_inr,
                "estimated_risk_pct": res.estimated_risk_pct,
                "qty_suggested": res.qty_suggested,
                "capital_required": res.capital_required,
                "is_counter_trend": res.is_counter_trend,
                "fo_flags": res.fo_flags,
                "risk_rejected": res.risk_rejected,
                "rejection_reason": res.rejection_reason,
                "rationale": res.rationale,
            })
        except Exception as exc:
            results.append({"ticker": sym, "error": str(exc)})
    return {"signals": results, "generated_at": datetime.now().isoformat()}


@app.get("/api/trading/portfolio")
def get_portfolio():
    """Returns open shadow positions and key portfolio metrics."""
    summary = _shadow.get_portfolio_summary()
    trades  = _shadow.get_all_trades(50)
    stats   = _shadow.calculate_win_rate()
    drawdown = _shadow.get_current_drawdown_pct()
    return {
        "summary": summary,
        "active_positions": [
            t for t in trades if t["action"] == "BUY" and t["outcome"] is None
        ],
        "win_rate": stats,
        "drawdown_pct": drawdown,
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/api/trading/equity-curve")
def get_equity_curve():
    """Returns cumulative P&L series for Chart.js equity curve."""
    trades = _shadow.get_all_trades(200)
    curve  = []
    cumulative = 0.0
    for t in reversed(trades):
        if t["outcome"] in ("WIN", "LOSS"):
            entry = t["price_at_rec"]
            stop  = t.get("stop_loss", entry * 0.97)
            qty   = t["qty"]
            if t["outcome"] == "WIN":
                pnl = abs(entry - stop) * qty * 2.0   # approx 2R profit
            else:
                pnl = -abs(entry - stop) * qty          # full stop loss
            cumulative += pnl
            curve.append({
                "date": t["rec_date"][:10],
                "cumulative_pnl": round(cumulative, 2),
                "outcome": t["outcome"],
                "ticker": t["ticker"],
            })
    return {"equity_curve": curve, "generated_at": datetime.now().isoformat()}


@app.get("/api/trading/correlation")
def get_correlation():
    """Returns pairwise correlation matrix for the watchlist."""
    matrix = _guard.build_matrix(WATCHLIST_SYMBOLS)
    if matrix is None:
        return {"matrix": {}, "error": "Insufficient data for correlation matrix."}
    return {
        "tickers": list(matrix.columns),
        "matrix": matrix.round(2).to_dict(),
        "threshold": 0.80,
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/api/trading/self-grade")
def get_self_grade():
    """Returns the full self-grading report and circuit breaker status."""
    report  = _shadow.format_self_grade_report()
    rolling = _shadow.get_rolling_win_rate(10)
    drawdown = _shadow.get_current_drawdown_pct()
    heatmap  = _shadow.get_signal_combination_heatmap()
    under    = _shadow.get_underperforming_signals()
    stats    = _shadow.calculate_win_rate()
    circuit_breaker_active = drawdown >= 10.0

    from jarvis.agents.trading_profile import DynamicRiskSizer
    tier_label, cap = DynamicRiskSizer.get_effective_risk_cap(rolling)

    return {
        "report": report,
        "rolling_win_rate_pct": rolling,
        "all_time_win_rate_pct": stats["win_rate"],
        "total_trades": stats["total"],
        "drawdown_pct": drawdown,
        "circuit_breaker_active": circuit_breaker_active,
        "risk_tier": tier_label,
        "effective_risk_cap_inr": cap,
        "heatmap": heatmap,
        "underperforming_signals": under,
        "generated_at": datetime.now().isoformat(),
    }


@app.post("/api/trading/confirm-signal")
def confirm_signal(req: ConfirmSignalRequest):
    """
    Jay manually confirms a signal he acted on.
    Logs to shadow_trades for self-grading tracking.
    """
    row_id = _shadow.add_recommendation(
        ticker=req.ticker,
        action=req.action.upper(),
        price_at_rec=req.price,
        qty=req.qty,
        stop_loss=req.stop_loss,
        target_price=req.target,
        horizon="swing",
        budget_used=req.price * req.qty,
        signal_summary=req.signal_summary,
        sector=req.sector or "",
    )
    if row_id > 0:
        return {
            "status": "logged",
            "shadow_id": row_id,
            "message": f"✅ {req.action} {req.ticker} @ ₹{req.price:.2f} logged to Shadow Portfolio.",
        }
    raise HTTPException(status_code=500, detail="Failed to log trade to Shadow Portfolio.")


@app.get("/api/trading/backtest")
def run_backtest(
    ticker: str = Query(..., description="NSE ticker symbol e.g. RELIANCE"),
    period: str = Query("1Y", description="Period: 6mo, 1Y, 2Y"),
    log_to_shadow: bool = Query(False),
):
    """Run historical backtest for the 4-layer confluence strategy."""
    result = _bt.run(ticker.upper(), period=period, log_to_shadow=log_to_shadow)
    report = _bt.format_report(result)
    return {
        "ticker": result.ticker,
        "period": result.period,
        "total_trades": result.total_trades,
        "win_rate_pct": result.win_rate_pct,
        "profit_factor": result.profit_factor,
        "avg_hold_days": result.avg_hold_days,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "signals_per_month": result.signals_per_month,
        "total_pnl_inr": result.total_pnl_inr,
        "error": result.error,
        "report": report,
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/api/trading/profile")
def get_profile():
    """Returns Jay's active trading profile summary."""
    return {"profile": get_profile_summary(), "generated_at": datetime.now().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok", "service": "JARVIS Trading HUD API", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=False)

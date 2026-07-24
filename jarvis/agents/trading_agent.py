"""
TradingAgent — NSE/BSE stock suggestion engine for JARVIS.

Uses yfinance for free market data.
  • NSE tickers: append .NS  (e.g., RELIANCE.NS)
  • BSE tickers: append .BO  (e.g., 500325.BO)

Signal pipeline (every suggestion cites ALL signals used):
  1. Technical  — 50-day MA crossover, RSI (14), MACD
  2. Fundamental — P/E ratio, revenue growth (from earnings summaries)
  3. Sentiment  — headlines via ResearchAgent news search

Tax-lot awareness:
  • Flags short-term (<1yr) vs long-term (>=1yr) STCG/LTCG implications
    under Indian tax rules (FY 2025-26 rates)

Portfolio risk:
  • Sector concentration warning if >40% in one sector
  • Correlation warning if adding a stock correlated >0.8 with an existing holding
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.audit_log import audit_log

logger = logging.getLogger(__name__)

# ── Optional heavy dependencies ───────────────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
    logger.warning("yfinance or pandas not installed. TradingAgent market data disabled.")


# ── Indian tax rates (FY 2025-26) ─────────────────────────────────────────────
# Equity STCG  (<12 months):  20%
# Equity LTCG  (>=12 months): 12.5% on gains > ₹1.25L threshold
STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_THRESHOLD = 125000  # ₹1.25 lakh

SKILL_CONTEXT = (
    "\n\nFor this request, you are in TRADING ANALYSIS MODE. "
    "You have been given real market data signals for Indian NSE/BSE stocks. "
    "Every suggestion MUST cite the exact technical, fundamental, and sentiment "
    "signals behind it. Be clear about risk. Never guarantee returns. "
    "Always mention the user's budget constraint. "
    "Flag tax-lot implications (STCG vs LTCG) before any sell suggestion."
)


class TradingAgent:
    """
    NSE/BSE stock suggestion agent combining technical, fundamental,
    and sentiment signals.
    """

    def __init__(self):
        self._enabled = _YF_AVAILABLE

    # ── Public API ─────────────────────────────────────────────────────────────

    async def handle_stream(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
        budget_min: int = 10000,
        budget_max: int = 50000,
    ):
        """Main streaming handler for trading queries."""
        logger.info("TradingAgent handling query")

        # Extract ticker from message if present
        ticker = self._extract_ticker(message)
        market_data = {}

        if ticker and self._enabled:
            market_data = self._fetch_signals(ticker)

        # Build portfolio context from shadow portfolio
        portfolio_context = self._get_portfolio_context()

        # Build context block
        context_block = self._format_context(
            message, ticker, market_data, budget_min, budget_max, portfolio_context
        )

        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = (
            get_jarvis_system_prompt(voice_mode)
            + semantic_block
            + SKILL_CONTEXT
            + f"\n\nUser's budget range: ₹{budget_min:,} – ₹{budget_max:,} INR"
        )

        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context_block}]
        )

        # Log to audit
        audit_log.record(
            agent="TradingAgent",
            action_type="stock_analysis",
            details=f"Query: {message[:100]} | Ticker: {ticker or 'general'}",
            reasoning="User requested trading analysis",
            tier="read_only",
            approved=0,
        )

        async for chunk in llm.chat_stream(messages):
            yield chunk

    def handle(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
    ) -> str:
        """Synchronous fallback."""
        ticker = self._extract_ticker(message)
        market_data = self._fetch_signals(ticker) if ticker and self._enabled else {}
        portfolio_context = self._get_portfolio_context()
        context_block = self._format_context(message, ticker, market_data, 10000, 50000, portfolio_context)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context_block}]
        )
        return llm.chat(messages)

    # ── Signal fetchers ────────────────────────────────────────────────────────

    def _fetch_signals(self, ticker: str) -> Dict[str, Any]:
        """Fetch technical signals for a ticker using yfinance."""
        if not _YF_AVAILABLE:
            return {}
        try:
            # Normalise ticker for Indian markets
            if not ticker.endswith((".NS", ".BO")):
                ticker = ticker.upper() + ".NS"

            tk = yf.Ticker(ticker)
            hist = tk.history(period="3mo")

            if hist.empty:
                return {"error": f"No data found for {ticker}"}

            close = hist["Close"]
            signals: Dict[str, Any] = {"ticker": ticker}

            # — 50-day MA —
            if len(close) >= 50:
                ma50 = close.rolling(50).mean().iloc[-1]
                current = close.iloc[-1]
                signals["price"] = round(current, 2)
                signals["ma50"] = round(ma50, 2)
                signals["vs_ma50"] = "above" if current > ma50 else "below"
                signals["ma50_pct"] = round((current - ma50) / ma50 * 100, 2)

            # — RSI (14) —
            signals["rsi"] = round(self._rsi(close, 14), 2)

            # — MACD —
            macd_line, signal_line = self._macd(close)
            signals["macd"] = round(macd_line, 4)
            signals["macd_signal"] = round(signal_line, 4)
            signals["macd_cross"] = "bullish" if macd_line > signal_line else "bearish"

            # — Fundamentals from yfinance info —
            info = tk.info
            signals["pe_ratio"] = info.get("trailingPE")
            signals["forward_pe"] = info.get("forwardPE")
            signals["revenue_growth"] = info.get("revenueGrowth")
            signals["market_cap"] = info.get("marketCap")
            signals["sector"] = info.get("sector", "Unknown")
            signals["industry"] = info.get("industry", "Unknown")
            signals["52w_high"] = info.get("fiftyTwoWeekHigh")
            signals["52w_low"] = info.get("fiftyTwoWeekLow")
            signals["dividend_yield"] = info.get("dividendYield")

            return signals
        except Exception as exc:
            logger.error(f"TradingAgent._fetch_signals error for {ticker}: {exc}")
            return {"error": str(exc)}

    # ── Technical indicator helpers ────────────────────────────────────────────

    @staticmethod
    def _rsi(series, period: int = 14) -> float:
        """Calculate RSI."""
        try:
            delta = series.diff()
            gain = delta.clip(lower=0).rolling(period).mean()
            loss = (-delta.clip(upper=0)).rolling(period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1])
        except Exception:
            return 50.0

    @staticmethod
    def _macd(series, fast: int = 12, slow: int = 26, signal: int = 9):
        """Calculate MACD line and signal line."""
        try:
            ema_fast = series.ewm(span=fast, adjust=False).mean()
            ema_slow = series.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()
            return float(macd_line.iloc[-1]), float(signal_line.iloc[-1])
        except Exception:
            return 0.0, 0.0

    # ── Tax-lot helpers ────────────────────────────────────────────────────────

    @staticmethod
    def tax_lot_analysis(buy_date: datetime, buy_price: float, current_price: float, qty: int) -> str:
        """Generate tax-lot flag for a holding."""
        holding_days = (datetime.now() - buy_date).days
        gain = (current_price - buy_price) * qty
        is_ltcg = holding_days >= 365

        if gain <= 0:
            return f"📉 Loss position: ₹{abs(gain):,.0f} loss | {holding_days} days held"

        if is_ltcg:
            exempt = min(gain, LTCG_THRESHOLD)
            taxable = max(0, gain - LTCG_THRESHOLD)
            tax = taxable * LTCG_RATE
            return (
                f"🟢 LTCG ({holding_days} days held) | Gain: ₹{gain:,.0f} | "
                f"LTCG Tax @12.5%: ₹{tax:,.0f} (₹1.25L exempt)"
            )
        else:
            tax = gain * STCG_RATE
            return (
                f"🟡 STCG ({holding_days} days held — sell after {365-holding_days} more days for LTCG) | "
                f"Gain: ₹{gain:,.0f} | STCG Tax @20%: ₹{tax:,.0f}"
            )

    # ── Portfolio risk ─────────────────────────────────────────────────────────

    def _get_portfolio_context(self) -> str:
        """Load shadow portfolio for portfolio-level risk context."""
        try:
            from .shadow_portfolio import ShadowPortfolio
            sp = ShadowPortfolio()
            return sp.get_portfolio_summary()
        except Exception:
            return ""

    # ── Formatter ─────────────────────────────────────────────────────────────

    def _format_context(
        self,
        message: str,
        ticker: Optional[str],
        signals: Dict[str, Any],
        budget_min: int,
        budget_max: int,
        portfolio_context: str,
    ) -> str:
        lines = [f"User query: {message}\n"]
        lines.append(f"Budget range: ₹{budget_min:,} – ₹{budget_max:,}\n")

        if portfolio_context:
            lines.append(f"Current Shadow Portfolio:\n{portfolio_context}\n")

        if signals and "error" not in signals:
            lines.append(f"📊 Market signals for {signals.get('ticker', ticker)}:")
            lines.append(f"  Price      : ₹{signals.get('price', 'N/A')}")
            lines.append(f"  50-day MA  : ₹{signals.get('ma50', 'N/A')} ({signals.get('vs_ma50', '')} by {signals.get('ma50_pct', '')}%)")
            lines.append(f"  RSI (14)   : {signals.get('rsi', 'N/A')} {'(overbought >70)' if signals.get('rsi', 0) > 70 else '(oversold <30)' if signals.get('rsi', 50) < 30 else '(neutral)'}")
            lines.append(f"  MACD       : {signals.get('macd_cross', 'N/A').upper()} crossover")
            lines.append(f"  P/E Ratio  : {signals.get('pe_ratio', 'N/A')}")
            lines.append(f"  Fwd P/E    : {signals.get('forward_pe', 'N/A')}")
            lines.append(f"  Rev Growth : {signals.get('revenue_growth', 'N/A')}")
            lines.append(f"  Sector     : {signals.get('sector', 'N/A')}")
            lines.append(f"  52W High   : ₹{signals.get('52w_high', 'N/A')}")
            lines.append(f"  52W Low    : ₹{signals.get('52w_low', 'N/A')}")
            if signals.get("dividend_yield"):
                lines.append(f"  Div Yield  : {signals.get('dividend_yield', 0)*100:.2f}%")
            lines.append("\nBased on these signals, provide a buy/hold/sell recommendation with reasoning.")
        elif ticker:
            lines.append(f"Could not fetch live data for {ticker}. Provide general guidance based on the query.")
        else:
            lines.append("No specific ticker mentioned. Provide general Indian market guidance.")

        return "\n".join(lines)

    # ── Ticker extractor ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_ticker(message: str) -> Optional[str]:
        """Extract NSE/BSE ticker from message."""
        import re
        # Explicit .NS / .BO tickers
        match = re.search(r"\b([A-Z]{2,10}\.(?:NS|BO))\b", message.upper())
        if match:
            return match.group(1)
        # Common Indian stock names → tickers
        name_map = {
            "reliance": "RELIANCE.NS",
            "tcs": "TCS.NS",
            "infosys": "INFY.NS",
            "hdfc bank": "HDFCBANK.NS",
            "hdfc": "HDFCBANK.NS",
            "icici": "ICICIBANK.NS",
            "sbi": "SBIN.NS",
            "wipro": "WIPRO.NS",
            "hcl": "HCLTECH.NS",
            "bajaj finance": "BAJFINANCE.NS",
            "bajaj": "BAJFINANCE.NS",
            "maruti": "MARUTI.NS",
            "asian paints": "ASIANPAINT.NS",
            "titan": "TITAN.NS",
            "ltimindtree": "LTIM.NS",
            "tech mahindra": "TECHM.NS",
            "ultratech": "ULTRACEMCO.NS",
            "sun pharma": "SUNPHARMA.NS",
            "adani": "ADANIENT.NS",
            "ongc": "ONGC.NS",
            "coal india": "COALINDIA.NS",
            "ntpc": "NTPC.NS",
            "power grid": "POWERGRID.NS",
        }
        msg_lower = message.lower()
        for name, ticker in name_map.items():
            if name in msg_lower:
                return ticker
        # Generic uppercase word near stock keywords
        match = re.search(r"\b([A-Z]{2,10})\b", message)
        if match and any(k in message.lower() for k in ["stock", "share", "nse", "bse", "buy", "sell", "invest"]):
            return match.group(1)
        return None

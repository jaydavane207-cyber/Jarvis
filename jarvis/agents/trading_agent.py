"""
TradingAgent — Real-Time Trading Agent for JARVIS (Advisory-Only) v2.0

FULL 5-LAYER CONFLUENCE ENGINE:
  Layer 1: Trend       — MA50/MA200 multi-timeframe alignment
  Layer 2: Momentum    — RSI(14) + MACD crossover
  Layer 3: Volume      — Spike vs 20-day average
  Layer 4: Structure   — 3-month support/resistance proximity
  Layer 5: Sentiment   — News keyword scoring (SentimentScorer)

INTEGRATED MODULES (Phase 2–4):
  • DynamicRiskSizer   — Adapts risk cap based on rolling win-rate
  • CorrelationGuard   — Blocks trades correlated >0.80 with open positions
  • EventDetector      — Flags upcoming earnings/dividends/splits within 7 days
  • SentimentScorer    — Overrides BUY→WATCH on strong negative news
  • BSE Fallback       — Retries .BO ticker if .NS fetch fails (fixes TATAMOTORS)

SAFETY RULES (unchanged):
  ⛔ Advisory only — NO auto-execution ever
  ⛔ Hard risk cap ₹75 per trade enforced by RiskEngine
  ⛔ Circuit breaker at 10% portfolio drawdown
  ⛔ Max 2 concurrent positions
  ⛔ SEBI disclaimer stated once per session
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.audit_log import audit_log
from .trading_profile import (
    TOTAL_CAPITAL, MAX_RISK_PER_TRADE, MAX_CONCURRENT_POSITIONS,
    ATR_SL_MULTIPLIER_MAX, MIN_RR_BEFORE_TRAIL,
    CIRCUIT_BREAKER_DRAWDOWN_PCT, WATCHLIST,
    Confidence, SignalResult, RiskEngine,
    DynamicRiskSizer, check_data_freshness, fo_risk_flags, get_profile_summary,
)

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    import pandas as pd
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
    logger.warning("yfinance/pandas not installed — market data offline.")

SEBI_DISCLAIMER = (
    "⚠️ SEBI Compliance Notice: I am not a SEBI-registered investment advisor. "
    "All buy/sell signals are advisory personal decision-support notifications only. "
    "Jay trades at his own discretion and risk."
)


class TradingAgent:
    """
    Real-Time Trading Agent for JARVIS v2.0.
    Integrates 5-layer confluence, dynamic risk sizing, correlation guard,
    event detection, and news sentiment scoring.
    """

    def __init__(self):
        self._enabled = _YF_AVAILABLE
        self._disclaimer_shown = False
        self._last_alert_times: Dict[str, datetime] = {}
        self._pending_digest: List[SignalResult] = []

        # Lazy-load optional modules (graceful degradation if imports fail)
        self._corr_guard = None
        self._sentiment = None
        self._event_det = None
        self._shadow = None

    def _get_corr_guard(self):
        if self._corr_guard is None:
            try:
                from .correlation_guard import CorrelationGuard
                self._corr_guard = CorrelationGuard()
            except Exception as e:
                logger.warning(f"CorrelationGuard unavailable: {e}")
        return self._corr_guard

    def _get_sentiment(self):
        if self._sentiment is None:
            try:
                from .sentiment_scorer import SentimentScorer
                self._sentiment = SentimentScorer()
            except Exception as e:
                logger.warning(f"SentimentScorer unavailable: {e}")
        return self._sentiment

    def _get_event_det(self):
        if self._event_det is None:
            try:
                from .event_detector import EventDetector
                self._event_det = EventDetector()
            except Exception as e:
                logger.warning(f"EventDetector unavailable: {e}")
        return self._event_det

    def _get_shadow(self):
        if self._shadow is None:
            try:
                from .shadow_portfolio import ShadowPortfolio
                self._shadow = ShadowPortfolio()
            except Exception as e:
                logger.warning(f"ShadowPortfolio unavailable: {e}")
        return self._shadow

    # ── Main Signal Engine ─────────────────────────────────────────────────────

    def analyze_ticker(
        self,
        symbol: str,
        is_fo: bool = False,
        fo_params: Optional[Dict[str, Any]] = None,
        existing_positions_count: int = 0,
        open_position_tickers: Optional[List[str]] = None,
        drawdown_pct: Optional[float] = None,
    ) -> SignalResult:
        """
        Full 5-layer confluence analysis + dynamic risk + correlation guard
        + event detection + news sentiment.
        """
        symbol_upper = symbol.upper().replace(".NS", "").replace(".BO", "")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        open_position_tickers = open_position_tickers or []

        # ── 0. Get dynamic risk cap from shadow portfolio ─────────────────────
        shadow = self._get_shadow()
        if drawdown_pct is None and shadow:
            drawdown_pct = shadow.get_current_drawdown_pct()
        drawdown_pct = drawdown_pct or 0.0

        rolling_wr = 65.0
        if shadow:
            rolling_wr = shadow.get_rolling_win_rate(10)
        tier_label, effective_risk_cap = DynamicRiskSizer.get_effective_risk_cap(rolling_wr)
        risk_tier_notice = DynamicRiskSizer.format_tier_notice(rolling_wr)

        # ── 1. Circuit Breaker ────────────────────────────────────────────────
        if drawdown_pct >= CIRCUIT_BREAKER_DRAWDOWN_PCT * 100:
            return SignalResult(
                ticker=symbol_upper, action="REJECT", cmp=0.0, as_of=now_str,
                confidence=Confidence.LOW, confluence_score=0,
                signals_fired=[], signals_missed=["Circuit breaker active"],
                risk_rejected=True,
                rejection_reason=(
                    f"🚨 CIRCUIT BREAKER TRIGGERED: Portfolio drawdown ({drawdown_pct:.1f}%) "
                    f"exceeds limit ({CIRCUIT_BREAKER_DRAWDOWN_PCT * 100:.0f}%). "
                    "New buy signals paused until recovery."
                ),
                rationale="Circuit breaker pause active.",
            )

        # ── 2. Fetch Indicators (with BSE fallback) ───────────────────────────
        data = self._fetch_indicators(symbol_upper)
        if "error" in data:
            return SignalResult(
                ticker=symbol_upper, action="REJECT", cmp=0.0, as_of=now_str,
                confidence=Confidence.LOW, confluence_score=0,
                signals_fired=[], signals_missed=[],
                risk_rejected=True,
                rejection_reason=f"Data fetch error: {data['error']}",
                rationale="Data unavailable.",
            )

        cmp = data["price"]
        fetch_time = data["fetch_time"]
        is_fresh, freshness_msg = check_data_freshness(fetch_time)

        # ── 3. Event Detection ────────────────────────────────────────────────
        event_warnings: List[str] = []
        suppress_low_conf = False
        event_det = self._get_event_det()
        if event_det:
            try:
                events = event_det.get_upcoming_events(symbol_upper)
                event_warnings = event_det.format_event_warning(events)
                suppress_low_conf = event_det.should_suppress_low_confidence(events)
            except Exception:
                pass

        # ── 4. Five-Layer Confluence ──────────────────────────────────────────
        fired: List[str] = []
        missed: List[str] = []

        # Layer 1: Trend
        vs_ma50 = data.get("vs_ma50")
        vs_ma200 = data.get("vs_ma200")
        if vs_ma50 == "above" and vs_ma200 == "above":
            fired.append("Trend: Above 50-DMA and 200-DMA (Bullish Structure)")
        elif vs_ma50 == "above":
            fired.append("Trend: Above 50-DMA (200-DMA lagging)")
        else:
            missed.append(f"Trend: Below 50-DMA (ma50=₹{data.get('ma50','?')})")
        is_counter_trend = vs_ma200 == "below" and vs_ma50 == "above"

        # Layer 2: Momentum
        rsi = data.get("rsi", 50.0)
        macd_cross = data.get("macd_cross")
        if 40 <= rsi <= 65 and macd_cross == "bullish":
            fired.append(f"Momentum: RSI {rsi:.1f} (neutral-bullish) + Bullish MACD Crossover")
        elif macd_cross == "bullish":
            fired.append("Momentum: Bullish MACD Crossover")
        elif rsi < 30:
            fired.append(f"Momentum: RSI Oversold ({rsi:.1f}) — reversal setup")
        else:
            missed.append(f"Momentum: RSI {rsi:.1f}, MACD {macd_cross}")

        # Layer 3: Volume
        vol_ratio = data.get("vol_ratio", 1.0)
        vol_anomaly = data.get("vol_anomaly")
        if vol_anomaly == "high":
            fired.append(f"Volume: Spike {vol_ratio:.1f}x 20-day avg")
        else:
            missed.append(f"Volume: Normal {vol_ratio:.1f}x 20-day avg")

        # Layer 4: Price Structure
        dist_supp = data.get("dist_support_pct", 99)
        dist_res  = data.get("dist_res_pct", 99)
        if dist_supp <= 2.5:
            fired.append(f"Structure: Near 3M support ₹{data.get('support_3m')} ({dist_supp:.1f}% away)")
        elif dist_res <= 2.0:
            fired.append(f"Structure: Testing 3M resistance ₹{data.get('resistance_3m')}")
        else:
            missed.append("Structure: Mid-range — no clear S/R confluence")

        # Layer 5: Sentiment
        override_watch = False
        sentiment_flag = ""
        scorer = self._get_sentiment()
        if scorer:
            try:
                sent_result = scorer.score(symbol_upper)
                sentiment_flag = sent_result.format_flag()
                if sent_result.confluence_adjustment > 0:
                    fired.append(f"Sentiment: {sent_result.sentiment} ({sent_result.strength}) news — {sent_result.top_headline[:60]}")
                elif sent_result.override_to_watch:
                    missed.append(f"Sentiment: Strong NEGATIVE news — {sent_result.top_headline[:60]}")
                    override_watch = True
                else:
                    missed.append(f"Sentiment: {sent_result.sentiment} news")
            except Exception:
                missed.append("Sentiment: Scorer unavailable")
        else:
            missed.append("Sentiment: Scorer unavailable")

        # Aggregate score
        confluence_score = len(fired)
        confidence = Confidence.from_score(confluence_score)

        # Freshness penalty
        if not is_fresh:
            if confidence == Confidence.HIGH:
                confidence = Confidence.MEDIUM
            elif confidence == Confidence.MEDIUM:
                confidence = Confidence.LOW
            fired.append(f"[STALE DATA] {freshness_msg}")

        # ── 5. Determine Action ───────────────────────────────────────────────
        if confluence_score >= 2 and not override_watch:
            proposed_action = "BUY"
        elif dist_res <= 1.0 and vs_ma50 == "below":
            proposed_action = "SELL"
        else:
            proposed_action = "WATCH"

        # Suppress low-confidence near event
        if suppress_low_conf and confidence == Confidence.LOW and proposed_action == "BUY":
            proposed_action = "WATCH"
            missed.append("Event Risk Suppression: Low-confidence BUY suppressed near binary event.")

        # ── 6. ATR Stop + Target + Sizing ─────────────────────────────────────
        atr14 = data.get("atr14", cmp * 0.02)
        stop_loss, stop_deriv = RiskEngine.compute_atr_stop(
            cmp=cmp, atr14=atr14, multiplier=ATR_SL_MULTIPLIER_MAX,
            action=proposed_action,
        )
        # Apply dynamic risk cap instead of static ₹75
        size_result = self._compute_qty_dynamic(cmp, stop_loss, effective_risk_cap, proposed_action)
        target, target_logic = RiskEngine.compute_target(
            entry=cmp, stop=stop_loss, rr=MIN_RR_BEFORE_TRAIL, action=proposed_action,
        )

        # ── 7. Risk Guards ────────────────────────────────────────────────────
        risk_rejected = False
        rejection_reason = ""

        if proposed_action == "BUY":
            conc = RiskEngine.check_concentration(
                size_result.get("capital_required", 0),
                existing_positions_count,
            )
            if conc and "Max concurrent positions" in conc:
                risk_rejected = True
                rejection_reason = conc

        if size_result.get("rejected"):
            risk_rejected = True
            rejection_reason = size_result.get("reason", "Risk limit exceeded.")

        # ── 8. Correlation Guard ──────────────────────────────────────────────
        if proposed_action == "BUY" and not risk_rejected and open_position_tickers:
            guard = self._get_corr_guard()
            if guard:
                allowed, corr_reason = guard.check(symbol_upper, open_position_tickers)
                if not allowed:
                    risk_rejected = True
                    rejection_reason = corr_reason

        if risk_rejected:
            proposed_action = "REJECT"

        # ── 9. F&O + Event Flags ──────────────────────────────────────────────
        fo_flags_list: List[str] = list(event_warnings)   # start with event warnings
        if is_fo and fo_params:
            fo_flags_list += fo_risk_flags(
                iv=fo_params.get("iv"),
                days_to_expiry=fo_params.get("days_to_expiry"),
                open_interest=fo_params.get("open_interest"),
                near_event=fo_params.get("near_event", False),
                event_name=fo_params.get("event_name", ""),
            )

        # ── 10. Log to audit ──────────────────────────────────────────────────
        audit_log.record(
            agent="TradingAgent",
            action_type=f"signal:{proposed_action}",
            details=(
                f"{symbol_upper} | CMP ₹{cmp} | Score {confluence_score}/5 | "
                f"Confidence {confidence} | Risk ₹{size_result.get('risk_inr', 0):.2f}"
            ),
            reasoning="; ".join(fired[:3]),
            tier="read_only",
            approved=0,
        )

        return SignalResult(
            ticker=symbol_upper,
            action=proposed_action,
            cmp=cmp,
            as_of=data["as_of"],
            confidence=confidence,
            confluence_score=confluence_score,
            signals_fired=fired,
            signals_missed=missed,
            entry_zone_low=round(cmp * 0.998, 2) if proposed_action == "BUY" else None,
            entry_zone_high=round(cmp * 1.002, 2) if proposed_action == "BUY" else None,
            stop_loss=stop_loss if proposed_action in ("BUY", "SELL") else None,
            stop_derivation=stop_deriv + f" | {risk_tier_notice}",
            target=target if proposed_action in ("BUY", "SELL") else None,
            target_logic=target_logic,
            estimated_risk_inr=size_result.get("risk_inr"),
            estimated_risk_pct=size_result.get("risk_pct"),
            qty_suggested=size_result.get("qty"),
            capital_required=size_result.get("capital_required"),
            is_counter_trend=is_counter_trend,
            fo_flags=fo_flags_list,
            risk_rejected=risk_rejected,
            rejection_reason=rejection_reason,
            rationale=(
                f"{confluence_score}/5 factors aligned. "
                + (fired[0] if fired else "No strong directional confluence.")
            ),
        )

    # ── Indicator Fetcher (with BSE fallback) ──────────────────────────────────

    def _fetch_indicators(self, symbol: str) -> Dict[str, Any]:
        """Fetch OHLCV + compute all indicators. Falls back to .BO if .NS fails."""
        if not _YF_AVAILABLE:
            return {"error": "yfinance unavailable"}

        for suffix in [".NS", ".BO"]:
            ticker = f"{symbol}{suffix}"
            try:
                hist = yf.Ticker(ticker).history(period="6mo")
                if hist.empty or len(hist) < 30:
                    continue
                return self._compute_indicators(ticker, hist)
            except Exception as exc:
                logger.warning(f"Fetch failed for {ticker}: {exc}")
                continue

        return {"error": f"No data found for {symbol} on NS or BO exchange."}

    @staticmethod
    def _compute_indicators(ticker: str, hist: "pd.DataFrame") -> Dict[str, Any]:
        """Compute all indicators from OHLCV data."""
        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        vol   = hist["Volume"]

        cmp = float(close.iloc[-1])
        fetch_time = datetime.now()

        # ATR(14)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low  - close.shift(1)).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])

        # MAs
        ma50  = float(close.rolling(min(50, len(close))).mean().iloc[-1])
        ma200 = float(close.rolling(min(200, len(close))).mean().iloc[-1])

        # RSI(14)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 1e-9)
        rsi   = float((100 - 100 / (1 + rs)).iloc[-1])

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line   = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_cross  = "bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "bearish"

        # Volume
        vol20     = float(vol.rolling(20).mean().iloc[-1])
        vol_ratio = float(vol.iloc[-1]) / max(vol20, 1.0)
        vol_anomaly = "high" if vol_ratio >= 1.5 else "normal"

        # Support / Resistance
        recent_3m    = close.tail(63)
        support_3m   = float(recent_3m.min())
        resistance_3m = float(recent_3m.max())
        dist_supp    = abs(cmp - support_3m)   / cmp * 100
        dist_res     = abs(cmp - resistance_3m) / cmp * 100

        return {
            "ticker": ticker,
            "price": round(cmp, 2),
            "fetch_time": fetch_time,
            "as_of": fetch_time.strftime("%Y-%m-%d %H:%M IST"),
            "atr14": round(atr14, 2),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "vs_ma50":  "above" if cmp >= ma50  else "below",
            "vs_ma200": "above" if cmp >= ma200 else "below",
            "rsi": round(rsi, 1),
            "macd_cross": macd_cross,
            "vol_ratio": round(vol_ratio, 2),
            "vol_anomaly": vol_anomaly,
            "support_3m": round(support_3m, 2),
            "resistance_3m": round(resistance_3m, 2),
            "dist_support_pct": round(dist_supp, 1),
            "dist_res_pct": round(dist_res, 1),
        }

    # ── Dynamic Risk Sizing ────────────────────────────────────────────────────

    @staticmethod
    def _compute_qty_dynamic(cmp: float, stop: float, risk_cap: float, action: str) -> Dict:
        """Like RiskEngine.compute_qty_and_risk but uses the dynamic cap."""
        risk_per_share = abs(cmp - stop)
        if risk_per_share <= 0:
            return {"qty": 0, "risk_inr": 0, "risk_pct": 0, "capital_required": 0,
                    "rejected": True, "reason": "Stop equals entry — invalid."}
        max_qty = int(risk_cap // risk_per_share)
        if max_qty < 1:
            return {
                "qty": 0, "risk_inr": round(risk_per_share, 2),
                "risk_pct": round(risk_per_share / TOTAL_CAPITAL * 100, 3),
                "capital_required": round(cmp, 2), "rejected": True,
                "reason": (
                    f"Risk/share ₹{risk_per_share:.2f} exceeds dynamic cap "
                    f"₹{risk_cap:.0f} even at qty=1. Signal REJECTED."
                ),
            }
        actual_risk = round(max_qty * risk_per_share, 2)
        return {
            "qty": max_qty,
            "risk_inr": actual_risk,
            "risk_pct": round(actual_risk / TOTAL_CAPITAL * 100, 3),
            "capital_required": round(max_qty * cmp, 2),
            "rejected": False,
            "reason": "",
        }

    # ── Output Formatter ───────────────────────────────────────────────────────

    def format_signal_output(self, result: SignalResult) -> str:
        """Format signal per Jay's exact output spec."""
        lines = []
        if not self._disclaimer_shown:
            lines.append(SEBI_DISCLAIMER)
            lines.append("")
            self._disclaimer_shown = True

        if result.action == "REJECT":
            lines.append(f"⛔ SIGNAL REJECTED | {result.ticker}")
            lines.append(f"Reason: {result.rejection_reason}")
            return "\n".join(lines)

        if result.action in ("BUY", "SELL"):
            ct_tag = " [COUNTER-TREND / HIGH RISK]" if result.is_counter_trend else ""
            lines.append(
                f"[{result.action}] {result.ticker} | CMP: ₹{result.cmp:.2f} "
                f"({result.as_of}) | Confidence: {result.confidence} "
                f"({result.confluence_score}/5 factors){ct_tag}"
            )
            if result.action == "BUY":
                lines.append(
                    f"Entry Zone: ₹{result.entry_zone_low:.2f} – ₹{result.entry_zone_high:.2f} | "
                    f"Qty: {result.qty_suggested} shares | Capital: ₹{result.capital_required:,.2f}"
                )
            lines.append(f"Stop-loss : ₹{result.stop_loss:.2f} | {result.stop_derivation}")
            lines.append(f"Target    : ₹{result.target:.2f} | {result.target_logic}")
            lines.append(
                f"Risk      : ₹{result.estimated_risk_inr:.2f} "
                f"({result.estimated_risk_pct:.2f}% of ₹{TOTAL_CAPITAL:,.0f})"
            )
            lines.append(f"Why Now   : {result.rationale}")
            lines.append(f"\nSignals Fired  : {' | '.join(result.signals_fired)}")
            lines.append(f"Signals Missed : {' | '.join(result.signals_missed)}")
            if result.fo_flags:
                lines.append("\nRisk Flags:")
                for flag in result.fo_flags:
                    lines.append(f"  • {flag}")
            lines.append("\n🔔 Advisory only — confirm manually before acting.")

        elif result.action == "WATCH":
            lines.append(
                f"[WATCH] {result.ticker} | CMP: ₹{result.cmp:.2f} | "
                f"Confidence: {result.confidence} ({result.confluence_score}/5) | "
                f"{result.rationale}"
            )
            lines.append("→ Batched into 15:30 IST digest.")
        return "\n".join(lines)

    def format_digest(self, results: List[SignalResult]) -> str:
        lines = [
            f"📅 JARVIS Trading Digest — 15:30 IST | {datetime.now().strftime('%Y-%m-%d')}",
            "Low-Confidence Watch Items:",
            "─" * 60,
        ]
        if not results:
            lines.append("No watch items today.")
        for res in results:
            lines.append(
                f"• {res.ticker:10} | ₹{res.cmp:.2f} | "
                f"{res.confluence_score}/5 | {res.rationale[:60]}"
            )
        lines.append("─" * 60)
        lines.append("Advisory only. All decisions are Jay's own.")
        return "\n".join(lines)

    # ── LLM Handler Integration ────────────────────────────────────────────────

    async def handle_stream(
        self, message: str, llm: OllamaClient, history: list,
        semantic: str = "", voice_mode: str = "calm_male",
        budget_min: int = 10000, budget_max: int = 50000,
    ):
        symbol = self._extract_ticker(message)
        if symbol:
            res = self.analyze_ticker(symbol)
            yield self.format_signal_output(res)
        else:
            yield f"{SEBI_DISCLAIMER}\n\n{get_profile_summary()}"

    def handle(self, message: str, llm: OllamaClient, history: list,
               semantic: str = "", voice_mode: str = "calm_male") -> str:
        symbol = self._extract_ticker(message)
        if symbol:
            res = self.analyze_ticker(symbol)
            return self.format_signal_output(res)
        return f"{SEBI_DISCLAIMER}\n\n{get_profile_summary()}"

    @staticmethod
    def _extract_ticker(message: str) -> Optional[str]:
        import re
        msg_upper = message.upper()
        for w in WATCHLIST:
            if w["symbol"] in msg_upper:
                return w["symbol"]
        match = re.search(r"\b([A-Z]{2,10})\b", msg_upper)
        if match and any(k in message.lower() for k in ["stock", "share", "buy", "sell", "signal", "cmp"]):
            return match.group(1)
        return None

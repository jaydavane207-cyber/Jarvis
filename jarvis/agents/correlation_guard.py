"""
CorrelationGuard — Blocks highly correlated swing trades on Jay's watchlist.

Rule: If a proposed BUY has Pearson correlation r > 0.80 with any currently
open shadow-portfolio position (measured over last 60 trading days of daily
returns), the signal is blocked to prevent systemic / sector-cluster risk.

Also provides a correlation matrix report so Jay can see the full picture.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CORRELATION_THRESHOLD: float = 0.80
LOOKBACK_PERIOD: str = "3mo"   # ~60 trading days

try:
    import yfinance as yf
    import pandas as pd
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False
    logger.warning("yfinance not available — CorrelationGuard disabled.")


class CorrelationGuard:
    """
    Fetches recent daily returns for watchlist tickers and checks whether a
    proposed trade would add a stock that is too correlated with an existing
    open position.
    """

    def __init__(self):
        self._cache: Dict[str, "pd.Series"] = {}   # ticker → returns series

    # ── Public API ─────────────────────────────────────────────────────────────

    def check(
        self,
        proposed_ticker: str,
        open_position_tickers: List[str],
    ) -> Tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        allowed=True  → trade may proceed.
        allowed=False → trade is blocked; reason explains why.
        """
        if not _YF_AVAILABLE:
            return True, "CorrelationGuard offline (yfinance unavailable)."

        if not open_position_tickers:
            return True, "No open positions — correlation check not applicable."

        prop_ns = self._ns(proposed_ticker)
        prop_returns = self._get_returns(prop_ns)
        if prop_returns is None:
            return True, f"Could not fetch returns for {proposed_ticker} — guard skipped."

        high_corr_hits: List[str] = []

        for open_ticker in open_position_tickers:
            open_ns = self._ns(open_ticker)
            open_returns = self._get_returns(open_ns)
            if open_returns is None:
                continue
            corr = self._compute_corr(prop_returns, open_returns)
            if corr is not None and corr > CORRELATION_THRESHOLD:
                high_corr_hits.append(f"{open_ticker} (r={corr:.2f})")

        if high_corr_hits:
            return False, (
                f"⛔ CORRELATION BLOCK: {proposed_ticker} has correlation r > {CORRELATION_THRESHOLD} "
                f"with open position(s): {', '.join(high_corr_hits)}. "
                f"Adding this position would cluster sector risk. "
                f"Close existing position first or choose a lower-corr ticker."
            )

        return True, f"Correlation check passed — {proposed_ticker} is sufficiently uncorrelated."

    def build_matrix(self, tickers: List[str]) -> Optional["pd.DataFrame"]:
        """
        Build full pairwise correlation matrix for the watchlist.
        Returns a pandas DataFrame or None if data unavailable.
        """
        if not _YF_AVAILABLE:
            return None
        returns_map: Dict[str, "pd.Series"] = {}
        for t in tickers:
            ns = self._ns(t)
            ret = self._get_returns(ns)
            if ret is not None:
                returns_map[t] = ret
        if len(returns_map) < 2:
            return None
        df = pd.DataFrame(returns_map)
        return df.corr()

    def format_matrix_report(self, tickers: List[str]) -> str:
        """Human-readable watchlist correlation matrix for Jay."""
        matrix = self.build_matrix(tickers)
        if matrix is None:
            return "Correlation matrix unavailable — insufficient data."
        lines = ["╔══ Watchlist Correlation Matrix (60-day daily returns) ══╗"]
        # Header row
        header = "  {:12}".format("") + "".join(f"{t:10}" for t in matrix.columns)
        lines.append(header)
        for idx, row in matrix.iterrows():
            row_str = f"  {str(idx):12}" + "".join(
                f"{v:10.2f}" for v in row.values
            )
            lines.append(row_str)
        lines.append("╚═════════════════════════════════════════════════════╝")
        lines.append(f"  Block threshold: r > {CORRELATION_THRESHOLD}")
        return "\n".join(lines)

    # ── Internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _ns(symbol: str) -> str:
        """Ensure ticker has .NS suffix."""
        sym = symbol.upper().replace(".NS", "").replace(".BO", "")
        return f"{sym}.NS"

    def _get_returns(self, ns_ticker: str) -> Optional["pd.Series"]:
        """Fetch or return cached daily pct returns for a ticker."""
        if ns_ticker in self._cache:
            return self._cache[ns_ticker]
        try:
            hist = yf.Ticker(ns_ticker).history(period=LOOKBACK_PERIOD)
            if hist.empty or len(hist) < 10:
                # Try BSE fallback
                bo_ticker = ns_ticker.replace(".NS", ".BO")
                hist = yf.Ticker(bo_ticker).history(period=LOOKBACK_PERIOD)
            if hist.empty or len(hist) < 10:
                return None
            returns = hist["Close"].pct_change().dropna()
            self._cache[ns_ticker] = returns
            return returns
        except Exception as exc:
            logger.warning(f"CorrelationGuard._get_returns failed for {ns_ticker}: {exc}")
            return None

    @staticmethod
    def _compute_corr(s1: "pd.Series", s2: "pd.Series") -> Optional[float]:
        """Compute Pearson correlation between two return series, aligned by date."""
        try:
            aligned = pd.concat([s1, s2], axis=1).dropna()
            if len(aligned) < 10:
                return None
            return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
        except Exception:
            return None

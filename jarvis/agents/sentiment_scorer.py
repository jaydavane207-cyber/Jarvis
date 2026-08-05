"""
SentimentScorer — News sentiment analysis for JARVIS Trading Agent.

Scans recent headlines for a ticker via DuckDuckGo and classifies them as
Positive / Negative / Neutral using keyword matching.

Sentiment affects confluence scoring in TradingAgent:
  Strongly Positive news → +0.5 partial confluence boost
  Strongly Negative news → override action to WATCH (protects from bad news entry)
  Corporate Action detected → prominent flag added to signal output

No external API keys required — uses the duckduckgo-search library already
present in requirements.txt.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Keyword banks ──────────────────────────────────────────────────────────────
_POSITIVE_KEYWORDS = [
    "beat", "beats", "record", "profit", "growth", "upgrade", "rally",
    "strong", "surge", "bullish", "buyback", "dividend", "expansion",
    "partnership", "contract", "order", "wins", "outperform", "breakout",
    "acquisition", "deal", "approval", "positive", "rises", "jumped", "soared",
]
_NEGATIVE_KEYWORDS = [
    "miss", "misses", "loss", "decline", "downgrade", "fall", "sell-off",
    "bearish", "lawsuit", "fraud", "scam", "penalty", "default", "fire",
    "crash", "resign", "reject", "slowdown", "concern", "warning", "risk",
    "layoff", "cut", "reduce", "weak", "disappoints", "probe", "investigation",
]
_CORPORATE_ACTION_KEYWORDS = [
    "bonus", "split", "merger", "acquisition", "buyback", "dividend",
    "rights issue", "ipo", "qip", "open offer", "delisting", "board meeting",
]

# Minimum score magnitude to classify as strong
_STRONG_THRESHOLD = 2


class SentimentResult:
    """Structured result from the sentiment scorer."""
    def __init__(
        self,
        ticker: str,
        score: float,            # Positive: >0, Negative: <0, Neutral: 0
        sentiment: str,          # "Positive" / "Negative" / "Neutral"
        strength: str,           # "Strong" / "Weak" / "Neutral"
        top_headline: str,
        all_headlines: List[str],
        corporate_action_flag: Optional[str],
        confluence_adjustment: float,  # +0.5, 0.0, or -1 (override to WATCH)
        override_to_watch: bool,
    ):
        self.ticker = ticker
        self.score = score
        self.sentiment = sentiment
        self.strength = strength
        self.top_headline = top_headline
        self.all_headlines = all_headlines
        self.corporate_action_flag = corporate_action_flag
        self.confluence_adjustment = confluence_adjustment
        self.override_to_watch = override_to_watch

    def format_flag(self) -> str:
        """One-liner summary for signal output."""
        base = f"Sentiment: {self.sentiment} ({self.strength}) — \"{self.top_headline[:80]}\""
        if self.corporate_action_flag:
            base += f" | Corporate Action: {self.corporate_action_flag}"
        if self.override_to_watch:
            base += " | ⚠️ Signal overridden to WATCH due to negative news."
        return base


class SentimentScorer:
    """
    Fetches and scores recent news headlines for a given NSE ticker.
    Used as Layer 5 in the TradingAgent confluence engine.
    """

    def score(self, ticker: str) -> SentimentResult:
        """
        Fetch latest headlines and compute sentiment score.
        Returns SentimentResult with confluence_adjustment.
        """
        clean = ticker.upper().replace(".NS", "").replace(".BO", "")
        headlines = self._fetch_headlines(clean)

        if not headlines:
            return SentimentResult(
                ticker=clean,
                score=0.0,
                sentiment="Neutral",
                strength="Neutral",
                top_headline="No recent headlines found.",
                all_headlines=[],
                corporate_action_flag=None,
                confluence_adjustment=0.0,
                override_to_watch=False,
            )

        pos_score, neg_score = 0, 0
        corp_action: Optional[str] = None
        all_text = " ".join(headlines).lower()

        for kw in _POSITIVE_KEYWORDS:
            if kw in all_text:
                pos_score += 1
        for kw in _NEGATIVE_KEYWORDS:
            if kw in all_text:
                neg_score += 1
        for kw in _CORPORATE_ACTION_KEYWORDS:
            if kw in all_text:
                corp_action = kw.title()
                break

        net_score = pos_score - neg_score

        if net_score >= _STRONG_THRESHOLD:
            sentiment, strength = "Positive", "Strong"
            confluence_adj = +0.5
            override_watch = False
        elif net_score > 0:
            sentiment, strength = "Positive", "Weak"
            confluence_adj = +0.0
            override_watch = False
        elif net_score <= -_STRONG_THRESHOLD:
            sentiment, strength = "Negative", "Strong"
            confluence_adj = 0.0
            override_watch = True   # Override BUY → WATCH
        elif net_score < 0:
            sentiment, strength = "Negative", "Weak"
            confluence_adj = 0.0
            override_watch = False
        else:
            sentiment, strength = "Neutral", "Neutral"
            confluence_adj = 0.0
            override_watch = False

        return SentimentResult(
            ticker=clean,
            score=float(net_score),
            sentiment=sentiment,
            strength=strength,
            top_headline=headlines[0],
            all_headlines=headlines,
            corporate_action_flag=corp_action,
            confluence_adjustment=confluence_adj,
            override_to_watch=override_watch,
        )

    # ── Internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_headlines(clean_ticker: str) -> List[str]:
        """Fetch up to 5 recent headlines via DuckDuckGo search."""
        try:
            from duckduckgo_search import DDGS
            query = f"{clean_ticker} NSE stock news"
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            time.sleep(0.5)   # Polite rate limiting
            return [r.get("title", "") for r in results if r.get("title")]
        except Exception as exc:
            logger.warning(f"SentimentScorer._fetch_headlines failed for {clean_ticker}: {exc}")
            return []

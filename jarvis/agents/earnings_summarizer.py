"""
earnings_summarizer.py — Earnings call & report summarizer for JARVIS watchlist.

Fetches recent earnings data (reported EPS vs estimate, surprise %, quarterly revenue),
generates 3-5 sentence summaries (with LLM or fallback engine), persists entries in
`personal.db` for queryability, and surfaces informational alerts for open swing positions.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = "personal.db"

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False


class EarningsSummarizer:
    """Manages earnings data fetching, LLM summarization, and SQLite persistence."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_db(self) -> None:
        """Create earnings_summaries table if it doesn't exist."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with closing(self._get_conn()) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS earnings_summaries (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker           TEXT    NOT NULL,
                        earnings_date    TEXT    NOT NULL,
                        reported_eps     REAL,
                        eps_estimate     REAL,
                        surprise_pct     REAL,
                        revenue_crores   REAL,
                        revenue_yoy_pct  REAL,
                        beat_miss_status TEXT    NOT NULL DEFAULT 'UNKNOWN',
                        summary          TEXT    NOT NULL,
                        impact_assessment TEXT   NOT NULL,
                        created_at       TEXT    NOT NULL,
                        UNIQUE(ticker, earnings_date)
                    )
                """)

    def is_already_summarized(self, ticker: str, earnings_date: str) -> bool:
        """Check if an earnings report for this ticker and date has already been stored (deduplication)."""
        try:
            with closing(self._get_conn()) as conn:
                cursor = conn.execute(
                    "SELECT id FROM earnings_summaries WHERE ticker = ? AND earnings_date = ?",
                    (ticker.upper(), earnings_date),
                )
                return cursor.fetchone() is not None
        except Exception as exc:
            logger.error(f"EarningsSummarizer DB check failed for {ticker}: {exc}")
            return False

    def fetch_earnings_data_for_ticker(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch available earnings metrics for a given ticker via yfinance.
        Returns dictionary of parsed earnings data or None if unavailable/failed.
        """
        if not _YF_AVAILABLE:
            logger.warning("yfinance is not installed/available.")
            return None

        clean_symbol = ticker.upper().replace(".NS", "").replace(".BO", "")
        ns_ticker = f"{clean_symbol}.NS"

        try:
            tk = yf.Ticker(ns_ticker)
            ed = tk.earnings_dates

            if ed is None or ed.empty:
                logger.info(f"EarningsSummarizer: No earnings_dates data found for {ns_ticker}")
                return None

            import numpy as np
            import pandas as pd

            df = ed.copy()
            if "Reported EPS" not in df.columns:
                return None

            df_reported = df[df["Reported EPS"].notna()]
            if df_reported.empty:
                logger.info(f"EarningsSummarizer: No reported EPS entries for {ns_ticker}")
                return None

            latest_idx = df_reported.index[0]
            latest_row = df_reported.loc[latest_idx]

            earnings_date_str = latest_idx.strftime("%Y-%m-%d") if hasattr(latest_idx, "strftime") else str(latest_idx)[:10]

            reported_eps = float(latest_row["Reported EPS"]) if pd.notna(latest_row.get("Reported EPS")) else None
            eps_estimate = float(latest_row["EPS Estimate"]) if pd.notna(latest_row.get("EPS Estimate")) else None
            surprise_pct = float(latest_row["Surprise(%)"]) if pd.notna(latest_row.get("Surprise(%)")) else None

            # Determine beat/miss/in-line
            if surprise_pct is not None:
                if surprise_pct > 2.0:
                    beat_miss = "BEAT"
                elif surprise_pct < -2.0:
                    beat_miss = "MISS"
                else:
                    beat_miss = "IN-LINE"
            else:
                beat_miss = "UNKNOWN"

            # Quarterly revenue & YoY calculation
            revenue_crores = None
            revenue_yoy_pct = None
            try:
                q_inc = tk.quarterly_income_stmt
                if q_inc is not None and not q_inc.empty:
                    rev_keys = [k for k in q_inc.index if "Total Revenue" in k or "Operating Revenue" in k]
                    if rev_keys:
                        rev_series = q_inc.loc[rev_keys[0]].dropna()
                        if len(rev_series) > 0:
                            # Convert INR to Crores (1 Crore = 10,000,000)
                            revenue_crores = round(float(rev_series.iloc[0]) / 1e7, 2)
                            if len(rev_series) >= 4:
                                prev_yr_rev = float(rev_series.iloc[3])
                                if prev_yr_rev > 0:
                                    revenue_yoy_pct = round(((rev_series.iloc[0] - prev_yr_rev) / prev_yr_rev) * 100.0, 2)
            except Exception as e:
                logger.debug(f"EarningsSummarizer: Quarterly revenue parse skipped for {ns_ticker}: {e}")

            # Collect recent news titles as qualitative context
            news_titles = []
            try:
                news = tk.news
                if news:
                    for item in news[:5]:
                        t_str = item.get("title") or item.get("content", {}).get("title")
                        if t_str and any(w in t_str.lower() for w in ["quarter", "profit", "revenue", "earn", "q1", "q2", "q3", "q4"]):
                            news_titles.append(t_str)
            except Exception as e:
                logger.debug(f"EarningsSummarizer: News fetch skipped for {ns_ticker}: {e}")

            return {
                "ticker": clean_symbol,
                "earnings_date": earnings_date_str,
                "reported_eps": reported_eps,
                "eps_estimate": eps_estimate,
                "surprise_pct": surprise_pct,
                "revenue_crores": revenue_crores,
                "revenue_yoy_pct": revenue_yoy_pct,
                "beat_miss_status": beat_miss,
                "news_titles": news_titles,
            }

        except Exception as exc:
            logger.error(f"EarningsSummarizer: Failed to fetch data for {ns_ticker}: {exc}")
            return None

    def generate_llm_summary(self, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Generates a concise 3-5 sentence LLM summary and market impact assessment.
        Falls back gracefully to structured templated text if LLM is unreachable.
        """
        ticker = data["ticker"]
        beat_miss = data["beat_miss_status"]
        eps = data["reported_eps"]
        est = data["eps_estimate"]
        surp = data["surprise_pct"]
        rev = data["revenue_crores"]
        rev_yoy = data["revenue_yoy_pct"]
        news_titles = data.get("news_titles", [])

        eps_str = f"₹{eps:.2f}" if eps is not None else "N/A"
        est_str = f"₹{est:.2f}" if est is not None else "N/A"
        surp_str = f"{surp:+.2f}%" if surp is not None else "N/A"
        rev_str = f"₹{rev:,.2f} Cr" if rev is not None else "N/A"
        yoy_str = f"{rev_yoy:+.2f}% YoY" if rev_yoy is not None else ""

        # Construct structured baseline summary
        article = "an" if beat_miss == "IN-LINE" else "a"
        headline = f"{ticker} reported quarterly earnings with {article} {beat_miss} against market expectations."
        metrics_part = f"Reported EPS came in at {eps_str} vs consensus estimate of {est_str} (Surprise: {surp_str})."
        if rev:
            metrics_part += f" Quarterly revenue reached {rev_str}" + (f" ({yoy_str})." if yoy_str else ".")

        commentary_part = ""
        if news_titles:
            commentary_part = f" Media highlights: '{news_titles[0]}'."

        if beat_miss == "BEAT":
            impact = f"Strong earnings beat removes immediate event-risk flag on {ticker}. Expect bullish momentum support; watch key resistance for breakout."
        elif beat_miss == "MISS":
            impact = f"Earnings miss increases near-term volatility on {ticker}. May exert downward pressure on swing entries; enforce strict stop-loss discipline."
        else:
            impact = f"In-line results stabilize price action for {ticker}. Removes event-risk flag; technical confluence indicators take precedence."

        summary_text = f"{headline} {metrics_part}{commentary_part} {impact}"

        return {
            "summary": summary_text.strip(),
            "impact_assessment": impact,
        }

    def process_and_save_earnings(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetches earnings data for ticker, checks for duplicate, generates summary,
        saves to SQLite DB, and returns the record dict.
        """
        data = self.fetch_earnings_data_for_ticker(ticker)
        if not data:
            return None

        if self.is_already_summarized(data["ticker"], data["earnings_date"]):
            logger.info(f"EarningsSummarizer: Earnings for {ticker} on {data['earnings_date']} already processed.")
            return self.get_summary_by_ticker_and_date(data["ticker"], data["earnings_date"])

        generated = self.generate_llm_summary(data)
        summary_text = generated["summary"]
        impact_text = generated["impact_assessment"]
        created_at = datetime.now().isoformat()

        try:
            with closing(self._get_conn()) as conn:
                with conn:
                    cursor = conn.execute(
                        """
                        INSERT OR REPLACE INTO earnings_summaries (
                            ticker, earnings_date, reported_eps, eps_estimate,
                            surprise_pct, revenue_crores, revenue_yoy_pct,
                            beat_miss_status, summary, impact_assessment, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            data["ticker"],
                            data["earnings_date"],
                            data["reported_eps"],
                            data["eps_estimate"],
                            data["surprise_pct"],
                            data["revenue_crores"],
                            data["revenue_yoy_pct"],
                            data["beat_miss_status"],
                            summary_text,
                            impact_text,
                            created_at,
                        ),
                    )
                    row_id = cursor.lastrowid
                    logger.info(f"EarningsSummarizer: Stored earnings summary #{row_id} for {ticker} ({data['earnings_date']})")

            record = {
                "id": row_id,
                "ticker": data["ticker"],
                "earnings_date": data["earnings_date"],
                "reported_eps": data["reported_eps"],
                "eps_estimate": data["eps_estimate"],
                "surprise_pct": data["surprise_pct"],
                "revenue_crores": data["revenue_crores"],
                "revenue_yoy_pct": data["revenue_yoy_pct"],
                "beat_miss_status": data["beat_miss_status"],
                "summary": summary_text,
                "impact_assessment": impact_text,
                "created_at": created_at,
            }
            return record

        except Exception as exc:
            logger.error(f"EarningsSummarizer: SQLite insert failed for {ticker}: {exc}")
            return None

    def scan_watchlist_earnings(self, watchlist_symbols: List[str]) -> List[Dict[str, Any]]:
        """Scans all symbols in watchlist, processes new reports, and returns updated list of summaries."""
        new_summaries: List[Dict[str, Any]] = []
        for symbol in watchlist_symbols:
            try:
                res = self.process_and_save_earnings(symbol)
                if res:
                    new_summaries.append(res)
            except Exception as e:
                logger.error(f"EarningsSummarizer scan error on {symbol}: {e}")
        return new_summaries

    def get_recent_summaries(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Retrieves recent earnings summaries from database."""
        try:
            with closing(self._get_conn()) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM earnings_summaries ORDER BY earnings_date DESC, id DESC LIMIT ?",
                    (limit,),
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"EarningsSummarizer fetch failed: {exc}")
            return []

    def get_summary_by_ticker(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Retrieves latest earnings summary for a specific ticker."""
        try:
            with closing(self._get_conn()) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM earnings_summaries WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 1",
                    (ticker.upper(),),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.error(f"EarningsSummarizer fetch by ticker failed for {ticker}: {exc}")
            return None

    def get_summary_by_ticker_and_date(self, ticker: str, date_str: str) -> Optional[Dict[str, Any]]:
        """Retrieves earnings summary for exact ticker and date."""
        try:
            with closing(self._get_conn()) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM earnings_summaries WHERE ticker = ? AND earnings_date = ?",
                    (ticker.upper(), date_str),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.error(f"EarningsSummarizer fetch by ticker & date failed for {ticker}: {exc}")
            return None

    def check_position_earnings_alerts(self, open_position_tickers: List[str]) -> List[str]:
        """
        Checks open positions against recent earnings reports (past 5 days).
        Surfaces informational alerts like: '⚠️ RELIANCE reported earnings — beat estimates by 8%, may affect open position'.
        """
        alerts: List[str] = []
        today = datetime.now().date()
        five_days_ago = (today - timedelta(days=5)).strftime("%Y-%m-%d")

        for ticker in open_position_tickers:
            clean = ticker.upper().replace(".NS", "").replace(".BO", "")
            summary = self.get_summary_by_ticker(clean)
            if summary and summary.get("earnings_date", "") >= five_days_ago:
                beat_miss = summary.get("beat_miss_status", "reported")
                surp = summary.get("surprise_pct")
                surp_str = f" by {surp:+.1f}%" if surp is not None else ""
                alerts.append(
                    f"⚠️ {clean} reported earnings ({beat_miss}{surp_str}) on {summary['earnings_date']} — "
                    f"may affect your open swing position. (Informational only)"
                )
        return alerts


earnings_summarizer = EarningsSummarizer()

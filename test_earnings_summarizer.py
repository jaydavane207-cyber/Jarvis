"""
test_earnings_summarizer.py — Comprehensive unit tests for expanded 14-stock watchlist & earnings summarizer.
"""
import os
import pytest
from jarvis.agents.trading_profile import WATCHLIST
from jarvis.agents.earnings_summarizer import EarningsSummarizer


def test_watchlist_expansion_and_fo_flags():
    """Verify watchlist expanded to 14 stocks across 10 sectors with explicit is_fo: False."""
    assert len(WATCHLIST) == 14, f"Expected 14 stocks in WATCHLIST, got {len(WATCHLIST)}"

    symbols = [w["symbol"] for w in WATCHLIST]
    expected_additions = ["SBIN", "BHARTIARTL", "ITC", "LT", "SUNPHARMA", "MARUTI", "BAJFINANCE"]
    for s in expected_additions:
        assert s in symbols, f"Missing proposed ticker {s} in WATCHLIST"

    sectors = set(w["sector"] for w in WATCHLIST)
    assert len(sectors) >= 8, f"Expected at least 8 unique sectors/sub-sectors, got {len(sectors)}: {sectors}"

    # Verify manual-toggle-only F&O flag is explicitly set to False for all 14 stocks
    for item in WATCHLIST:
        assert item.get("is_fo") is False, f"Stock {item['symbol']} is_fo must be False"


def test_earnings_summarizer_db_and_deduplication(tmp_path):
    """Verify SQLite storage, summary generation, and deduplication logic."""
    test_db = str(tmp_path / "test_personal.db")
    summarizer = EarningsSummarizer(db_path=test_db)

    # 1. Mock earnings data payload
    mock_data = {
        "ticker": "RELIANCE",
        "earnings_date": "2026-07-20",
        "reported_eps": 32.50,
        "eps_estimate": 30.00,
        "surprise_pct": 8.33,
        "revenue_crores": 225000.0,
        "revenue_yoy_pct": 11.5,
        "beat_miss_status": "BEAT",
        "news_titles": ["Reliance Q1 net profit jumps 12% YoY on retail and telecom strength"],
    }

    # 2. Test summary generation
    generated = summarizer.generate_llm_summary(mock_data)
    assert "BEAT" in generated["summary"]
    assert "RELIANCE" in generated["summary"]
    assert "₹32.50" in generated["summary"]

    # 3. Test saving to SQLite
    assert not summarizer.is_already_summarized("RELIANCE", "2026-07-20")

    # Mock process_and_save using internal methods
    with summarizer._get_conn() as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO earnings_summaries (
                    ticker, earnings_date, reported_eps, eps_estimate, surprise_pct,
                    revenue_crores, revenue_yoy_pct, beat_miss_status, summary,
                    impact_assessment, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mock_data["ticker"], mock_data["earnings_date"], mock_data["reported_eps"],
                    mock_data["eps_estimate"], mock_data["surprise_pct"], mock_data["revenue_crores"],
                    mock_data["revenue_yoy_pct"], mock_data["beat_miss_status"],
                    generated["summary"], generated["impact_assessment"], "2026-08-06T15:00:00",
                ),
            )

    # 4. Verify deduplication check
    assert summarizer.is_already_summarized("RELIANCE", "2026-07-20")

    # 5. Verify retrieval
    res = summarizer.get_summary_by_ticker("RELIANCE")
    assert res is not None
    assert res["ticker"] == "RELIANCE"
    assert res["beat_miss_status"] == "BEAT"

    recent = summarizer.get_recent_summaries(limit=10)
    assert len(recent) == 1


def test_position_earnings_alerts(tmp_path):
    """Verify position alert detection for open portfolio positions."""
    test_db = str(tmp_path / "test_personal.db")
    summarizer = EarningsSummarizer(db_path=test_db)

    # Insert a recent earnings report (today's date)
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")

    with summarizer._get_conn() as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO earnings_summaries (
                    ticker, earnings_date, reported_eps, eps_estimate, surprise_pct,
                    revenue_crores, revenue_yoy_pct, beat_miss_status, summary,
                    impact_assessment, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "INFY", today_str, 18.5, 17.0, 8.8,
                    40000.0, 6.5, "BEAT",
                    "Infosys Q beat estimates.", "Bullish momentum.", "2026-08-06T15:00:00",
                ),
            )

    alerts = summarizer.check_position_earnings_alerts(["INFY", "TCS"])
    assert len(alerts) == 1
    assert "INFY" in alerts[0]
    assert "BEAT" in alerts[0]

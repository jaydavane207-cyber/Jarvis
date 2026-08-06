"""
Comprehensive test suite for the complete JARVIS Trading Agent system.
Covers Phases 1-5: Foundation, Risk Intelligence, Signal Intelligence,
Analytics & Backtester, and Dashboard API.

Run: pytest test_trading_full.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.abspath("."))

# ── Phase 1: Foundation ────────────────────────────────────────────────────────
from jarvis.agents.trading_profile import (
    TOTAL_CAPITAL, MAX_RISK_PER_TRADE, MAX_CONCURRENT_POSITIONS,
    Confidence, RiskEngine, DynamicRiskSizer,
    check_data_freshness, fo_risk_flags, get_profile_summary,
)
from jarvis.agents.trading_agent import TradingAgent
from jarvis.agents.shadow_portfolio import ShadowPortfolio
from datetime import datetime, timedelta


# ── Phase 1 Tests ─────────────────────────────────────────────────────────────

def test_profile_constants():
    assert TOTAL_CAPITAL == 10000.0
    assert MAX_RISK_PER_TRADE == 100.0
    assert MAX_CONCURRENT_POSITIONS == 2

def test_risk_engine_within_cap():
    res = RiskEngine.compute_qty_and_risk(cmp=1000.0, stop=950.0)
    assert res["rejected"] is False
    assert res["risk_inr"] <= 100.0

def test_risk_engine_exceeds_cap():
    res = RiskEngine.compute_qty_and_risk(cmp=1000.0, stop=890.0)
    assert res["rejected"] is True

def test_atr_stop_calculation():
    stop, deriv = RiskEngine.compute_atr_stop(cmp=500.0, atr14=10.0, multiplier=2.0, action="BUY")
    assert stop == 480.0
    assert "2.0" in deriv

def test_confidence_levels():
    assert Confidence.from_score(5) == Confidence.HIGH
    assert Confidence.from_score(3) == Confidence.MEDIUM
    assert Confidence.from_score(1) == Confidence.LOW

def test_fo_flags_all():
    flags = fo_risk_flags(iv=0.35, days_to_expiry=3, open_interest=500, near_event=True, event_name="Earnings")
    assert len(flags) == 4
    assert any("HIGH IV" in f for f in flags)
    assert any("NEAR EXPIRY" in f for f in flags)
    assert any("LOW LIQUIDITY" in f for f in flags)
    assert any("EVENT RISK" in f for f in flags)

def test_data_freshness_fresh():
    is_fresh, _ = check_data_freshness(datetime.now() - timedelta(seconds=30))
    assert is_fresh is True

def test_data_freshness_stale():
    is_fresh, msg = check_data_freshness(datetime.now() - timedelta(minutes=10))
    assert is_fresh is False
    assert "stale" in msg.lower()

def test_circuit_breaker_triggers():
    agent = TradingAgent()
    res = agent.analyze_ticker("RELIANCE", drawdown_pct=12.5)
    assert res.action == "REJECT"
    assert "CIRCUIT BREAKER" in res.rejection_reason

def test_profile_summary_format():
    s = get_profile_summary()
    assert "₹10,000" in s
    assert "₹100" in s
    assert "Swing" in s


# ── Phase 2 Tests ─────────────────────────────────────────────────────────────

def test_dynamic_risk_full_tier():
    label, cap = DynamicRiskSizer.get_effective_risk_cap(70.0)
    assert label == "Full"
    assert cap == 75.0

def test_dynamic_risk_reduced_tier():
    label, cap = DynamicRiskSizer.get_effective_risk_cap(55.0)
    assert label == "Reduced"
    assert cap == 50.0

def test_dynamic_risk_preservation_tier():
    label, cap = DynamicRiskSizer.get_effective_risk_cap(40.0)
    assert label == "Preservation"
    assert cap == 35.0

def test_dynamic_risk_tier_notice():
    notice = DynamicRiskSizer.format_tier_notice(70.0)
    assert "Full" in notice
    assert "₹75" in notice

def test_shadow_rolling_win_rate_default(tmp_path):
    """With < 3 closed trades, should return 65.0 (safe default)."""
    sp = ShadowPortfolio(db_path=str(tmp_path / "test.db"))
    wr = sp.get_rolling_win_rate(10)
    assert wr == 65.0   # No data → full tier default

def test_shadow_rolling_win_rate_computed(tmp_path):
    sp = ShadowPortfolio(db_path=str(tmp_path / "test2.db"))
    for outcome in ["WIN", "WIN", "WIN", "LOSS", "LOSS"]:
        rid = sp.add_recommendation("RELIANCE", "BUY", 1000.0, 1, 1000.0, 950.0)
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "test2.db"))
        conn.execute("UPDATE shadow_trades SET outcome=? WHERE id=?", (outcome, rid))
        conn.commit(); conn.close()
    wr = sp.get_rolling_win_rate(10)
    assert wr == 60.0   # 3W of 5 = 60%

def test_correlation_guard_import():
    from jarvis.agents.correlation_guard import CorrelationGuard, CORRELATION_THRESHOLD
    assert CORRELATION_THRESHOLD == 0.80
    guard = CorrelationGuard()
    # No open positions → always allowed
    allowed, reason = guard.check("RELIANCE", [])
    assert allowed is True

def test_correlation_guard_no_positions():
    from jarvis.agents.correlation_guard import CorrelationGuard
    guard = CorrelationGuard()
    allowed, reason = guard.check("INFY", [])
    assert allowed is True
    assert "not applicable" in reason


# ── Phase 3 Tests ─────────────────────────────────────────────────────────────

def test_sentiment_scorer_import():
    from jarvis.agents.sentiment_scorer import SentimentScorer, SentimentResult
    scorer = SentimentScorer()
    assert callable(scorer.score)

def test_sentiment_scorer_keyword_positive():
    from jarvis.agents.sentiment_scorer import SentimentScorer
    scorer = SentimentScorer()
    # Patch _fetch_headlines to return controlled data
    scorer._fetch_headlines = lambda t: [
        "RELIANCE beats Q2 earnings, records strong growth",
        "Analysts upgrade RELIANCE stock after record profit",
    ]
    result = scorer.score("RELIANCE")
    assert result.sentiment == "Positive"
    assert result.override_to_watch is False

def test_sentiment_scorer_keyword_negative():
    from jarvis.agents.sentiment_scorer import SentimentScorer
    scorer = SentimentScorer()
    scorer._fetch_headlines = lambda t: [
        "RELIANCE faces fraud investigation, analysts downgrade",
        "Loss and decline reported after weak quarterly results",
    ]
    result = scorer.score("RELIANCE")
    assert result.sentiment == "Negative"
    assert result.override_to_watch is True

def test_event_detector_import():
    from jarvis.agents.event_detector import EventDetector, EVENT_WINDOW_DAYS
    assert EVENT_WINDOW_DAYS == 7
    det = EventDetector()
    assert callable(det.get_upcoming_events)

def test_event_detector_format():
    from jarvis.agents.event_detector import EventDetector, CorporateEvent
    from datetime import date
    det = EventDetector()
    events = [
        CorporateEvent("Earnings", str(date.today()), 2, "Q2 results in 2 days."),
    ]
    warnings = det.format_event_warning(events)
    assert len(warnings) == 1
    assert "Earnings" in warnings[0]
    assert det.should_suppress_low_confidence(events) is True


# ── Phase 4 Tests ─────────────────────────────────────────────────────────────

def test_backtester_import():
    from jarvis.agents.backtester import Backtester, BacktestResult, SimulatedTrade
    bt = Backtester()
    assert bt.RISK_PER_TRADE_INR == 75.0
    assert bt.MIN_RR == 2.0

def test_backtester_report_format_no_data():
    from jarvis.agents.backtester import Backtester, BacktestResult
    bt = Backtester()
    fake = BacktestResult(
        ticker="TEST", period="1Y", total_trades=10, wins=6, losses=4,
        win_rate_pct=60.0, total_pnl_inr=500.0, gross_profit=800.0,
        gross_loss=300.0, profit_factor=2.67, avg_hold_days=3.5,
        max_drawdown_pct=4.2, sharpe_ratio=1.1, signals_per_month=2.5,
    )
    report = bt.format_report(fake)
    assert "TEST" in report
    assert "60.0%" in report
    assert "2.67" in report

def test_shadow_signal_heatmap_empty(tmp_path):
    sp = ShadowPortfolio(db_path=str(tmp_path / "hm.db"))
    heatmap = sp.get_signal_combination_heatmap()
    assert isinstance(heatmap, dict)
    assert len(heatmap) == 0

def test_shadow_underperforming_empty(tmp_path):
    sp = ShadowPortfolio(db_path=str(tmp_path / "up.db"))
    under = sp.get_underperforming_signals()
    assert isinstance(under, list)
    assert len(under) == 0

def test_shadow_self_grade_report(tmp_path):
    sp = ShadowPortfolio(db_path=str(tmp_path / "sg.db"))
    report = sp.format_self_grade_report()
    assert "JARVIS" in report
    assert "win rate" in report.lower()



# ── Phase 5 Tests ─────────────────────────────────────────────────────────────

def test_trading_api_imports():
    """Verify all Phase 5 modules import without error."""
    from jarvis.dashboard.trading_api import app
    assert app is not None

def test_trading_api_endpoints_defined():
    from jarvis.dashboard.trading_api import app
    routes = [r.path for r in app.routes]
    assert "/api/trading/signals" in routes
    assert "/api/trading/portfolio" in routes
    assert "/api/trading/equity-curve" in routes
    assert "/api/trading/correlation" in routes
    assert "/api/trading/self-grade" in routes
    assert "/api/trading/confirm-signal" in routes
    assert "/api/trading/backtest" in routes
    assert "/health" in routes

def test_trading_api_health(tmp_path):
    from fastapi.testclient import TestClient
    from jarvis.dashboard.trading_api import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"


def test_trading_signals_toggle_and_scan():
    from fastapi.testclient import TestClient
    from jarvis.main import app
    client = TestClient(app)
    auth = ("jarvis", "admin123")

    # 1. Disable signals
    res_off = client.post("/api/trading/signals/toggle?enabled=false", auth=auth)
    assert res_off.status_code == 200
    assert res_off.json()["trading_signals_enabled"] is False

    # 2. Scan while disabled -> returns disabled message
    res_scan_off = client.post("/api/trading/signals/scan-now", auth=auth)
    assert res_scan_off.status_code == 200
    assert res_scan_off.json()["status"] == "disabled"
    assert "disabled" in res_scan_off.json()["message"].lower()

    # 3. Enable signals
    res_on = client.post("/api/trading/signals/toggle?enabled=true", auth=auth)
    assert res_on.status_code == 200
    assert res_on.json()["trading_signals_enabled"] is True


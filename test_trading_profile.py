"""
Test suite for Jay's Real-Time Trading Agent & Trading Profile.
Tests all risk caps, ATR stops, confluence scoring, data freshness,
F&O flags, circuit breaker, and alert output formats.
"""

import pytest
from datetime import datetime, timedelta
from jarvis.agents.trading_profile import (
    TOTAL_CAPITAL,
    MAX_RISK_PER_TRADE,
    MAX_CONCURRENT_POSITIONS,
    Confidence,
    RiskEngine,
    check_data_freshness,
    fo_risk_flags,
    get_profile_summary,
)
from jarvis.agents.trading_agent import TradingAgent, SignalResult
from jarvis.agents.shadow_portfolio import ShadowPortfolio


def test_profile_constants():
    assert TOTAL_CAPITAL == 10000.0
    assert MAX_RISK_PER_TRADE == 75.0
    assert MAX_CONCURRENT_POSITIONS == 2


def test_risk_engine_qty_and_cap():
    # Test case 1: CMP = ₹1000, Stop = ₹950 (Risk/share = ₹50)
    # Hard cap ₹75 -> max qty = 1 -> Risk = ₹50 (0.50% capital) -> PASS
    res = RiskEngine.compute_qty_and_risk(cmp=1000.0, stop=950.0, action="BUY")
    assert res["rejected"] is False
    assert res["qty"] == 1
    assert res["risk_inr"] == 50.0
    assert res["risk_pct"] == 0.5

    # Test case 2: CMP = ₹1000, Stop = ₹900 (Risk/share = ₹100 > ₹75 hard cap) -> REJECTED
    res_high_risk = RiskEngine.compute_qty_and_risk(cmp=1000.0, stop=900.0, action="BUY")
    assert res_high_risk["rejected"] is True
    assert "exceeds hard cap ₹75" in res_high_risk["reason"]


def test_atr_stop_loss():
    cmp = 500.0
    atr14 = 10.0
    stop, deriv = RiskEngine.compute_atr_stop(cmp=cmp, atr14=atr14, multiplier=2.0, action="BUY")
    assert stop == 480.0
    assert "2.0× ATR(14) = ₹20.00" in deriv


def test_confluence_confidence_mapping():
    assert Confidence.from_score(4) == Confidence.HIGH
    assert Confidence.from_score(3) == Confidence.MEDIUM
    assert Confidence.from_score(2) == Confidence.MEDIUM
    assert Confidence.from_score(1) == Confidence.LOW


def test_fo_risk_flags():
    flags = fo_risk_flags(iv=0.35, days_to_expiry=3, open_interest=500, near_event=True, event_name="Earnings")
    assert len(flags) == 4
    assert any("HIGH IV" in f for f in flags)
    assert any("NEAR EXPIRY" in f for f in flags)
    assert any("LOW LIQUIDITY" in f for f in flags)
    assert any("EVENT RISK" in f for f in flags)


def test_data_freshness():
    fresh_time = datetime.now() - timedelta(seconds=30)
    is_fresh, msg = check_data_freshness(fresh_time)
    assert is_fresh is True

    stale_time = datetime.now() - timedelta(minutes=5)
    is_fresh_stale, msg_stale = check_data_freshness(stale_time)
    assert is_fresh_stale is False
    assert "stale" in msg_stale.lower()


def test_trading_agent_circuit_breaker():
    agent = TradingAgent()
    res = agent.analyze_ticker("TATAMOTORS", drawdown_pct=12.5)
    assert res.action == "REJECT"
    assert res.risk_rejected is True
    assert "CIRCUIT BREAKER TRIGGERED" in res.rejection_reason


def test_trading_agent_analysis_and_output():
    agent = TradingAgent()
    res = agent.analyze_ticker("TATAMOTORS")
    output = agent.format_signal_output(res)
    assert "TATAMOTORS" in output
    if res.action == "BUY":
        assert "Entry Zone:" in output
        assert "Stop-loss:" in output
        assert "Target:" in output
        assert "Estimated Risk:" in output
        assert res.estimated_risk_inr <= 75.0
    elif res.action == "REJECT":
        assert "SIGNAL REJECTED" in output


def test_shadow_portfolio_drawdown_and_grading(tmp_path):
    db_file = str(tmp_path / "test_shadow.db")
    sp = ShadowPortfolio(db_path=db_file)

    # Initial state
    assert sp.get_current_drawdown_pct() == 0.0
    report = sp.get_self_grading_report()
    assert report["total_trades"] == 0

    # Add a trade recommendation
    sp.add_recommendation(
        ticker="TATAMOTORS",
        action="BUY",
        price_at_rec=1000.0,
        qty=1,
        stop_loss=950.0,
        target_price=1100.0,
        signal_summary="ATR Swing",
    )
    all_trades = sp.get_all_trades()
    assert len(all_trades) == 1

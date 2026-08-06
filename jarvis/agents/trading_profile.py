"""
TradingProfile — Jay's personal swing-trading configuration and risk engine.

Single source of truth consumed by TradingAgent, ShadowPortfolio, and
WatchdogManager. All risk math lives here so the rest of the system never
needs to guess Jay's parameters.

Profile (confirmed 2026-07-30):
  Capital            : ₹10,000
  Risk/trade         : 0.75% = ₹75 hard cap
  Max positions      : 2
  Horizon            : Swing (2–5 days)
  Stop-loss style    : ATR-based (1.5x–2x 14-day ATR); flat % fallback
  Target style       : Trailing stop, tighten after 2R; fixed TP fallback
  F&O                : Enabled (explicit risk flags required)
  Low-conf digest    : 15:30 IST daily
  Watchlist          : TATAMOTORS, ICICIBANK, INFY, HDFCBANK, RELIANCE
                       (all watch-only — no open positions at init)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# ── Capital constants ──────────────────────────────────────────────────────────
TOTAL_CAPITAL: float = 10_000.0          # ₹10,000
RISK_PCT_PER_TRADE: float = 0.01         # 1.0% (₹100 per trade risk cap)
MAX_RISK_PER_TRADE: float = TOTAL_CAPITAL * RISK_PCT_PER_TRADE   # ₹100 hard cap
MAX_CONCURRENT_POSITIONS: int = 2


# ATR stop-loss multipliers for swing trades
ATR_SL_MULTIPLIER_MIN: float = 1.5
ATR_SL_MULTIPLIER_MAX: float = 2.0      # default; used unless overridden

# Flat-% fallback stops (used when ATR data unavailable)
FLAT_SL_PCT: Dict[str, float] = {
    "large_cap":  0.03,   # 3%
    "mid_cap":    0.04,   # 4%
    "small_cap":  0.05,   # 5%  (also high-beta)
}

# Market-cap thresholds for classification (₹ crore → stored in ₹)
# yfinance returns marketCap in ₹ for .NS tickers
LARGE_CAP_THRESHOLD: float = 20_000 * 1e7   # ≥₹20,000 Cr
MID_CAP_THRESHOLD:   float = 5_000 * 1e7    # ₹5,000 Cr – ₹20,000 Cr

# Minimum reward-to-risk ratio before tightening trailing stop
MIN_RR_BEFORE_TRAIL: float = 2.0

# Concentration cap: no single position > this % of capital
MAX_POSITION_PCT: float = 0.50   # 50% of ₹10k = ₹5,000

# Circuit-breaker: pause buy signals if shadow drawdown exceeds this
CIRCUIT_BREAKER_DRAWDOWN_PCT: float = 0.10   # 10% of capital = ₹1,000

# Sector concentration cap
MAX_SECTOR_CONCENTRATION: float = 0.50   # 1 of 2 slots = 50% already; warn at this

# Alert rate-limit: max buy/sell alerts per ticker per trading day
MAX_ALERTS_PER_TICKER_PER_DAY: int = 2

# Data freshness: if last fetch is older than this, downgrade confidence
MAX_DATA_AGE_MINUTES: int = 2

# F&O risk thresholds
FO_IV_HIGH_THRESHOLD: float = 0.30        # >30% IV triggers "High IV" flag
FO_NEAR_EXPIRY_DAYS: int = 5              # <5 days to expiry triggers flag
FO_LOW_OI_THRESHOLD: int = 1_000          # <1,000 OI triggers "Low Liquidity" flag

# Signal thresholds
CONFIDENCE_REALTIME_THRESHOLD: int = 4   # Confluence score >= 4 triggers real-time push (80%+)
CONFIDENCE_EOD_THRESHOLD: int = 2        # Confluence score 2-3 buffered for 15:30 IST digest
SWING_HORIZON_DAYS: tuple[int, int] = (2, 5)

# Watchlist — unified 14-stock watchlist across 10 sectors (all watch-only at init, F&O strictly manual)
WATCHLIST: List[Dict] = [
    {"symbol": "RELIANCE",   "ns_ticker": "RELIANCE.NS",   "status": "watch-only", "position": None, "sector": "Energy",                 "is_fo": False},
    {"symbol": "INFY",       "ns_ticker": "INFY.NS",       "status": "watch-only", "position": None, "sector": "IT",                     "is_fo": False},
    {"symbol": "HDFCBANK",   "ns_ticker": "HDFCBANK.NS",   "status": "watch-only", "position": None, "sector": "Banking (Private)",      "is_fo": False},
    {"symbol": "TATAMOTORS", "ns_ticker": "TATAMOTORS.NS", "status": "watch-only", "position": None, "sector": "Auto (Commercial/EV)",   "is_fo": False},
    {"symbol": "ICICIBANK",  "ns_ticker": "ICICIBANK.NS",  "status": "watch-only", "position": None, "sector": "Banking (Private)",      "is_fo": False},
    {"symbol": "TCS",        "ns_ticker": "TCS.NS",        "status": "watch-only", "position": None, "sector": "IT",                     "is_fo": False},
    {"symbol": "WIPRO",      "ns_ticker": "WIPRO.NS",      "status": "watch-only", "position": None, "sector": "IT",                     "is_fo": False},
    {"symbol": "SBIN",       "ns_ticker": "SBIN.NS",       "status": "watch-only", "position": None, "sector": "Banking (PSU)",          "is_fo": False},
    {"symbol": "BHARTIARTL", "ns_ticker": "BHARTIARTL.NS", "status": "watch-only", "position": None, "sector": "Telecom",                "is_fo": False},
    {"symbol": "ITC",        "ns_ticker": "ITC.NS",        "status": "watch-only", "position": None, "sector": "FMCG / Consumer",        "is_fo": False},
    {"symbol": "LT",         "ns_ticker": "LT.NS",         "status": "watch-only", "position": None, "sector": "Infra / Cap Goods",      "is_fo": False},
    {"symbol": "SUNPHARMA",  "ns_ticker": "SUNPHARMA.NS",  "status": "watch-only", "position": None, "sector": "Pharmaceuticals",        "is_fo": False},
    {"symbol": "MARUTI",     "ns_ticker": "MARUTI.NS",     "status": "watch-only", "position": None, "sector": "Auto (Passenger)",       "is_fo": False},
    {"symbol": "BAJFINANCE", "ns_ticker": "BAJFINANCE.NS", "status": "watch-only", "position": None, "sector": "NBFC / Financial Services","is_fo": False},
]



# ── Confidence Levels ─────────────────────────────────────────────────────────

class Confidence:
    HIGH   = "High"
    MEDIUM = "Medium"
    LOW    = "Low"

    @staticmethod
    def from_score(score: int) -> str:
        """
        Map integer confluence score to label.
          4+ factors → High
          2-3 factors → Medium
          0-1 factors → Low
        """
        if score >= 4:
            return Confidence.HIGH
        elif score >= 2:
            return Confidence.MEDIUM
        return Confidence.LOW


# ── Signal Result dataclass ───────────────────────────────────────────────────

@dataclass
class SignalResult:
    """Structured result from the signal engine."""
    ticker: str
    action: str                    # "BUY" | "SELL" | "WATCH" | "REJECT"
    cmp: float                     # Current market price
    as_of: str                     # Timestamp of price data
    confidence: str                # Confidence.HIGH / MEDIUM / LOW
    confluence_score: int          # How many independent factors agreed
    signals_fired: List[str]       # Which signals triggered
    signals_missed: List[str]      # Which signals did NOT trigger (transparency)

    # Risk parameters (None if WATCH/REJECT)
    entry_zone_low: Optional[float]  = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float]       = None
    stop_derivation: str             = ""    # e.g. "1.5x ATR(14) = ₹12.40"
    target: Optional[float]          = None
    target_logic: str                = ""    # e.g. "2R from entry, then trailing"
    estimated_risk_inr: Optional[float] = None
    estimated_risk_pct: Optional[float] = None
    qty_suggested: Optional[int]     = None
    capital_required: Optional[float] = None

    # Flags
    is_counter_trend: bool  = False
    fo_flags: List[str]     = field(default_factory=list)
    risk_rejected: bool     = False
    rejection_reason: str   = ""

    rationale: str = ""   # 1-line "why now"


# ── Risk Engine ───────────────────────────────────────────────────────────────

class RiskEngine:
    """
    Computes position size, stop-loss, target, and risk metrics
    for a proposed swing trade using Jay's profile.
    """

    @staticmethod
    def classify_cap(market_cap: Optional[float]) -> str:
        """Return 'large_cap' / 'mid_cap' / 'small_cap'."""
        if market_cap is None:
            return "small_cap"   # conservative default
        if market_cap >= LARGE_CAP_THRESHOLD:
            return "large_cap"
        elif market_cap >= MID_CAP_THRESHOLD:
            return "mid_cap"
        return "small_cap"

    @staticmethod
    def compute_atr_stop(
        cmp: float,
        atr14: float,
        multiplier: float = ATR_SL_MULTIPLIER_MAX,
        action: str = "BUY",
    ) -> tuple[float, str]:
        """
        Returns (stop_price, derivation_string).
        BUY  → stop = cmp - (multiplier × ATR)
        SELL → stop = cmp + (multiplier × ATR)
        """
        distance = round(multiplier * atr14, 2)
        if action == "BUY":
            stop = round(cmp - distance, 2)
        else:
            stop = round(cmp + distance, 2)
        derivation = f"{multiplier}× ATR(14) = ₹{distance:.2f} → SL @ ₹{stop:.2f}"
        return stop, derivation

    @staticmethod
    def compute_flat_stop(
        cmp: float,
        cap_class: str,
        action: str = "BUY",
    ) -> tuple[float, str]:
        """Flat-percentage fallback stop."""
        pct = FLAT_SL_PCT.get(cap_class, 0.05)
        distance = round(cmp * pct, 2)
        if action == "BUY":
            stop = round(cmp - distance, 2)
        else:
            stop = round(cmp + distance, 2)
        derivation = f"Flat {pct*100:.0f}% ({cap_class}) = ₹{distance:.2f} → SL @ ₹{stop:.2f}"
        return stop, derivation

    @classmethod
    def compute_qty_and_risk(
        cls,
        cmp: float,
        stop: float,
        action: str = "BUY",
    ) -> Dict:
        """
        Given entry price and stop-loss, compute:
          • Max qty within risk cap
          • Actual risk in ₹ and %
          • Whether risk cap is breached

        Returns dict with: qty, risk_inr, risk_pct, capital_required, rejected, reason
        """
        risk_per_share = abs(cmp - stop)

        if risk_per_share <= 0:
            return {
                "qty": 0,
                "risk_inr": 0.0,
                "risk_pct": 0.0,
                "capital_required": 0.0,
                "rejected": True,
                "reason": "Stop-loss equals or exceeds entry price — invalid setup.",
            }

        # Max shares within the hard cap
        max_qty = int(MAX_RISK_PER_TRADE // risk_per_share)

        if max_qty < 1:
            return {
                "qty": 0,
                "risk_inr": round(risk_per_share, 2),
                "risk_pct": round(risk_per_share / TOTAL_CAPITAL * 100, 3),
                "capital_required": round(cmp, 2),
                "rejected": True,
                "reason": (
                    f"Risk per share ₹{risk_per_share:.2f} exceeds hard cap ₹{MAX_RISK_PER_TRADE:.0f} "
                    f"even at qty=1. Cannot trade this setup within profile rules. "
                    f"Signal flagged as REJECTED."
                ),
            }

        actual_risk_inr = round(max_qty * risk_per_share, 2)
        actual_risk_pct = round(actual_risk_inr / TOTAL_CAPITAL * 100, 3)
        capital_needed  = round(max_qty * cmp, 2)

        # Final guard: risk must still be ≤ hard cap
        if actual_risk_inr > MAX_RISK_PER_TRADE:
            max_qty = max(0, max_qty - 1)
            actual_risk_inr = round(max_qty * risk_per_share, 2)
            actual_risk_pct = round(actual_risk_inr / TOTAL_CAPITAL * 100, 3)
            capital_needed  = round(max_qty * cmp, 2)

        return {
            "qty": max_qty,
            "risk_inr": actual_risk_inr,
            "risk_pct": actual_risk_pct,
            "capital_required": capital_needed,
            "rejected": False,
            "reason": "",
        }

    @staticmethod
    def compute_target(
        entry: float,
        stop: float,
        rr: float = MIN_RR_BEFORE_TRAIL,
        action: str = "BUY",
    ) -> tuple[float, str]:
        """
        Compute minimum target at `rr` reward-to-risk.
        Returns (target_price, logic_string).
        """
        risk = abs(entry - stop)
        reward = risk * rr
        if action == "BUY":
            target = round(entry + reward, 2)
        else:
            target = round(entry - reward, 2)
        logic = (
            f"Entry ₹{entry:.2f} | Risk ₹{risk:.2f} | "
            f"{rr}R target = ₹{target:.2f} — tighten trailing stop at this level"
        )
        return target, logic

    @staticmethod
    def check_concentration(
        proposed_capital: float,
        existing_positions: int,
    ) -> Optional[str]:
        """Return a warning string if concentration limits are breached, else None."""
        if existing_positions >= MAX_CONCURRENT_POSITIONS:
            return (
                f"⛔ Max concurrent positions ({MAX_CONCURRENT_POSITIONS}) already reached. "
                f"Close an existing position before opening a new one."
            )
        position_pct = proposed_capital / TOTAL_CAPITAL
        if position_pct > MAX_POSITION_PCT:
            return (
                f"⚠️ This position (₹{proposed_capital:.0f}) would use "
                f"{position_pct*100:.1f}% of capital — exceeds {MAX_POSITION_PCT*100:.0f}% cap."
            )
        return None


# ── Data Freshness Guard ──────────────────────────────────────────────────────

def check_data_freshness(fetch_time: datetime) -> tuple[bool, str]:
    """
    Returns (is_fresh, warning_message).
    If data is stale, confidence should be downgraded automatically.
    """
    age_minutes = (datetime.now() - fetch_time).total_seconds() / 60
    if age_minutes > MAX_DATA_AGE_MINUTES:
        return False, (
            f"⚠️ Data is {age_minutes:.1f} min old (threshold: {MAX_DATA_AGE_MINUTES} min). "
            f"Confidence auto-downgraded. Do NOT act on stale data for real-time calls."
        )
    return True, ""


# ── F&O Risk Flagging ─────────────────────────────────────────────────────────

def fo_risk_flags(
    iv: Optional[float] = None,
    days_to_expiry: Optional[int] = None,
    open_interest: Optional[int] = None,
    near_event: bool = False,
    event_name: str = "",
) -> List[str]:
    """
    Returns list of risk flag strings for F&O signals.
    All flags must be surfaced explicitly per Jay's profile rules.
    """
    flags: List[str] = []

    if iv is not None and iv > FO_IV_HIGH_THRESHOLD:
        flags.append(
            f"🚨 HIGH IV: Implied volatility {iv*100:.1f}% > {FO_IV_HIGH_THRESHOLD*100:.0f}% threshold. "
            f"Options are expensive — premium buyers at risk of IV crush."
        )

    if days_to_expiry is not None and days_to_expiry <= FO_NEAR_EXPIRY_DAYS:
        flags.append(
            f"⏰ NEAR EXPIRY: {days_to_expiry} day(s) to expiry. "
            f"Theta decay accelerates sharply — high-risk if OTM."
        )

    if open_interest is not None and open_interest < FO_LOW_OI_THRESHOLD:
        flags.append(
            f"⚠️ LOW LIQUIDITY: Open Interest = {open_interest:,} contracts. "
            f"Bid-ask spreads may be wide — entry/exit slippage risk."
        )

    if near_event:
        event_str = f" ({event_name})" if event_name else ""
        flags.append(
            f"📅 EVENT RISK{event_str}: Binary event pending. "
            f"IV may spike or collapse post-event — define risk carefully."
        )

    return flags


# ── Dynamic Risk Sizer ────────────────────────────────────────────────────────

class DynamicRiskSizer:
    """
    Adapts risk-per-trade based on the rolling win-rate of the last N trades.
    Protects capital during drawdown phases by scaling position sizes down
    automatically. Never guesses — always computed from actual shadow portfolio
    history.

    Tiers:
      Win-rate >= 65%  → Full risk (0.75% = ₹75)   — Performing well
      Win-rate 50-65%  → Reduced  (0.50% = ₹50)   — Caution mode
      Win-rate  < 50%  → Minimal  (0.35% = ₹35)   — Capital preservation
      Circuit breaker  → Zero new buys             — Drawdown limit hit
    """

    TIER_FULL      = ("Full",         TOTAL_CAPITAL * 0.0075)   # ₹75
    TIER_REDUCED   = ("Reduced",      TOTAL_CAPITAL * 0.0050)   # ₹50
    TIER_MINIMAL   = ("Preservation", TOTAL_CAPITAL * 0.0035)   # ₹35
    TIER_BLOCKED   = ("Blocked",      0.0)                       # Circuit breaker

    @classmethod
    def get_effective_risk_cap(cls, win_rate_pct: float) -> tuple:
        """
        Returns (tier_label: str, effective_risk_cap: float).
        win_rate_pct: float in range 0.0 – 100.0.
        """
        if win_rate_pct >= 65.0:
            return cls.TIER_FULL
        elif win_rate_pct >= 50.0:
            return cls.TIER_REDUCED
        else:
            return cls.TIER_MINIMAL

    @classmethod
    def format_tier_notice(cls, win_rate_pct: float, last_n: int = 10) -> str:
        """Human-readable explanation of why a tier was chosen."""
        label, cap = cls.get_effective_risk_cap(win_rate_pct)
        return (
            f"Dynamic Risk Tier: {label} | "
            f"Rolling {last_n}-trade win-rate: {win_rate_pct:.1f}% | "
            f"Effective risk cap: ₹{cap:.0f}"
        )


# ── Profile Summary ────────────────────────────────────────────────────────────

def get_profile_summary() -> str:
    """Return a formatted summary of Jay's active trading profile."""
    tickers = ", ".join(w["symbol"] for w in WATCHLIST)
    return (
        f"╔══ JARVIS Trading Profile (Active) ══╗\n"
        f"  Capital          : ₹{TOTAL_CAPITAL:,.0f}\n"
        f"  Risk / Trade     : {RISK_PCT_PER_TRADE*100:.2f}% = ₹{MAX_RISK_PER_TRADE:.0f} hard cap\n"
        f"  Max Positions    : {MAX_CONCURRENT_POSITIONS}\n"
        f"  Horizon          : Swing (2–5 days)\n"
        f"  Stop Style       : ATR-based (1.5×–2× 14-day ATR) | Flat % fallback\n"
        f"  Target Style     : Trailing stop, tighten after {MIN_RR_BEFORE_TRAIL}R\n"
        f"  F&O              : Enabled (with explicit risk flags)\n"
        f"  Low-conf Digest  : 15:30 IST daily\n"
        f"  Watchlist        : {tickers}\n"
        f"  Circuit Breaker  : Pause buys if drawdown > {CIRCUIT_BREAKER_DRAWDOWN_PCT*100:.0f}%\n"
        f"  Data Freshness   : Alert if fetch > {MAX_DATA_AGE_MINUTES} min stale\n"
        f"╚══════════════════════════════════════╝"
    )

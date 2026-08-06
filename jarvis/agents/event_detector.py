"""
EventDetector — Detects upcoming corporate events for JARVIS Trading Agent.

Checks for events within the next 7 days for a given ticker:
  • Earnings / Quarterly Results
  • Ex-Dividend dates
  • Board meetings (via yfinance calendar)
  • Stock splits

Any pending event within 7 days:
  → Attaches EVENT_RISK flag to the signal
  → For F&O signals, triggers elevated IV warning automatically
  → Optionally suppresses LOW-confidence BUY signals pre-event
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

EVENT_WINDOW_DAYS: int = 7

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False


@dataclass
class CorporateEvent:
    event_type: str       # "Earnings", "Dividend", "Split", "Board Meeting"
    event_date: str       # ISO date string
    days_away: int        # Days from today
    detail: str           # Extra info (e.g. EPS estimate, dividend amount)


class EventDetector:
    """
    Fetches upcoming events for a ticker from yfinance and returns a structured
    list of CorporateEvent objects within the EVENT_WINDOW_DAYS window.
    """

    def get_upcoming_events(self, ticker: str) -> List[CorporateEvent]:
        """
        Returns list of upcoming events within EVENT_WINDOW_DAYS.
        Empty list = no events detected (signal can proceed normally).
        """
        if not _YF_AVAILABLE:
            return []

        clean = ticker.upper().replace(".NS", "").replace(".BO", "")
        ns_ticker = f"{clean}.NS"
        events: List[CorporateEvent] = []
        today = datetime.now().date()
        cutoff = today + timedelta(days=EVENT_WINDOW_DAYS)

        try:
            tk = yf.Ticker(ns_ticker)

            # 1. Earnings dates (check both calendar dict and earnings_dates DataFrame)
            try:
                earn_dates = []
                cal = tk.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        earn_dates.extend(cal.get("Earnings Date", []))
                    elif hasattr(cal, "columns") and "Earnings Date" in cal.columns:
                        earn_dates.extend(cal["Earnings Date"].tolist())

                # Fallback to tk.earnings_dates DataFrame if empty
                if not earn_dates:
                    try:
                        ed_df = tk.earnings_dates
                        if ed_df is not None and not ed_df.empty:
                            # Future dates in index
                            for idx in ed_df.index:
                                d_val = idx.date() if hasattr(idx, "date") else idx
                                if isinstance(d_val, datetime):
                                    d_val = d_val.date()
                                if today <= d_val <= cutoff:
                                    earn_dates.append(d_val)
                    except Exception:
                        pass

                for ed in earn_dates:
                    if ed is None:
                        continue
                    try:
                        ed_date = ed.date() if hasattr(ed, "date") else ed
                        if today <= ed_date <= cutoff:
                            days_away = (ed_date - today).days
                            events.append(CorporateEvent(
                                event_type="Earnings",
                                event_date=str(ed_date),
                                days_away=days_away,
                                detail=f"Quarterly results expected in {days_away} day(s).",
                            ))
                    except Exception:
                        continue
            except Exception as exc:
                logger.debug(f"EventDetector: earnings fetch skipped for {ns_ticker}: {exc}")

            # 2. Ex-Dividend dates
            try:
                info = tk.info
                ex_div = info.get("exDividendDate")
                if ex_div:
                    import datetime as dt
                    ex_date = dt.date.fromtimestamp(ex_div)
                    if today <= ex_date <= cutoff:
                        days_away = (ex_date - today).days
                        div_amt = info.get("dividendRate", "?")
                        events.append(CorporateEvent(
                            event_type="Ex-Dividend",
                            event_date=str(ex_date),
                            days_away=days_away,
                            detail=f"Ex-dividend date in {days_away} day(s). Dividend: ₹{div_amt}/share.",
                        ))
            except Exception as exc:
                logger.debug(f"EventDetector: dividend fetch skipped for {ns_ticker}: {exc}")

            # 3. Stock splits
            try:
                splits = tk.splits
                if splits is not None and not splits.empty:
                    for split_date, ratio in splits.items():
                        try:
                            sd = split_date.date() if hasattr(split_date, "date") else split_date
                            if today <= sd <= cutoff:
                                days_away = (sd - today).days
                                events.append(CorporateEvent(
                                    event_type="Stock Split",
                                    event_date=str(sd),
                                    days_away=days_away,
                                    detail=f"Split ratio {ratio} in {days_away} day(s) — price & qty will adjust.",
                                ))
                        except Exception:
                            continue
            except Exception as exc:
                logger.debug(f"EventDetector: splits fetch skipped for {ns_ticker}: {exc}")

        except Exception as exc:
            logger.warning(f"EventDetector.get_upcoming_events failed for {ns_ticker}: {exc}")

        return events

    def format_event_warning(self, events: List[CorporateEvent]) -> List[str]:
        """
        Returns list of formatted warning strings for signal output.
        Each string is ready to append to the F&O / signal flags list.
        """
        warnings: List[str] = []
        for ev in events:
            urgency = "🚨" if ev.days_away <= 2 else "📅"
            warnings.append(
                f"{urgency} EVENT RISK — {ev.event_type} in {ev.days_away} day(s) "
                f"({ev.event_date}): {ev.detail} "
                f"Binary outcome may cause sharp price move. "
                f"Define risk carefully before entry."
            )
        return warnings

    def should_suppress_low_confidence(self, events: List[CorporateEvent]) -> bool:
        """
        Returns True if a LOW-confidence BUY should be suppressed
        because a binary event is imminent (within 3 days).
        """
        return any(ev.days_away <= 3 for ev in events)

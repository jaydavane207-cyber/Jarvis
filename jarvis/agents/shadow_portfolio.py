"""
ShadowPortfolio — 3-month paper trading tracker for JARVIS.

Tracks every buy/sell recommendation over time to measure win-rate and
signal accuracy before using real money. Stored in SQLite (personal.db).

Tables:
  shadow_trades      — individual trade recommendations
  shadow_performance — periodic win-rate snapshots

Manual entry workflow (per PRD):
  - Jay manually logs what recommendations he acted on
  - JARVIS auto-evaluates outcomes at 30/60/90 day checkpoints
"""
from __future__ import annotations
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "personal.db",
)


class ShadowPortfolio:
    """Paper trading tracker with win-rate analysis."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_tables()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS shadow_trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT    NOT NULL,
                    action          TEXT    NOT NULL CHECK(action IN ('BUY','SELL','HOLD')),
                    price_at_rec    REAL    NOT NULL,
                    qty             INTEGER NOT NULL DEFAULT 1,
                    budget_used     REAL    NOT NULL DEFAULT 0,
                    signal_summary  TEXT    NOT NULL DEFAULT '',
                    rec_date        TEXT    NOT NULL,
                    eval_30d        TEXT,
                    eval_60d        TEXT,
                    eval_90d        TEXT,
                    outcome         TEXT,
                    sector          TEXT    DEFAULT '',
                    notes           TEXT    DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS shadow_performance (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_at TEXT    NOT NULL,
                    total_recs  INTEGER NOT NULL DEFAULT 0,
                    wins        INTEGER NOT NULL DEFAULT 0,
                    losses      INTEGER NOT NULL DEFAULT 0,
                    win_rate    REAL    NOT NULL DEFAULT 0.0,
                    notes       TEXT    DEFAULT ''
                );
            """)
            conn.commit()
            conn.close()
            logger.info("ShadowPortfolio: tables ready ✓")
        except Exception as exc:
            logger.error(f"ShadowPortfolio._ensure_tables error: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_recommendation(
        self,
        ticker: str,
        action: str,
        price_at_rec: float,
        qty: int = 1,
        budget_used: float = 0.0,
        signal_summary: str = "",
        sector: str = "",
        notes: str = "",
    ) -> int:
        """Log a new trade recommendation. Returns row id."""
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """INSERT INTO shadow_trades
                   (ticker, action, price_at_rec, qty, budget_used,
                    signal_summary, rec_date, sector, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticker.upper(),
                    action.upper(),
                    price_at_rec,
                    qty,
                    budget_used,
                    signal_summary,
                    datetime.now().isoformat(),
                    sector,
                    notes,
                ),
            )
            row_id = cur.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"ShadowPortfolio: logged {action} {ticker} @ ₹{price_at_rec}")
            return row_id
        except Exception as exc:
            logger.error(f"ShadowPortfolio.add_recommendation error: {exc}")
            return -1

    def evaluate_outcomes(self) -> List[Dict[str, Any]]:
        """
        Auto-evaluate trades at 30/60/90 day checkpoints using live prices.
        Returns list of updated trades.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not available — skipping outcome evaluation")
            return []

        now = datetime.now()
        updated = []

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM shadow_trades WHERE outcome IS NULL"
            ).fetchall()

            for row in rows:
                rec_date = datetime.fromisoformat(row["rec_date"])
                age_days = (now - rec_date).days
                ticker = row["ticker"]

                try:
                    current_price = float(
                        yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1]
                    )
                except Exception:
                    continue

                entry = row["price_at_rec"]
                pct_change = ((current_price - entry) / entry) * 100
                is_win = (
                    (row["action"] == "BUY" and current_price > entry)
                    or (row["action"] == "SELL" and current_price < entry)
                )

                updates: Dict[str, str] = {}
                if age_days >= 30 and not row["eval_30d"]:
                    updates["eval_30d"] = f"₹{current_price:.2f} ({pct_change:+.1f}%)"
                if age_days >= 60 and not row["eval_60d"]:
                    updates["eval_60d"] = f"₹{current_price:.2f} ({pct_change:+.1f}%)"
                if age_days >= 90 and not row["eval_90d"]:
                    updates["eval_90d"] = f"₹{current_price:.2f} ({pct_change:+.1f}%)"
                    updates["outcome"] = "WIN" if is_win else "LOSS"

                if updates:
                    set_clause = ", ".join(f"{k} = ?" for k in updates)
                    conn.execute(
                        f"UPDATE shadow_trades SET {set_clause} WHERE id = ?",
                        (*updates.values(), row["id"]),
                    )
                    updated.append({"id": row["id"], "ticker": ticker, **updates})

            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"ShadowPortfolio.evaluate_outcomes error: {exc}")

        return updated

    def calculate_win_rate(self) -> Dict[str, Any]:
        """Calculate overall win-rate from completed trades."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT outcome FROM shadow_trades WHERE outcome IS NOT NULL"
            ).fetchall()
            conn.close()

            total = len(rows)
            wins = sum(1 for r in rows if r["outcome"] == "WIN")
            losses = total - wins
            win_rate = (wins / total * 100) if total > 0 else 0.0

            return {
                "total": total,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
            }
        except Exception as exc:
            logger.error(f"ShadowPortfolio.calculate_win_rate error: {exc}")
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0}

    def get_all_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent shadow trades."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM shadow_trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"ShadowPortfolio.get_all_trades error: {exc}")
            return []

    def get_portfolio_summary(self) -> str:
        """Format shadow portfolio for inclusion in trading context."""
        trades = self.get_all_trades(20)
        if not trades:
            return "Shadow portfolio is empty (no tracked recommendations yet)."

        stats = self.calculate_win_rate()
        # Sector concentration
        sectors: Dict[str, int] = {}
        active_buys = [t for t in trades if t["action"] == "BUY" and t["outcome"] is None]
        for t in active_buys:
            sec = t.get("sector") or "Unknown"
            sectors[sec] = sectors.get(sec, 0) + 1

        lines = [
            f"Shadow Portfolio: {len(active_buys)} active positions | "
            f"Win Rate: {stats['win_rate']}% ({stats['wins']}W / {stats['losses']}L of {stats['total']} completed)\n"
        ]
        if active_buys:
            lines.append("Active Positions:")
            for t in active_buys[:10]:
                lines.append(
                    f"  {t['ticker']:12} | {t['action']} @ ₹{t['price_at_rec']:.2f} | "
                    f"{t['rec_date'][:10]} | {t['signal_summary'][:60]}"
                )

        # Sector concentration warning
        for sec, count in sectors.items():
            if count / max(len(active_buys), 1) > 0.4:
                lines.append(
                    f"\n⚠️ Sector concentration warning: {count}/{len(active_buys)} positions in {sec}"
                )

        return "\n".join(lines)

    def manual_add(
        self, ticker: str, action: str, price: float, qty: int, signal_summary: str
    ) -> str:
        """Jay manually logs a trade. Returns confirmation string."""
        row_id = self.add_recommendation(ticker, action, price, qty, price * qty, signal_summary)
        if row_id > 0:
            return f"✅ Logged {action} {ticker} @ ₹{price:.2f} (qty {qty}) to shadow portfolio (ID #{row_id})"
        return "❌ Failed to log trade — check logs."

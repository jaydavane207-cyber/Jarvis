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
                    target_price    REAL    DEFAULT 0.0,
                    stop_loss       REAL    DEFAULT 0.0,
                    horizon         TEXT    DEFAULT 'short-term',
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
            # Migration check for target_price / stop_loss / horizon
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(shadow_trades)")
            columns = [row[1] for row in cursor.fetchall()]
            if "target_price" not in columns:
                conn.execute("ALTER TABLE shadow_trades ADD COLUMN target_price REAL DEFAULT 0.0")
            if "stop_loss" not in columns:
                conn.execute("ALTER TABLE shadow_trades ADD COLUMN stop_loss REAL DEFAULT 0.0")
            if "horizon" not in columns:
                conn.execute("ALTER TABLE shadow_trades ADD COLUMN horizon TEXT DEFAULT 'short-term'")
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
        target_price: float = 0.0,
        stop_loss: float = 0.0,
        horizon: str = "short-term",
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
                   (ticker, action, price_at_rec, qty, target_price, stop_loss,
                    horizon, budget_used, signal_summary, rec_date, sector, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticker.upper(),
                    action.upper(),
                    price_at_rec,
                    qty,
                    target_price,
                    stop_loss,
                    horizon,
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
            logger.info(f"ShadowPortfolio: logged {action} {ticker} @ ₹{price_at_rec} (T: ₹{target_price}, SL: ₹{stop_loss})")
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

    def get_current_drawdown_pct(self, initial_capital: float = 10000.0) -> float:
        """Calculate peak-to-trough drawdown % across closed losses and open P&L."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM shadow_trades").fetchall()
            conn.close()

            if not rows:
                return 0.0

            total_loss_inr = 0.0
            for r in rows:
                if r["outcome"] == "LOSS":
                    entry = r["price_at_rec"]
                    stop = r["stop_loss"] if r["stop_loss"] > 0 else entry * 0.95
                    qty = r["qty"]
                    total_loss_inr += abs(entry - stop) * qty

            drawdown_pct = (total_loss_inr / initial_capital) * 100.0
            return round(drawdown_pct, 2)
        except Exception as exc:
            logger.error(f"ShadowPortfolio.get_current_drawdown_pct error: {exc}")
            return 0.0

    def get_self_grading_report(self) -> Dict[str, Any]:
        """Continuous self-grading: hit rate, false positive rate, predictive signal analysis."""
        stats = self.calculate_win_rate()
        total = stats["total"]
        wins = stats["wins"]
        losses = stats["losses"]
        false_positive_rate = (losses / total * 100) if total > 0 else 0.0

        return {
            "total_trades": total,
            "hit_rate_pct": stats["win_rate"],
            "false_positive_rate_pct": round(false_positive_rate, 1),
            "wins": wins,
            "losses": losses,
            "verdict": "Performing within target confidence bounds" if stats["win_rate"] >= 60 else "Underperforming — downweighting weak signals",
        }

    def manual_add(
        self, ticker: str, action: str, price: float, qty: int, signal_summary: str
    ) -> str:
        """Jay manually logs a trade. Returns confirmation string."""
        row_id = self.add_recommendation(ticker, action, price, qty, price * qty, signal_summary)
        if row_id > 0:
            return f"✅ Logged {action} {ticker} @ ₹{price:.2f} (qty {qty}) to shadow portfolio (ID #{row_id})"
        return "❌ Failed to log trade — check logs."

    def get_rolling_win_rate(self, last_n: int = 10) -> float:
        """
        Return win-rate (0.0–100.0) from the last N *closed* trades.
        Used by DynamicRiskSizer to determine the effective risk cap.
        Returns 65.0 (full tier) if fewer than 3 closed trades exist (no data = no penalty).
        """
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT outcome FROM shadow_trades WHERE outcome IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (last_n,),
            ).fetchall()
            conn.close()
            if len(rows) < 3:
                return 65.0   # Insufficient data — default to full tier
            wins = sum(1 for r in rows if r["outcome"] == "WIN")
            return round(wins / len(rows) * 100, 1)
        except Exception as exc:
            logger.error(f"ShadowPortfolio.get_rolling_win_rate error: {exc}")
            return 65.0   # Safe default

    def get_signal_combination_heatmap(self) -> Dict[str, Any]:
        """
        Maps signal_summary strings to win rates so the agent can identify
        which signal combinations are actually predictive vs noise.
        Returns dict: { signal_key: {wins, total, win_rate_pct} }
        """
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT signal_summary, outcome FROM shadow_trades WHERE outcome IS NOT NULL"
            ).fetchall()
            conn.close()

            heatmap: Dict[str, Dict[str, int]] = {}
            for r in rows:
                key = (r["signal_summary"] or "unknown")[:80]
                if key not in heatmap:
                    heatmap[key] = {"wins": 0, "total": 0}
                heatmap[key]["total"] += 1
                if r["outcome"] == "WIN":
                    heatmap[key]["wins"] += 1

            return {
                k: {
                    "wins": v["wins"],
                    "total": v["total"],
                    "win_rate_pct": round(v["wins"] / v["total"] * 100, 1),
                }
                for k, v in heatmap.items()
            }
        except Exception as exc:
            logger.error(f"ShadowPortfolio.get_signal_combination_heatmap error: {exc}")
            return {}

    def get_underperforming_signals(self, threshold: float = 40.0) -> List[str]:
        """
        Return signal combinations with win-rate below threshold (%).
        These should be downweighted or killed in the signal engine.
        """
        heatmap = self.get_signal_combination_heatmap()
        return [
            sig
            for sig, stats in heatmap.items()
            if stats["win_rate_pct"] < threshold and stats["total"] >= 3
        ]

    def format_self_grade_report(self) -> str:
        """Full periodic self-grading report for Jay."""
        stats = self.calculate_win_rate()
        rolling = self.get_rolling_win_rate(10)
        underperforming = self.get_underperforming_signals()
        drawdown = self.get_current_drawdown_pct()

        lines = [
            "╔══ JARVIS Trading Signal Self-Grading Report ══╗",
            f"  All-time trades    : {stats['total']} ({stats['wins']}W / {stats['losses']}L)",
            f"  All-time win rate  : {stats['win_rate']}%",
            f"  Rolling 10-trade WR: {rolling:.1f}%",
            f"  Portfolio drawdown : {drawdown:.2f}%",
        ]
        if underperforming:
            lines.append(f"  Underperforming signals (< 40% WR, ≥ 3 trades):")
            for sig in underperforming[:5]:
                lines.append(f"    ↓ {sig[:70]}")
        else:
            lines.append("  No underperforming signal combinations detected.")
        lines.append("╚═══════════════════════════════════════════════╝")
        return "\n".join(lines)

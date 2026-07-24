"""
BudgetAgent — personal expense and budget tracking for JARVIS.

Separate from the TradingAgent — this is day-to-day money management.

Manual entry workflow (per PRD):
  - Jay enters transactions manually (no bank CSV import initially)
  - JARVIS analyses patterns, flags unusual spending, and reports summaries

Tables:
  budget_transactions — individual expense/income entries
  budget_categories   — custom categories with monthly limits
"""
from __future__ import annotations
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.audit_log import audit_log

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "personal.db",
)

SKILL_CONTEXT = (
    "\n\nFor this request, you are in BUDGET & EXPENSE TRACKING MODE. "
    "Help Jay track, categorise, and analyse his personal spending. "
    "Flag unusual spending vs monthly averages. "
    "Provide actionable savings recommendations. "
    "Be concise and specific — use exact amounts where available."
)


class BudgetAgent:
    """Personal expense tracking agent with anomaly detection."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_tables()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS budget_transactions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT    NOT NULL,
                    amount      REAL    NOT NULL,
                    type        TEXT    NOT NULL CHECK(type IN ('expense','income')),
                    category    TEXT    NOT NULL DEFAULT 'Uncategorized',
                    description TEXT    NOT NULL DEFAULT '',
                    payment_mode TEXT   DEFAULT 'UPI',
                    notes       TEXT    DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS budget_categories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL UNIQUE,
                    monthly_limit REAL  DEFAULT 0,
                    color       TEXT    DEFAULT '#6366f1'
                );
            """)
            # Seed default categories
            defaults = [
                ("Food & Dining", 5000),
                ("Transport", 2000),
                ("Shopping", 3000),
                ("Entertainment", 1500),
                ("Utilities", 2000),
                ("Health", 2000),
                ("Education", 3000),
                ("Investment", 10000),
                ("Rent", 15000),
                ("Miscellaneous", 2000),
            ]
            for name, limit in defaults:
                conn.execute(
                    "INSERT OR IGNORE INTO budget_categories (name, monthly_limit) VALUES (?, ?)",
                    (name, limit),
                )
            conn.commit()
            conn.close()
            logger.info("BudgetAgent: tables ready ✓")
        except Exception as exc:
            logger.error(f"BudgetAgent._ensure_tables error: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────────

    async def handle_stream(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
    ):
        """Handle budget/expense queries."""
        logger.info("BudgetAgent handling query")

        # Quick-add: "add expense 500 food chai" etc.
        quick_add = self._try_quick_add(message)
        if quick_add:
            yield quick_add
            return

        # Build spending context for LLM
        context = self._build_spending_context(message)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT

        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context}]
        )

        async for chunk in llm.chat_stream(messages):
            yield chunk

    def handle(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
    ) -> str:
        quick_add = self._try_quick_add(message)
        if quick_add:
            return quick_add
        context = self._build_spending_context(message)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context}]
        )
        return llm.chat(messages)

    # ── Transaction management ─────────────────────────────────────────────────

    def add_transaction(
        self,
        amount: float,
        tx_type: str,
        category: str = "Miscellaneous",
        description: str = "",
        payment_mode: str = "UPI",
        date: Optional[str] = None,
    ) -> int:
        """Add a transaction. Returns row id."""
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                """INSERT INTO budget_transactions
                   (date, amount, type, category, description, payment_mode)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    date or datetime.now().isoformat(),
                    abs(amount),
                    tx_type.lower(),
                    category,
                    description,
                    payment_mode,
                ),
            )
            row_id = cur.lastrowid
            conn.commit()
            conn.close()
            audit_log.record(
                agent="BudgetAgent",
                action_type="add_transaction",
                details=f"{tx_type} ₹{amount:.0f} | {category} | {description}",
                reasoning="User manual entry",
                tier="read_only",
                approved=1,
            )
            return row_id
        except Exception as exc:
            logger.error(f"BudgetAgent.add_transaction error: {exc}")
            return -1

    def get_monthly_summary(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """Return spending summary for a given month."""
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        month_str = f"{year}-{month:02d}"

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT category, type, SUM(amount) as total
                   FROM budget_transactions
                   WHERE date LIKE ?
                   GROUP BY category, type
                   ORDER BY total DESC""",
                (f"{month_str}%",),
            ).fetchall()
            conn.close()

            expenses: Dict[str, float] = {}
            income_total = 0.0
            for r in rows:
                if r["type"] == "expense":
                    expenses[r["category"]] = r["total"]
                else:
                    income_total += r["total"]

            total_expense = sum(expenses.values())
            return {
                "month": month_str,
                "total_expenses": total_expense,
                "total_income": income_total,
                "net": income_total - total_expense,
                "by_category": expenses,
            }
        except Exception as exc:
            logger.error(f"BudgetAgent.get_monthly_summary error: {exc}")
            return {}

    def detect_anomalies(self) -> List[str]:
        """Compare current month to last 3-month average. Flag unusual spend."""
        anomalies = []
        now = datetime.now()
        current = self.get_monthly_summary(now.year, now.month)

        # Build 3-month average
        prev_months = []
        for delta in range(1, 4):
            dt = now - timedelta(days=delta * 30)
            prev_months.append(self.get_monthly_summary(dt.year, dt.month))

        if not any(p.get("by_category") for p in prev_months):
            return []

        # Average by category
        avg_by_cat: Dict[str, float] = {}
        for p in prev_months:
            for cat, amt in p.get("by_category", {}).items():
                avg_by_cat[cat] = avg_by_cat.get(cat, 0) + amt / 3

        for cat, current_amt in current.get("by_category", {}).items():
            avg = avg_by_cat.get(cat, 0)
            if avg > 0 and current_amt > avg * 1.5:
                anomalies.append(
                    f"⚠️ {cat}: ₹{current_amt:,.0f} this month vs avg ₹{avg:,.0f} "
                    f"(+{(current_amt/avg-1)*100:.0f}% above normal)"
                )
        return anomalies

    # ── Private helpers ────────────────────────────────────────────────────────

    def _try_quick_add(self, message: str) -> Optional[str]:
        """
        Parse quick-add commands like:
          "add expense 500 food chai"
          "log income 30000 salary"
        """
        msg = message.strip().lower()
        match = re.match(
            r"(?:add|log)\s+(expense|income)\s+(\d+(?:\.\d+)?)\s+(\w+)(?:\s+(.+))?",
            msg,
        )
        if not match:
            return None

        tx_type = match.group(1)
        amount = float(match.group(2))
        category_hint = match.group(3).title()
        description = match.group(4) or ""

        # Fuzzy match category
        category = self._match_category(category_hint)
        row_id = self.add_transaction(amount, tx_type, category, description)

        if row_id > 0:
            return (
                f"✅ Logged {tx_type}: ₹{amount:,.0f} in '{category}'"
                + (f" — {description}" if description else "")
                + f" (ID #{row_id})"
            )
        return "❌ Could not log transaction. Please try again."

    def _match_category(self, hint: str) -> str:
        """Fuzzy-match a hint to known categories."""
        categories = [
            "Food & Dining", "Transport", "Shopping", "Entertainment",
            "Utilities", "Health", "Education", "Investment", "Rent", "Miscellaneous"
        ]
        hint_lower = hint.lower()
        for cat in categories:
            if hint_lower in cat.lower() or cat.lower().startswith(hint_lower):
                return cat
        return hint.title()

    def _build_spending_context(self, message: str) -> str:
        """Build spending summary for LLM context."""
        summary = self.get_monthly_summary()
        anomalies = self.detect_anomalies()
        lines = [f"User query: {message}\n"]

        if summary.get("by_category"):
            lines.append(f"This month's spending summary ({summary['month']}):")
            lines.append(f"  Total Expenses : ₹{summary['total_expenses']:,.0f}")
            lines.append(f"  Total Income   : ₹{summary['total_income']:,.0f}")
            lines.append(f"  Net Balance    : ₹{summary['net']:,.0f}")
            lines.append("\nBy Category:")
            for cat, amt in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
                lines.append(f"  {cat:20} ₹{amt:,.0f}")
        else:
            lines.append("No transactions recorded this month yet.")

        if anomalies:
            lines.append("\nSpending Anomalies Detected:")
            lines.extend(anomalies)

        return "\n".join(lines)

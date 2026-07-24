"""
EarningsAgent — NSE/BSE quarterly earnings report ingester and summariser.

Ingests PDFs of quarterly earnings reports (by URL or upload) and extracts:
  • Revenue beats/misses vs estimates
  • EPS (actual vs expected)
  • Management guidance (raised/lowered/maintained)
  • Red flags (debt spikes, margin compression, promoter selling)
  • Key positive catalysts

Cross-Agent Correlation:
  When ResearchAgent detects news about a stock in the shadow portfolio,
  it triggers EarningsAgent + TradingAgent to re-evaluate — instead of
  waiting for the next scheduled watchdog cycle.
"""
from __future__ import annotations
import logging
import os
import re
import io
from typing import Optional, Dict, Any

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.audit_log import audit_log

logger = logging.getLogger(__name__)

# ── Optional PDF dependency ───────────────────────────────────────────────────
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False
    logger.warning("pdfminer.six not installed. PDF parsing disabled.")

try:
    import requests as _req
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

SKILL_CONTEXT = (
    "\n\nFor this request, you are in EARNINGS ANALYSIS MODE. "
    "You have been given the raw text of a quarterly earnings report. "
    "Extract and present:\n"
    "1. Revenue: Actual vs estimate, % beat or miss\n"
    "2. EPS: Actual vs estimate\n"
    "3. Guidance: Raised / Maintained / Lowered\n"
    "4. Red flags: Any debt spikes, margin compression, promoter stake reduction\n"
    "5. Key positives: New contracts, market share gains, cost savings\n"
    "6. Overall verdict: Bullish / Neutral / Bearish for the stock\n"
    "Be concise, use bullet points. Cite exact numbers from the report."
)


class EarningsAgent:
    """Ingests and summarises NSE/BSE earnings reports from PDF or text."""

    def __init__(self):
        self._pdf_enabled = _PDF_AVAILABLE
        self._http_enabled = _REQUESTS_AVAILABLE

    # ── Public API ─────────────────────────────────────────────────────────────

    async def handle_stream(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
        file_content: Optional[str] = None,
        file_name: Optional[str] = None,
    ):
        """Handle earnings query — with optional PDF text already extracted."""
        logger.info("EarningsAgent handling query")

        report_text = ""

        # If file content is provided (base64 decoded by main.py), use it
        if file_content:
            report_text = file_content[:8000]  # cap for LLM context

        # Otherwise, try to fetch from URL in message
        elif self._http_enabled:
            url = self._extract_url(message)
            if url and url.endswith(".pdf"):
                report_text = self._fetch_and_parse_pdf(url)

        context = self._format_context(message, report_text, file_name)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT

        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context}]
        )

        audit_log.record(
            agent="EarningsAgent",
            action_type="earnings_analysis",
            details=f"Query: {message[:80]} | File: {file_name or 'none'} | URL: {self._extract_url(message) or 'none'}",
            reasoning="User requested earnings report analysis",
            tier="read_only",
            approved=0,
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
        file_content: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> str:
        """Synchronous fallback."""
        report_text = file_content[:8000] if file_content else ""
        context = self._format_context(message, report_text, file_name)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context}]
        )
        return llm.chat(messages)

    # ── Cross-Agent Correlation hook ───────────────────────────────────────────

    async def cross_correlate_stream(
        self,
        ticker: str,
        news_summary: str,
        llm: OllamaClient,
        voice_mode: str = "calm_male",
    ):
        """
        Called by WatchdogManager when ResearchAgent detects news about
        a held stock. Re-evaluates position with the fresh news context.
        """
        logger.info(f"EarningsAgent cross-correlation triggered for {ticker}")
        prompt = (
            f"ResearchAgent has detected new market news about {ticker} that is in "
            f"the shadow portfolio.\n\n"
            f"News Summary:\n{news_summary}\n\n"
            f"Re-evaluate the current {ticker} position in the shadow portfolio. "
            f"Should we hold, buy more, or sell? Cite specific signals."
        )
        try:
            from .trading_agent import TradingAgent
            ta = TradingAgent()
            async for chunk in ta.handle_stream(prompt, llm, [], voice_mode=voice_mode):
                yield chunk
        except Exception as exc:
            logger.error(f"EarningsAgent.cross_correlate_stream error: {exc}")
            yield f"Cross-correlation analysis failed: {exc}"

    # ── Private helpers ────────────────────────────────────────────────────────

    def _fetch_and_parse_pdf(self, url: str) -> str:
        """Download a PDF from URL and extract text."""
        if not self._pdf_enabled or not self._http_enabled:
            return ""
        try:
            resp = _req.get(url, timeout=15, headers={"User-Agent": "JARVIS/1.0"})
            resp.raise_for_status()
            pdf_bytes = io.BytesIO(resp.content)
            text = pdf_extract_text(pdf_bytes)
            return text[:8000] if text else ""
        except Exception as exc:
            logger.error(f"EarningsAgent._fetch_and_parse_pdf error: {exc}")
            return ""

    @staticmethod
    def _extract_url(message: str) -> Optional[str]:
        """Extract first URL from message."""
        match = re.search(r"https?://\S+", message)
        return match.group(0) if match else None

    @staticmethod
    def _format_context(message: str, report_text: str, file_name: Optional[str]) -> str:
        lines = [f"User query: {message}\n"]
        if file_name:
            lines.append(f"Report file: {file_name}")
        if report_text:
            lines.append(f"\nEarnings Report Text (first 8000 chars):\n{report_text}")
        else:
            lines.append(
                "\nNo report text was extracted. "
                "Provide guidance on how to interpret earnings reports generally, "
                "or ask Jay to attach the PDF directly."
            )
        return "\n".join(lines)

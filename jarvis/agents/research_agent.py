"""
ResearchAgent — gives JARVIS real-time internet access.

Uses DuckDuckGo (no API key required) to search the web, fetches the top
result pages, and summarises the findings through the LLM.
"""
from __future__ import annotations
import logging
import re
from typing import List, Optional

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)

# ── Optional heavy dependencies ───────────────────────────────────────────────

try:
    from duckduckgo_search import DDGS
    _DDG_AVAILABLE = True
except ImportError:
    _DDG_AVAILABLE = False
    logger.warning("duckduckgo-search not installed. Web research disabled.")

try:
    import requests as _requests
    from bs4 import BeautifulSoup
    _SCRAPE_AVAILABLE = True
except ImportError:
    _SCRAPE_AVAILABLE = False


class ResearchAgent:
    """
    Handles queries that require live web information.

    Pipeline:
      1. Extract search query from the user's message
      2. Search DuckDuckGo for top results
      3. Optionally scrape the best result page
      4. Summarise with JARVIS LLM
    """

    MAX_RESULTS = 5
    MAX_BODY_CHARS = 3000   # cap scraped page content
    SCRAPE_TIMEOUT = 8      # seconds

    SKILL_CONTEXT = (
        "\n\nFor this request, you are in WEB RESEARCH MODE. "
        "You have been given live search results from the internet. "
        "Synthesise them into a clear, factual summary. "
        "Cite sources where relevant. Be concise yet thorough."
    )

    def __init__(self):
        self._enabled = _DDG_AVAILABLE

    # ── Public API ────────────────────────────────────────────────────────────

    def handle(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male") -> str:
        """Synchronous: search + summarise."""
        if not self._enabled:
            return (
                "I'm afraid my web research capability is currently offline, Jay. "
                "The duckduckgo-search package is not installed."
            )

        query = self._extract_query(message)
        logger.info(f"ResearchAgent searching: '{query}'")

        snippets = self._search(query)
        if not snippets:
            return (
                f"I searched for '{query}' but found no relevant results, Jay. "
                "This may be a network issue or a very niche topic."
            )

        context = self._format_snippets(snippets, query)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.SKILL_CONTEXT
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": f"Search query: {query}\n\n{context}"}]
        )
        return llm.chat(messages)

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Async streaming version."""
        if not self._enabled:
            yield (
                "I'm afraid my web research capability is currently offline, Jay. "
                "The duckduckgo-search package is not installed."
            )
            return

        query = self._extract_query(message)
        logger.info(f"ResearchAgent streaming search: '{query}'")

        snippets = self._search(query)
        if not snippets:
            yield (
                f"I searched for '{query}' but found no relevant results, Jay."
            )
            return

        context = self._format_snippets(snippets, query)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.SKILL_CONTEXT
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": f"Search query: {query}\n\n{context}"}]
        )
        async for chunk in llm.chat_stream(messages):
            yield chunk

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_query(self, message: str) -> str:
        """Strip common search preambles to get the raw query."""
        cleaned = re.sub(
            r"^(?:search\s+(?:for|the\s+web\s+for)?|look\s+up|find\s+(?:information\s+(?:on|about))?|"
            r"what(?:'s|\s+is)\s+(?:the\s+)?(?:latest\s+)?(?:on|about)?|"
            r"tell\s+me\s+about|news\s+(?:on|about)?|research)\s+",
            "",
            message.strip(),
            flags=re.IGNORECASE,
        ).strip(" ?.,")
        return cleaned if len(cleaned) > 3 else message.strip()

    def _search(self, query: str) -> List[dict]:
        """Run DuckDuckGo text search and return structured results."""
        # Detect if it's an academic search
        is_academic = any(k in query.lower() for k in ["academic", "paper", "journal", "research paper"])
        search_query = query
        if is_academic:
            logger.info("Academic search detected, augmenting query")
            # DuckDuckGo supports basic site search and terms
            search_query += " (site:arxiv.org OR site:edu)"
            
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=self.MAX_RESULTS))
            return results
        except Exception as exc:
            logger.error(f"DuckDuckGo search error: {exc}")
            return []

    def _fetch_page(self, url: str) -> str:
        """Lightly scrape a URL and return its main text content."""
        if not _SCRAPE_AVAILABLE:
            return ""
        try:
            resp = _requests.get(
                url,
                timeout=self.SCRAPE_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JARVIS/1.0)"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove scripts, styles, nav, footer
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            return text[: self.MAX_BODY_CHARS]
        except Exception:
            return ""

    def _format_snippets(self, snippets: List[dict], query: str) -> str:
        """Format search results into a context block for the LLM."""
        lines = [f"Live web search results for: '{query}'\n"]
        for i, s in enumerate(snippets[:self.MAX_RESULTS], 1):
            title = s.get("title", "No title")
            body  = s.get("body",  "No description")
            href  = s.get("href",  "")
            lines.append(f"[{i}] {title}")
            lines.append(f"    {body}")
            if href:
                lines.append(f"    Source: {href}")
            lines.append("")
        return "\n".join(lines)

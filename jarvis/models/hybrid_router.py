"""
HybridLLMRouter — automatically routes LLM calls to local (Ollama) or
cloud (Anthropic Claude) based on a complexity heuristic.

Local = fast, free, private (Ollama)
Cloud = powerful, accurate for hard tasks (Anthropic)

The routing threshold is set via config.cloud_threshold (default 0.65).
"""
from __future__ import annotations
import logging
import re
from typing import List, Dict, AsyncGenerator

from ..config import settings
from .ollama_client import OllamaClient
from .cloud_client import AnthropicClient

logger = logging.getLogger(__name__)

# ── Keywords that indicate a complex request ───────────────────────────────────

_COMPLEX_KEYWORDS = {
    "compare", "analyse", "analyze", "synthesise", "synthesize",
    "comprehensive", "critique", "evaluate", "dissertation",
    "research paper", "prove", "derive", "in-depth", "in depth",
    "thoroughly", "academic", "thesis", "peer review",
    "explain everything", "explain in detail",
}

_SIMPLE_KEYWORDS = {
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay",
    "yes", "no", "sure", "great", "cool",
}


class HybridLLMRouter:
    """
    Drop-in replacement for OllamaClient that transparently routes to the
    best model based on query complexity.

    Falls back to Ollama if:
      - ANTHROPIC_API_KEY is not set
      - Cloud call fails
      - Message is below the complexity threshold
    """

    def __init__(self):
        self._local = OllamaClient()
        self._cloud = AnthropicClient()
        self._threshold = settings.cloud_threshold
        logger.info(
            f"HybridLLMRouter: local={self._local.model} | "
            f"cloud={'enabled' if self._cloud.enabled else 'disabled (no API key)'} | "
            f"threshold={self._threshold}"
        )

    # ── Public API (same interface as OllamaClient) ───────────────────────────

    @property
    def model(self) -> str:
        return self._local.model

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Route to cloud or local based on complexity; return full reply."""
        user_content = self._extract_user_content(messages)
        score = self._complexity_score(user_content)
        use_cloud = self._cloud.enabled and score >= self._threshold

        if use_cloud:
            logger.info(
                f"HybridLLMRouter → CLOUD (score={score:.2f}, "
                f"threshold={self._threshold})"
            )
            try:
                return self._cloud.chat(messages)
            except Exception as exc:
                logger.warning(f"Cloud LLM failed, falling back to local: {exc}")

        logger.info(f"HybridLLMRouter → LOCAL (score={score:.2f})")
        return self._local.chat(messages)

    async def chat_stream(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """Route to cloud or local; yield tokens as they arrive."""
        user_content = self._extract_user_content(messages)
        score = self._complexity_score(user_content)
        use_cloud = self._cloud.enabled and score >= self._threshold

        if use_cloud:
            logger.info(
                f"HybridLLMRouter → CLOUD stream (score={score:.2f})"
            )
            try:
                async for chunk in self._cloud.chat_stream(messages):
                    yield chunk
                return
            except Exception as exc:
                logger.warning(f"Cloud stream failed, falling back to local: {exc}")

        logger.info(f"HybridLLMRouter → LOCAL stream (score={score:.2f})")
        async for chunk in self._local.chat_stream(messages):
            yield chunk

    # ── Complexity scorer ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_user_content(messages: List[Dict[str, str]]) -> str:
        """Return the last user message content."""
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return ""

    def _complexity_score(self, text: str) -> float:
        """
        Score 0.0–1.0 indicating query complexity.

        Factors:
          - Message word count
          - Complex/analytical keyword presence
          - Attached code length (long code → cloud for deep review)
          - Multi-step reasoning indicators
        """
        if not text:
            return 0.0

        text_lower = text.lower()
        words = text.split()
        score = 0.0

        # Immediately return 0 for trivially simple greetings
        if any(kw == text_lower.strip() for kw in _SIMPLE_KEYWORDS):
            return 0.0

        # Word count
        wc = len(words)
        if wc > 200:
            score += 0.35
        elif wc > 100:
            score += 0.20
        elif wc > 50:
            score += 0.10

        # Complex keywords
        for kw in _COMPLEX_KEYWORDS:
            if kw in text_lower:
                score += 0.25
                break

        # Multi-step reasoning phrases
        reasoning_patterns = [
            r"step.by.step", r"in\s+detail", r"walk\s+me\s+through",
            r"explain\s+how", r"why\s+does", r"what\s+are\s+the\s+pros\s+and\s+cons",
        ]
        for pat in reasoning_patterns:
            if re.search(pat, text_lower):
                score += 0.15
                break

        # Embedded code block length
        code_matches = re.findall(r"```[\s\S]*?```", text)
        total_code_lines = sum(c.count("\n") for c in code_matches)
        if total_code_lines > 50:
            score += 0.30
        elif total_code_lines > 20:
            score += 0.15

        return min(1.0, score)

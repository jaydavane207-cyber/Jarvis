"""
CloudClient — wraps the Anthropic API with streaming support.

Falls back gracefully if ANTHROPIC_API_KEY is not set.

Network error handling
──────────────────────
WindowsWSARECV / connection-forcibly-closed errors (e.g. TCP reset from
Google infra mid-stream) are caught *inside* the async generator so they
don't propagate as unhandled exceptions and crash the WebSocket handler.
When a mid-stream reset is detected a RuntimeError is raised so the hybrid
router can fall back to the local Ollama model.
"""
from __future__ import annotations
import logging
from typing import List, Dict, AsyncGenerator, Generator

from ..config import settings

logger = logging.getLogger(__name__)

try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Cloud LLM disabled.")


class AnthropicClient:
    """
    Thin wrapper around the Anthropic Messages API.

    Supports:
      - chat(messages)        → synchronous str
      - chat_stream(messages) → async token generator
    """

    MAX_TOKENS = 4096

    def __init__(self):
        self._client = None
        self._async_client = None
        self.model = settings.cloud_model or "claude-sonnet-4-5"
        self._enabled = False

        if not _ANTHROPIC_AVAILABLE:
            return

        key = settings.anthropic_api_key
        if not key:
            logger.info(
                "AnthropicClient: ANTHROPIC_API_KEY not set — cloud LLM disabled."
            )
            return

        try:
            self._client = _anthropic.Anthropic(api_key=key)
            self._async_client = _anthropic.AsyncAnthropic(api_key=key)
            self._enabled = True
            logger.info(f"AnthropicClient: ready (model={self.model})")
        except Exception as exc:
            logger.error(f"AnthropicClient init error: {exc}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _split_messages(
        messages: List[Dict[str, str]],
    ) -> tuple[str, List[Dict[str, str]]]:
        """Separate system prompt from conversation history for Anthropic API."""
        system = ""
        conv: List[Dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                conv.append(m)
        return system, conv

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Synchronous multi-turn chat. Raises RuntimeError on failure."""
        if not self._enabled:
            raise RuntimeError("Anthropic client not enabled")
        system, conv = self._split_messages(messages)
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                system=system or "You are JARVIS, a highly intelligent AI assistant.",
                messages=conv,
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.error(f"AnthropicClient.chat error: {exc}")
            raise RuntimeError(f"Cloud LLM error: {exc}") from exc

    async def chat_stream(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """
        Async streaming chat. Yields tokens as strings.

        Mid-stream TCP resets (Windows wsarecv error, connection forcibly
        closed by remote host) are caught inside the generator so they don't
        silently corrupt the WebSocket frame sequence.  A RuntimeError is
        raised cleanly so HybridLLMRouter can fall back to local Ollama.
        """
        if not self._enabled:
            raise RuntimeError("Anthropic client not enabled")
        system, conv = self._split_messages(messages)
        tokens_yielded = 0
        try:
            async with self._async_client.messages.stream(
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                system=system or "You are JARVIS, a highly intelligent AI assistant.",
                messages=conv,
            ) as stream:
                try:
                    async for text in stream.text_stream:
                        tokens_yielded += 1
                        yield text
                except Exception as mid_exc:
                    # Mid-stream network reset (e.g. wsarecv connection reset)
                    logger.warning(
                        "AnthropicClient: mid-stream error after %d tokens — %s",
                        tokens_yielded, mid_exc
                    )
                    raise RuntimeError(
                        f"Cloud LLM stream interrupted after {tokens_yielded} tokens: {mid_exc}"
                    ) from mid_exc
        except RuntimeError:
            raise  # already wrapped above — let hybrid router handle it
        except Exception as exc:
            logger.error("AnthropicClient.chat_stream setup error: %s", exc)
            raise RuntimeError(f"Cloud LLM stream error: {exc}") from exc

import logging
from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)


class CoderAgent:
    """Provides coding-specific context to inject into the JARVIS system prompt."""

    def get_skill_context(self, message: str) -> str:
        return (
            "\n\nFor this request, you are in CODING MODE. "
            "Provide clean, working code with brief explanations. "
            "If writing code, wrap it in appropriate code blocks. "
            "Since your output may be spoken, briefly summarize what the code does before showing it."
        )

    def handle(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male") -> str:
        """Generate a coding response via the LLM synchronously."""
        logger.info("CoderAgent building coding prompt")
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        return llm.chat(messages)

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Generate a coding response via the LLM as a stream."""
        logger.info("CoderAgent building coding prompt")
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        async for chunk in llm.chat_stream(messages):
            yield chunk

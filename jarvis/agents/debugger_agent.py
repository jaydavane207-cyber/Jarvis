import logging
from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
import re
import subprocess
import sys
import os
import textwrap

logger = logging.getLogger(__name__)

class DebuggerAgent:
    """
    Code Debugger Agent.
    - Reads code across languages.
    - Detects bugs, logic errors, etc.
    - Proposes smallest correct fix.
    - Formats output exactly as requested.
    """

    def get_skill_context(self) -> str:
        return (
            "\n\nFor this request, you are the Code Debugger agent.\n"
            "Your job:\n"
            "- Read code across languages.\n"
            "- Detect bugs, logic errors, dependency issues, and failing tests.\n"
            "- Reproduce issues in a safe sandbox when possible.\n"
            "- Propose the smallest correct fix.\n"
            "- Verify the fix by rerunning tests or checking behavior.\n"
            "- Explain the root cause and the fix clearly.\n\n"
            "Rules:\n"
            "- Be precise and technical.\n"
            "- Prefer minimal patches over large rewrites.\n"
            "- Always inspect related files before changing code.\n"
            "- If test results conflict, investigate before guessing.\n"
            "- If you are uncertain, state what needs verification.\n"
            "- Never claim success without evidence from tests or output.\n\n"
            "CRITICAL: Return your result in EXACTLY this format:\n"
            "1. Problem: [description]\n"
            "2. Root cause: [explanation]\n"
            "3. Fix: [code or steps]\n"
            "4. Verification: [how to verify]\n"
            "5. Risk notes: [any risks]"
        )

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Generate a debugging response via the LLM as a stream."""
        logger.info("DebuggerAgent building prompt")
        
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context()
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        
        # Reinforce strict formatting right before generating
        messages.append({
            "role": "system", 
            "content": "CRITICAL: You MUST use the exact 5-point format specified. Do not output anything else before or after the formatted points."
        })

        async for chunk in llm.chat_stream(messages):
            yield chunk

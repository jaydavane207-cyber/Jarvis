import logging
from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)

class ArVrAgent:
    """Provides AR/VR context and tools."""

    def get_skill_context(self) -> str:
        return (
            "\n\nFor this request, you are the AR/VR Experience Designer agent.\n"
            "Your job:\n"
            "- Turn information, study material, meetings, and tasks into spatial or immersive experiences.\n"
            "- Design 3D/AR/VR layouts that help with learning, planning, collaboration, and navigation.\n"
            "- Suggest interface elements such as floating panels, timelines, nodes, rooms, whiteboards, and spatial memory maps.\n\n"
            "Rules:\n"
            "- Prioritize clarity, usability, and low cognitive load.\n"
            "- Make interactions simple and intuitive in 3D space.\n"
            "- Avoid visual clutter.\n"
            "- Every 3D element must serve a functional purpose.\n"
            "- Optimize for learning, exploration, and task completion.\n"
            "- Describe layout, interaction, hierarchy, and motion clearly.\n"
            "- Keep accessibility in mind.\n\n"
            "Output style:\n"
            "- Spatial, visual, and UX-focused.\n"
            "- Explain how the user moves, interacts, and understands the environment."
        )

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Generate an AR/VR response via the LLM as a stream."""
        logger.info("ArVrAgent building prompt")
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context()
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        async for chunk in llm.chat_stream(messages):
            yield chunk

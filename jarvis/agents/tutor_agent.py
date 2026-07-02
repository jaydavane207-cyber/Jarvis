import logging
import re
from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)

class TutorAgent:
    """
    Handles Study & Learning Features:
    - Smart Note-Taking (Summarization)
    - Q&A Tutor (Math, Science, Coding)
    - Study Planner (Scheduling)
    - Flashcard Generator
    """

    def _determine_mode(self, message: str) -> str:
        msg_lower = message.lower()
        if any(k in msg_lower for k in ["flashcard", "flash card"]):
            return "flashcard"
        if any(k in msg_lower for k in ["study plan", "schedule", "timetable", "study schedule"]):
            return "planner"
        if any(k in msg_lower for k in ["summarize", "summarise", "notes", "note-taking"]):
            return "notes"
        if any(k in msg_lower for k in ["mindmap", "mind map", "visualize", "diagram", "draw architecture", "graph", "chart", "flowchart"]):
            return "mindmap"
        if any(k in msg_lower for k in ["quiz me", "mock interview", "test me", "oral exam"]):
            return "quiz"
        return "tutor"

    def get_skill_context(self, message: str, mode: str) -> str:
        base_context = "\n\nFor this request, you are acting as an EXPERT STUDY TUTOR. "
        
        if mode == "flashcard":
            return base_context + (
                "The user wants flashcards for revision. "
                "You MUST output the flashcards in the following format: "
                "\n[FLASHCARD] Front: <Question> | Back: <Answer> [/FLASHCARD]\n"
                "Do this for each flashcard. Provide at least 3-5 flashcards unless specified otherwise."
            )
        elif mode == "planner":
            return base_context + (
                "The user wants a study plan or schedule. "
                "Format the plan beautifully using Markdown tables, grouping by days or weeks, "
                "and clearly allocate time for difficult vs. easy topics based on upcoming deadlines."
            )
        elif mode == "notes":
            return base_context + (
                "The user wants notes or a summary of provided text/files. "
                "Extract the most important points. Structure your response with clear headings, "
                "bullet points, and highlight key terms."
            )
        elif mode == "mindmap":
            return base_context + (
                "The user wants a visual representation. You MUST output a Mermaid graph wrapped exactly in:\n"
                "\n[MINDMAP]\n<mermaid code here>\n[/MINDMAP]\n"
                "CRITICAL: Do NOT wrap the mermaid code in markdown codeblocks (e.g., ```mermaid). Just raw mermaid syntax inside the MINDMAP tags.\n"
                "CRITICAL: Choose the BEST diagram type for the request:\n"
                "- `stateDiagram-v2` for FSMs (Finite State Machines) or lifecycles.\n"
                "- `sequenceDiagram` for communication protocols (I2C, SPI, UART timing).\n"
                "- `gantt` for schedules or timing diagrams.\n"
                "- `graph TD` or `mindmap` for structural concepts (like architecture).\n"
                "Ensure you use rich Mermaid styling (e.g., classDef for colors, node shapes) to make it look premium."
            )
        elif mode == "quiz":
            return base_context + (
                "The user wants to be quizzed interactively. "
                "You are the examiner. Ask ONLY ONE question at a time. "
                "If the user has just answered a previous question, grade their answer briefly, correct any mistakes, and then ask the next question. "
                "IMPORTANT: You MUST append the exact tag [AWAITING_ANSWER] at the very end of your response. This will automatically turn on the user's microphone."
            )
        else:
            return base_context + (
                "Provide a step-by-step Socratic explanation for the user's question. "
                "For Math, Science, and Coding (especially Assembly/8086/ARM), be technically rigorous but easy to understand. "
                "Do not just give the answer; explain the 'why' behind it."
            )

    def handle(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male") -> str:
        """Generate a tutor response via the LLM synchronously."""
        logger.info("TutorAgent handling request")
        mode = self._determine_mode(message)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message, mode)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        return llm.chat(messages)

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Generate a tutor response via the LLM as a stream."""
        logger.info("TutorAgent streaming request")
        mode = self._determine_mode(message)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message, mode)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        async for chunk in llm.chat_stream(messages):
            yield chunk

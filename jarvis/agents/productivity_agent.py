import logging
import re
from ..models.hybrid_router import HybridLLMRouter
from .planner import get_jarvis_system_prompt
from .executor_agent import ExecutorAgent

logger = logging.getLogger(__name__)

class ProductivityAgent:
    """
    Handles Work & Productivity Features:
    - Task Manager
    - Document Assistant
    - Email Composer
    - Meeting Notes
    - Data Analyzer
    """

    def _determine_mode(self, message: str) -> str:
        msg_lower = message.lower()
        if any(k in msg_lower for k in ["task manager", "daily task", "task list", "todo list", "deadlines"]):
            return "task"
        if any(k in msg_lower for k in ["email", "draft professional email", "compose email"]):
            return "email"
        if any(k in msg_lower for k in ["meeting notes", "summarize meeting", "action items"]):
            return "meeting"
        if any(k in msg_lower for k in ["analyze spreadsheet", "generate chart", "find insights", "data analysis", "data analyzer"]):
            return "data"
        if any(k in msg_lower for k in ["document assistant", "summarize document", "edit document", "format document"]):
            return "document"
        if any(k in msg_lower for k in ["generate pdf", "generate invoice", "create docx", "generate report", "downloadable pdf", "downloadable docx"]):
            return "doc_gen"
        # Fallback to general productivity
        return "general"

    def get_skill_context(self, message: str, mode: str) -> str:
        base_context = "\n\nFor this request, you are acting as an EXPERT WORK AND PRODUCTIVITY ASSISTANT. "
        
        if mode == "task":
            return base_context + (
                "The user wants to manage their tasks. "
                "You MUST output the task list in the following format so the frontend can render it beautifully: "
                "\n[TASK_LIST]\n<Markdown list of tasks with priorities and deadlines>\n[/TASK_LIST]\n"
                "Ensure the content inside is standard markdown (e.g., bullets or checkboxes)."
            )
        elif mode == "email":
            return base_context + (
                "The user wants you to draft an email. "
                "You MUST output the email draft in the following format: "
                "\n[EMAIL_DRAFT]\nSubject: <Subject>\n\n<Body of the email>\n[/EMAIL_DRAFT]\n"
            )
        elif mode == "meeting":
            return base_context + (
                "The user wants meeting notes or action items. "
                "Extract the most important action items, decisions, and summaries. "
                "You MUST output the meeting notes in the following format: "
                "\n[MEETING_NOTES]\n<Markdown structured meeting notes>\n[/MEETING_NOTES]\n"
            )
        elif mode == "data":
            return base_context + (
                "The user wants data analysis, charts, or insights. "
                "Write a Python script inside ```python ... ``` that uses `pandas` and `matplotlib` to analyze the data and generate a chart. "
                "CRITICAL: Do NOT use plt.show(). Save the plot to a BytesIO object, base64 encode it, and print it to stdout "
                "exactly in this format: [IMAGE]data:image/png;base64,...[/IMAGE]. "
                "Also print clear, bulleted textual insights based on the data before the image tag."
            )
        elif mode == "document":
            return base_context + (
                "The user wants document formatting, editing, or summarization. "
                "Provide a clear, well-structured output. If summarizing, highlight the main points and key takeaways. "
                "You MUST output the result in the following format: "
                "\n[DOC_SUMMARY]\n<Markdown formatted document summary/edits>\n[/DOC_SUMMARY]\n"
            )
        elif mode == "doc_gen":
            return base_context + (
                "The user wants to generate a downloadable PDF or DOCX file. "
                "Write a Python script inside ```python ... ``` that uses `fpdf2` (from fpdf import FPDF) or `python-docx` (from docx import Document) to generate a beautifully formatted document. "
                "Save the file locally (e.g., invoice.pdf or report.docx). "
                "Print a success message and the absolute path of the generated file to stdout."
            )
        else:
            return base_context + (
                "Assist the user with their productivity tasks, providing clear, actionable, and professional responses."
            )

    def handle(self, message: str, llm: HybridLLMRouter, history: list, semantic: str = "", voice_mode: str = "calm_male") -> str:
        """Generate a productivity response via the LLM synchronously."""
        logger.info("ProductivityAgent handling request")
        mode = self._determine_mode(message)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message, mode)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        
        if mode in ("data", "doc_gen"):
            raw_response = llm.chat(messages)
            code = ExecutorAgent._extract_code(raw_response)
            if not code:
                return "I couldn't write the Python code to fulfill your request. Here is what I thought:\n" + raw_response
            stdout, stderr, timed_out = ExecutorAgent._run(code)
            
            reply = f"Here is the result of your request:\n\n{stdout}"
            if stderr:
                reply += f"\n\n**Warnings/Errors:**\n```\n{stderr}\n```"
            if timed_out:
                reply += "\n\n⚠️ **Execution timed out.**"
            return reply

        return llm.chat(messages)

    async def handle_stream(self, message: str, llm: HybridLLMRouter, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Generate a productivity response via the LLM as a stream."""
        logger.info("ProductivityAgent streaming request")
        mode = self._determine_mode(message)
        
        if mode in ("data", "doc_gen"):
            result = self.handle(message, llm, history, semantic, voice_mode)
            yield result
            return

        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message, mode)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        async for chunk in llm.chat_stream(messages):
            yield chunk

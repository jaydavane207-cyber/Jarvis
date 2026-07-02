"""
AgentRouter — the central dispatcher for all JARVIS capabilities.

Routing priority (highest → lowest):
  1. Reminder    — set/list/cancel reminders (no LLM needed)
  2. Smart Home  — control HA devices (no LLM needed)
  3. Executor    — run/execute Python code
  4. Research    — live web search
  5. Planner     — planning, scheduling, goals
  6. Coder       — write/debug/review code
  7. General LLM — everything else (fallback)

Every route() / route_stream() call:
  - Saves user turn to SQLite memory
  - Retrieves relevant past context from vector memory (semantic search)
  - Saves JARVIS reply to both SQLite and vector store
  - Logs routing decision + latency for the dashboard
"""
from __future__ import annotations
import time
import logging
from typing import AsyncGenerator, Optional

from .planner import PlannerAgent, get_jarvis_system_prompt
from .coder import CoderAgent
from .reminder_agent import ReminderAgent
from .research_agent import ResearchAgent
from .smarthome_agent import SmartHomeAgent
from .executor_agent import ExecutorAgent
from .tutor_agent import TutorAgent
from .image_agent import ImageAgent
from .productivity_agent import ProductivityAgent
from .communication_agent import CommunicationAgent
from .personal_agent import PersonalAgent
from .debugger_agent import DebuggerAgent
from .arvr_agent import ArVrAgent
from ..models.hybrid_router import HybridLLMRouter
from ..memory.sqlite_store import SQLiteStore
from ..memory.vector_store import VectorStore
from ..memory.supabase_store import SupabaseChatStore, SupabaseVectorStore
from ..config import settings

logger = logging.getLogger(__name__)


# ── Keyword routing tables ────────────────────────────────────────────────────

_REMINDER_KEYWORDS = (
    "remind me", "set a reminder", "set a timer", "set alarm",
    "alarm for", "remind me to", "my reminders", "show reminders",
    "cancel reminder", "clear reminder", "what are my reminder",
)

_SMARTHOME_KEYWORDS = (
    "turn on the", "turn off the", "switch on", "switch off",
    "lock the", "unlock the", "open the garage", "close the garage",
    "set the thermostat", "set thermostat", "dim the", "brighten the",
    "lights on", "lights off",
)

_EXECUTOR_KEYWORDS = (
    "run this", "run the code", "execute this", "execute the code",
    "run this code", "test this code", "what does this output",
    "what will this print", "run it", "execute it",
)

_RESEARCH_KEYWORDS = (
    "search for", "search the web", "look up", "look it up",
    "find information about", "find info on", "latest news",
    "what's the latest on", "what is the latest on",
    "news about", "tell me about the latest",
    "research", "what's happening with",
)

_PLANNING_KEYWORDS = (
    "plan", "schedule", "goal", "task list", "roadmap",
    "deadline", "milestones", "project plan", "weekly plan",
)

_CODING_KEYWORDS = (
    "write code", "code for", "implement", "debug", "fix the bug",
    "fix this", "error in", "bug in", "script to", "function to",
    "algorithm", "program that", "attached file", "this file",
    "explain this code", "review this code", "what does this code",
    "refactor", "optimise this", "optimize this",
)

_STUDY_KEYWORDS = (
    "flashcard", "flash card", "study plan", "study schedule",
    "summarize", "summarise", "tutor", "explain math", "explain science",
    "note-taking", "revision notes", "mindmap", "mind map", "visualize", 
    "diagram", "draw architecture", "quiz me", "mock interview", 
    "test me", "oral exam", "graph", "chart", "flowchart"
)

_IMAGE_KEYWORDS = (
    "generate image", "create image", "make an image", "draw",
    "paint", "show me a picture of", "generate a picture",
    "generate photo", "generate illustration",
    "create a picture", "create a photo", "picture of",
    "image of", "photo of"
)

_PRODUCTIVITY_KEYWORDS = (
    "task manager", "daily task", "task list", "todo list", "deadlines",
    "draft an email", "draft professional email", "compose email", "send an email",
    "meeting notes", "summarize meeting", "action items",
    "analyze spreadsheet", "generate chart", "find insights", "data analysis", "data analyzer",
    "document assistant", "summarize document", "edit document", "format document"
)

_COMMUNICATION_KEYWORDS = (
    # Chat assistant
    "suggest response", "suggest a response", "suggest reply",
    "improve this message", "improve my message", "improve my text",
    "rephrase this", "rewrite this", "reword this",
    "make it clearer", "make this clearer", "make it professional",
    "match tone", "change tone", "help me reply", "how should i reply",
    "what should i say", "help me respond",
    # Voice call
    "call summary", "summarize call", "summarise call",
    "call notes", "voice call", "transcribe call",
    "from this call", "follow-up from call", "action items from call",
    "key points from call", "what was discussed", "call transcript",
    "meeting transcript",
    # Translation
    "translate this", "translate to", "translate into",
    "say this in", "how do you say", "how to say",
    "translate message", "language translate", "translate the following",
    "in spanish", "in french", "in hindi", "in japanese", "in german",
    "in arabic", "in chinese", "in portuguese", "in marathi",
    # Emotion detector
    "detect emotion", "analyze tone", "analyse tone",
    "how does this sound", "empathetic response",
    "sentiment analysis", "tone check", "tone of this",
    "emotional analysis", "how will this be received",
    "is this too harsh", "is this too formal", "sounds rude",
    "soften this", "make it kinder", "make it warmer",
    # Contacts
    "add contact", "save contact", "new contact",
    "contact info", "who is", "interaction history",
    "update contact", "edit contact", "my contacts",
    "list contacts", "show contacts", "delete contact",
    "remove contact", "log interaction", "add interaction",
    "search contact", "find contact", "tell me about", "note interaction",
    "call ",
)

_PERSONAL_KEYWORDS = (
    "goal", "target", "milestone", "progress on my goal", "set a goal",
    "track sleep", "logged sleep", "how much did i sleep", "sleep log",
    "track diet", "ate today", "calories", "food log",
    "track exercise", "workout", "ran today", "exercise log",
    "expense", "spent", "budget", "financial log", "money spent",
    "creative idea", "brainstorm", "design suggestion", "creative partner",
    "preferences", "remember this", "forget this", "my habits",
)



class AgentRouter:
    """
    Routes user messages to the appropriate specialised agent,
    handles memory persistence, and collects dashboard metrics.
    """

    MAX_ROUTING_LOG = 50    # retain last N routing decisions
    MAX_LATENCY_LOG = 100   # retain last N latency samples

    def __init__(self):
        self.planner             = PlannerAgent()
        self.coder               = CoderAgent()
        self.reminder_agent      = ReminderAgent()
        self.research_agent      = ResearchAgent()
        self.smarthome_agent     = SmartHomeAgent()
        self.executor_agent      = ExecutorAgent()
        self.tutor_agent         = TutorAgent()
        self.image_agent         = ImageAgent()
        self.productivity_agent  = ProductivityAgent()
        self.communication_agent = CommunicationAgent()
        self.personal_agent      = PersonalAgent()
        self.debugger_agent      = DebuggerAgent()
        self.arvr_agent          = ArVrAgent()
        self.communication_agent.router = self  # Inject router for cross-agent features
        self.llm                 = HybridLLMRouter()
        if settings.supabase_enabled:
            self.memory              = SupabaseChatStore()
            self.vector_store        = SupabaseVectorStore()
        else:
            self.memory              = SQLiteStore()
            self.vector_store        = VectorStore()
        # Expose stores for background checkers
        self.reminder_store = self.reminder_agent.store
        self.contact_store  = self.communication_agent.contact_store
        # Dashboard metrics
        self.routing_log: list[dict] = []
        self.latency_log: list[float] = []
        self.tool_logs: list[dict] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def route(
        self,
        message: str,
        file_context: str = "",
        file_name: str = "",
        voice_mode: str = "calm_male",
        agent_mode: str = "Default Assistant",
    ) -> str:
        """
        Synchronous routing. Returns complete reply string.
        Used for non-streaming clients (tests, simple requests).
        """
        t0 = time.perf_counter()
        self.memory.add_message("user", message)

        augmented = self._augment_message(message, file_context, file_name)
        history   = self._build_history(message)
        semantic  = self._recall(message)

        msg_lower = message.lower()
        agent_name, reply = self._dispatch_sync(msg_lower, message, augmented, history, semantic, voice_mode)

        latency_ms = (time.perf_counter() - t0) * 1000
        self._log(agent_name, message, latency_ms)
        self.memory.add_message("jarvis", reply)
        self.vector_store.add("user", message)
        self.vector_store.add("assistant", reply)
        return reply

    async def route_stream(
        self,
        message: str,
        file_context: str = "",
        file_name: str = "",
        voice_mode: str = "calm_male",
        agent_mode: str = "Default Assistant",
    ) -> AsyncGenerator[str, None]:
        """
        Async streaming routing. Yields string tokens as they arrive.
        Handles memory persistence after the stream is complete.
        """
        t0 = time.perf_counter()
        self.memory.add_message("user", message)

        augmented = self._augment_message(message, file_context, file_name)
        history   = self._build_history(message)
        semantic  = self._recall(message)

        msg_lower = message.lower()

        full_reply = ""
        agent_name = "GeneralLLM"

        # ── Explicit Agent Mode Routing ────────────────────────────────────
        if agent_mode == "Code Debugger":
            agent_name = "DebuggerAgent"
            async for chunk in self.debugger_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk
            self._persist_reply(full_reply, message, agent_name, t0)
            self._log_tool(agent_name, message, full_reply)
            return

        elif agent_mode == "IoT Controller":
            agent_name = "SmartHomeAgent"
            async for chunk in self.smarthome_agent.handle_stream(message, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk
            self._persist_reply(full_reply, message, agent_name, t0)
            self._log_tool(agent_name, message, full_reply)
            return

        elif agent_mode == "Autonomous Agent":
            agent_name = "ExecutorAgent"
            async for chunk in self.executor_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk
            self._persist_reply(full_reply, message, agent_name, t0)
            self._log_tool(agent_name, message, full_reply)
            return

        elif agent_mode == "AR/VR Assistant":
            agent_name = "ArVrAgent"
            async for chunk in self.arvr_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk
            self._persist_reply(full_reply, message, agent_name, t0)
            self._log_tool(agent_name, message, full_reply)
            return

        # ── Agents that don't stream (instant responses) ───────────────────
        if any(k in msg_lower for k in _REMINDER_KEYWORDS):
            reply = self.reminder_agent.handle(message)
            self._persist_reply(reply, message, "ReminderAgent", t0)
            self._log_tool("ReminderAgent", message, reply)
            yield reply
            return

        if any(k in msg_lower for k in _SMARTHOME_KEYWORDS):
            reply = self.smarthome_agent.handle(message)
            self._persist_reply(reply, message, "SmartHomeAgent", t0)
            self._log_tool("SmartHomeAgent", message, reply)
            yield reply
            return

        # ── Streaming agents ───────────────────────────────────────────────
        full_reply = ""

        if any(k in msg_lower for k in _EXECUTOR_KEYWORDS):
            agent_name = "ExecutorAgent"
            async for chunk in self.executor_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _RESEARCH_KEYWORDS):
            agent_name = "ResearchAgent"
            async for chunk in self.research_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _PLANNING_KEYWORDS):
            agent_name = "PlannerAgent"
            async for chunk in self.planner.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _CODING_KEYWORDS):
            agent_name = "CoderAgent"
            async for chunk in self.coder.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _STUDY_KEYWORDS):
            agent_name = "TutorAgent"
            async for chunk in self.tutor_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _IMAGE_KEYWORDS):
            agent_name = "ImageAgent"
            async for chunk in self.image_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _PRODUCTIVITY_KEYWORDS):
            agent_name = "ProductivityAgent"
            async for chunk in self.productivity_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _COMMUNICATION_KEYWORDS):
            agent_name = "CommunicationAgent"
            async for chunk in self.communication_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        elif any(k in msg_lower for k in _PERSONAL_KEYWORDS):
            agent_name = "PersonalAgent"
            async for chunk in self.personal_agent.handle_stream(augmented, self.llm, history, semantic, voice_mode):
                full_reply += chunk
                yield chunk

        else:
            agent_name = "GeneralLLM"
            messages = (
                [{"role": "system", "content": get_jarvis_system_prompt(voice_mode) + self._semantic_block(semantic)}]
                + history
                + [{"role": "user", "content": augmented}]
            )
            async for chunk in self.llm.chat_stream(messages):
                full_reply += chunk
                yield chunk

        self._persist_reply(full_reply, message, agent_name, t0)

        # Log all streaming agents to tool_logs for the dashboard
        if agent_name in ("ExecutorAgent", "ResearchAgent", "PlannerAgent", "CoderAgent", "TutorAgent", "ImageAgent", "ProductivityAgent", "CommunicationAgent", "PersonalAgent"):
            self._log_tool(agent_name, message, full_reply)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _dispatch_sync(
        self,
        msg_lower: str,
        message: str,
        augmented: str,
        history: list,
        semantic: str,
        voice_mode: str = "calm_male",
    ) -> tuple[str, str]:
        """Dispatch to the correct agent synchronously. Returns (agent_name, reply)."""

        if any(k in msg_lower for k in _REMINDER_KEYWORDS):
            logger.info("Router → ReminderAgent")
            return "ReminderAgent", self.reminder_agent.handle(message)

        if any(k in msg_lower for k in _SMARTHOME_KEYWORDS):
            logger.info("Router → SmartHomeAgent")
            return "SmartHomeAgent", self.smarthome_agent.handle(message)

        if any(k in msg_lower for k in _EXECUTOR_KEYWORDS):
            logger.info("Router → ExecutorAgent")
            return "ExecutorAgent", self.executor_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _RESEARCH_KEYWORDS):
            logger.info("Router → ResearchAgent")
            return "ResearchAgent", self.research_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _PLANNING_KEYWORDS):
            logger.info("Router → PlannerAgent")
            return "PlannerAgent", self.planner.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _CODING_KEYWORDS):
            logger.info("Router → CoderAgent")
            return "CoderAgent", self.coder.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _STUDY_KEYWORDS):
            logger.info("Router → TutorAgent")
            return "TutorAgent", self.tutor_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _IMAGE_KEYWORDS):
            logger.info("Router → ImageAgent")
            return "ImageAgent", self.image_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _PRODUCTIVITY_KEYWORDS):
            logger.info("Router → ProductivityAgent")
            return "ProductivityAgent", self.productivity_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _COMMUNICATION_KEYWORDS):
            logger.info("Router → CommunicationAgent")
            return "CommunicationAgent", self.communication_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        if any(k in msg_lower for k in _PERSONAL_KEYWORDS):
            logger.info("Router → PersonalAgent")
            return "PersonalAgent", self.personal_agent.handle(augmented, self.llm, history, semantic, voice_mode)

        logger.info("Router → GeneralLLM")
        messages = (
            [{"role": "system", "content": get_jarvis_system_prompt(voice_mode) + self._semantic_block(semantic)}]
            + history
            + [{"role": "user", "content": augmented}]
        )
        return "GeneralLLM", self.llm.chat(messages)

    # ── Memory helpers ────────────────────────────────────────────────────────

    def _augment_message(self, message: str, file_context: str, file_name: str) -> str:
        if file_context and file_name:
            return (
                f"[Attached file: {file_name}]\n\n"
                f"{file_context}\n\n"
                f"---\n"
                f"User's question about the file: {message}"
            )
        return message

    def _build_history(self, message: str) -> list:
        """Return recent conversation history, de-duplicating the current turn."""
        history = self.memory.get_recent_messages_formatted(limit=20)
        if history and history[-1]["role"] == "user" and history[-1]["content"] == message:
            history = history[:-1]
        return history

    def _recall(self, message: str) -> str:
        """Run semantic search and return formatted context block."""
        results = self.vector_store.search(message, n=5)
        return self.vector_store.format_context(results)

    def _semantic_block(self, semantic_context: str) -> str:
        """Prepend semantic memory context to system prompt if available."""
        if not semantic_context:
            return ""
        return f"\n\n{semantic_context}"

    def _persist_reply(
        self, reply: str, original_message: str, agent_name: str, t0: float
    ) -> None:
        latency_ms = (time.perf_counter() - t0) * 1000
        self._log(agent_name, original_message, latency_ms)
        self.memory.add_message("jarvis", reply)
        self.vector_store.add("user", original_message)
        self.vector_store.add("assistant", reply)

    # ── Metrics ───────────────────────────────────────────────────────────────

    def _log(self, agent: str, message: str, latency_ms: float) -> None:
        entry = {
            "agent":      agent,
            "message":    message[:80],
            "latency_ms": round(latency_ms, 1),
        }
        self.routing_log = (self.routing_log + [entry])[-self.MAX_ROUTING_LOG:]
        self.latency_log = (self.latency_log + [round(latency_ms, 1)])[-self.MAX_LATENCY_LOG:]

    def _log_tool(self, agent: str, message: str, result: str) -> None:
        entry = {
            "agent": agent,
            "message": message[:80],
            "result": result[:150].strip() + ("..." if len(result) > 150 else ""),
            "timestamp": time.time()
        }
        self.tool_logs = (self.tool_logs + [entry])[-20:]

    def clear_logs(self) -> None:
        """Clear the dashboard telemetry logs."""
        self.routing_log.clear()
        self.latency_log.clear()
        self.tool_logs.clear()
        logger.info("Cleared dashboard telemetry logs.")

    def get_stats(self) -> dict:
        """Return serialisable stats for the dashboard /stats endpoint."""
        pending_reminders = self.reminder_store.get_all_upcoming()
        lats = self.latency_log
        return {
            "routing_log":       self.routing_log[-20:],
            "tool_logs":         self.tool_logs,
            "latency_log":       lats[-50:],
            "avg_latency_ms":    round(sum(lats) / len(lats), 1) if lats else 0,
            "pending_reminders": len(pending_reminders),
            "memory_messages":   len(self.memory.get_recent_messages(limit=9999)),
            "vector_enabled":    self.vector_store.enabled,
            "cloud_enabled":     self.llm._cloud.enabled,
            "local_model":       self.llm.model,
        }

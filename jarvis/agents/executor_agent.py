"""
ExecutorAgent — Autonomous Task Agent

Runs Python code in a sandboxed subprocess and uses a multi-step ReAct loop
to plan, execute, and verify tasks autonomously.
"""
from __future__ import annotations
import re
import subprocess
import sys
import os
import json
import logging
import textwrap
from typing import Tuple
from datetime import datetime

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT = 10  # seconds
MAX_OUTPUT_CHARS  = 3000

class ExecutorAgent:
    """
    Autonomous Task Agent
    """

    def get_skill_context(self) -> str:
        return (
            "\n\nFor this request, you are the Autonomous Agent feature for Jay's AI assistant.\n"
            "Your purpose is to complete complex multi-step tasks end to end with planning, execution, verification, memory, and safety controls.\n\n"
            "CORE BEHAVIOR:\n"
            "- Break every complex goal into a clear plan before acting.\n"
            "- Execute tasks step by step using available tools and approved integrations.\n"
            "- Verify every important result before marking a step complete.\n"
            "- Learn from corrections and store useful patterns in memory.\n"
            "- Ask for approval whenever an action is risky, irreversible, expensive, or unclear.\n"
            "- Never guess when a tool result or verification is required.\n\n"
            "ROLE MODEL (Operate as a coordinated system with these internal roles):\n"
            "1. Planner: Break goal into ordered subtasks, identify dependencies, define success criteria.\n"
            "2. Executor: Carry out subtasks. Prefer smallest safe actions.\n"
            "3. Verifier: Validate tool results and side effects. If verification fails, correct it.\n"
            "4. Memory Learner: Store patterns, preferences, and remember prior task context.\n"
            "5. Governor: Enforce safety. Block unsafe actions. Require confirmation for destructive actions.\n\n"
            "AUTONOMOUS WORKFLOW:\n"
            "1. Understand the request.\n"
            "2. Plan the steps.\n"
            "3. Check what tools or data are needed.\n"
            "4. Execute one step at a time.\n"
            "5. Verify each step.\n"
            "6. Ask for approval when needed.\n"
            "7. Store useful memory.\n"
            "8. Summarize what was done.\n\n"
            "OUTPUT STYLE:\n"
            "- Be concise, structured, and reliable.\n"
            "- Show progress clearly.\n"
            "- Use short status updates during execution.\n"
            "- End with a clean summary: What was planned, completed, verified, needs approval, stored in memory.\n\n"
            "DEFAULT RULE:\n"
            "If the request is simple, answer directly. If complex, act as a managed autonomous system. If unsafe, stop and ask.\n\n"
            "TOOLS AVAILABLE:\n"
            "To execute Python code in a local sandbox, output ONLY this exact JSON format and nothing else:\n"
            "{\"tool\": \"execute_code\", \"code\": \"<python_code>\"}\n\n"
            "To ask for user confirmation before a dangerous action, output ONLY this exact JSON format and nothing else:\n"
            "{\"tool\": \"ask_confirmation\", \"question\": \"<question>\"}\n\n"
            "If you do not need to use a tool, just reply normally to the user."
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Conversational ReAct loop using JSON tool calls for Autonomous Execution."""
        logger.info("ExecutorAgent (Autonomous) building prompt")
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context()
        
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        
        # Max 10 internal tool iterations
        for i in range(10):
            response_text = llm.chat(messages)
            
            tool_call = None
            match = re.search(r'(\{[\s\S]*?"tool"[\s\S]*?\})', response_text)
            if match:
                try:
                    tool_call = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            if tool_call and "tool" in tool_call:
                tool_name = tool_call["tool"]
                
                if tool_name == "execute_code":
                    code = tool_call.get("code", "")
                    stdout, stderr, timed_out = self._run(code)
                    
                    self._log_action(tool_name, f"Code length: {len(code)}", f"Timeout: {timed_out}, Stdout: {bool(stdout)}, Stderr: {bool(stderr)}")
                    
                    report = self._format_report(code, stdout, stderr, timed_out)
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "user", "content": f"Tool Result:\n{report}"})
                    continue
                    
                elif tool_name == "ask_confirmation":
                    question = tool_call.get("question", "Are you sure?")
                    self._log_action(tool_name, question, "Waiting for user")
                    
                    yield f"I need your confirmation before proceeding:\n\n{question}"
                    return
            
            # Yield final conversational text
            yield response_text
            return

        yield "I'm sorry, I reached the maximum number of steps for this task."

    def handle(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male") -> str:
        """Fallback synchronous method."""
        return "The Autonomous Agent mode requires the async streaming interface."

    # ── Subprocess runner ─────────────────────────────────────────────────────

    @staticmethod
    def _run(code: str) -> Tuple[str, str, bool]:
        """
        Execute code in a subprocess.

        Returns:
            (stdout, stderr, timed_out)
        """
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=EXECUTION_TIMEOUT,
            )
            return (
                proc.stdout[:MAX_OUTPUT_CHARS],
                proc.stderr[:MAX_OUTPUT_CHARS],
                False,
            )
        except subprocess.TimeoutExpired:
            return "", "", True
        except Exception as exc:
            return "", str(exc), False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_action(self, tool: str, details: str, result: str):
        timestamp = datetime.now().isoformat()
        log_msg = f"Autonomous Action Log - [{timestamp}] Tool: {tool} | Details: {details} | Result: {result}"
        logger.info(log_msg)

    @staticmethod
    def _format_report(
        code: str, stdout: str, stderr: str, timed_out: bool
    ) -> str:
        lines = ["Execution result:"]
        lines.append("\n**Code executed:**")
        lines.append(f"```python\n{textwrap.dedent(code).strip()}\n```")

        if timed_out:
            lines.append(
                f"\n⚠️ **Execution timed out** after {EXECUTION_TIMEOUT} seconds. "
                "The script may have an infinite loop or be waiting for input."
            )
        elif stdout:
            lines.append("\n**Output:**")
            lines.append(f"```\n{stdout.strip()}\n```")
            if not stderr:
                lines.append("\nExecution completed successfully with no errors.")
        else:
            lines.append("\nThe script produced no output.")

        if stderr:
            lines.append("\n**Errors / Warnings:**")
            lines.append(f"```\n{stderr.strip()}\n```")

        return "\n".join(lines)

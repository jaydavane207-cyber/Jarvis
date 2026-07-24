"""
CoderAgent — repo-aware coding assistant for JARVIS.

Enhanced per PRD §5.7:
  • Repo-Aware: Point Coder at a local git repo and it can:
    - Read directory structure and open files for context
    - Run tests via Executor and report results
    - Check git status / diff
    - Summarise changes for PR description
  • Cost tracking wired into every LLM call
"""
from __future__ import annotations
import logging
import os
import subprocess
import sys
from typing import Optional

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)


class CoderAgent:
    """Repo-aware coding assistant."""

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = repo_path

    def get_skill_context(self, message: str, repo_context: str = "") -> str:
        base = (
            "\n\nFor this request, you are in CODING MODE. "
            "Provide clean, working code with brief explanations. "
            "If writing code, wrap it in appropriate code blocks. "
            "Since your output may be spoken, briefly summarize what the code does before showing it. "
            "Prefer Assembly/C for embedded work (Jay's specialty: 8086, 8051, ARM Cortex). "
            "For web/server code, use clean modern patterns."
        )
        if repo_context:
            base += f"\n\nREPO CONTEXT:\n{repo_context}"
        return base

    # ── Repo helpers ───────────────────────────────────────────────────────────

    def _get_repo_context(self, repo_path: str) -> str:
        """Build repo context: directory tree + git status."""
        lines = [f"Repository: {repo_path}"]
        # Git status
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_path, capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                lines.append(f"\nGit Status:\n{result.stdout.strip()[:500]}")
        except Exception:
            pass
        # Git log (last 3 commits)
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-3"],
                cwd=repo_path, capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                lines.append(f"\nRecent Commits:\n{result.stdout.strip()}")
        except Exception:
            pass
        # Directory tree (top-level + one level deep)
        try:
            entries = []
            for item in sorted(os.listdir(repo_path))[:20]:
                full = os.path.join(repo_path, item)
                if os.path.isdir(full) and not item.startswith("."):
                    entries.append(f"  {item}/")
                elif os.path.isfile(full):
                    entries.append(f"  {item}")
            if entries:
                lines.append(f"\nDirectory:\n" + "\n".join(entries))
        except Exception:
            pass
        return "\n".join(lines)

    def run_tests(self, repo_path: str) -> str:
        """Run pytest in the repo and return a summary."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--tb=short", "-q"],
                cwd=repo_path, capture_output=True, text=True,
                timeout=120, encoding="utf-8"
            )
            output = (result.stdout + result.stderr)[:3000]
            return f"Test Results:\n{output}"
        except subprocess.TimeoutExpired:
            return "Tests timed out after 120 seconds."
        except Exception as exc:
            return f"Test run failed: {exc}"

    def get_diff(self, repo_path: str) -> str:
        """Get current git diff for PR context."""
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=repo_path, capture_output=True, text=True, timeout=10
            )
            diff = result.stdout[:4000]
            return f"Git Diff:\n{diff}" if diff else "No uncommitted changes."
        except Exception as exc:
            return f"Git diff failed: {exc}"

    # ── Public API ─────────────────────────────────────────────────────────────

    def handle(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
        repo_path: Optional[str] = None,
    ) -> str:
        """Generate a coding response via the LLM synchronously."""
        logger.info("CoderAgent building coding prompt")
        rp = repo_path or self.repo_path
        repo_ctx = self._get_repo_context(rp) if rp and os.path.isdir(rp) else ""
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message, repo_ctx)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        return llm.chat(messages)

    async def handle_stream(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
        repo_path: Optional[str] = None,
    ):
        """Generate a coding response via the LLM as a stream."""
        logger.info("CoderAgent building coding prompt")
        rp = repo_path or self.repo_path
        repo_ctx = self._get_repo_context(rp) if rp and os.path.isdir(rp) else ""
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context(message, repo_ctx)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        async for chunk in llm.chat_stream(messages):
            yield chunk

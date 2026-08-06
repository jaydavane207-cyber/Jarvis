"""
async_writer.py — Safe, race-free async persistence for JARVIS memory.

Design decisions
────────────────
• SQLite and vector-store writes run *concurrently* via asyncio.gather so
  neither write blocks streaming tokens from reaching the client.

• Each write runs in a background thread (asyncio.to_thread) to avoid
  blocking the event loop; sqlite3 is synchronous/thread-safe by default
  when WAL mode + busy_timeout is enabled.

• The stores are treated as INDEPENDENT: a failure in one does NOT roll
  back the other, and does NOT raise to the caller.  Rationale:
    - SQLite is the primary source of truth for the active session.
      The vector store is a secondary semantic index.
    - ChromaDB has no transactional rollback, so a compensating delete
      after a partial write is itself failure-prone.
    - Conversation continuity is more important than vector consistency.
    - Vector store already has graceful-degradation fallback everywhere.

• CONSECUTIVE FAILURE TRACKING: if the vector store fails 3+ times in a
  row a WARNING-level log is emitted (once per threshold crossing), making
  silent semantic-memory degradation visible in logs / monitoring.

Multi-worker (uvicorn --workers N) note
────────────────────────────────────────
WAL + busy_timeout is sufficient for *read-heavy* workloads or when writes
are rare.  Once you add ≥2 uvicorn workers (fix #9):

  • WAL allows ONE concurrent writer + many concurrent readers.
  • If two workers race to commit simultaneously, the loser gets
    SQLITE_BUSY and will retry until busy_timeout expires (5 s here).
  • For JARVIS's workload (one user, sequential conversation turns) this
    is almost always fine — throughput is low, writes are short.

  When it's NO LONGER sufficient:
    - High-concurrency deployments (multiple simultaneous users / workers
      writing every second).
    - In that case, replace SQLiteStore with a PostgreSQL store (pgvector
      already handles multi-process locking natively via Supabase) OR
      route all SQLite writes through a single asyncio.Queue consumed by
      a dedicated writer task (see `_SqliteWriteQueue` stub at bottom).

  For Jay's current single-user setup: WAL + busy_timeout = fine.
  Add the queue only if you observe repeated "database is locked" warnings.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Consecutive-failure threshold for vector store warning ───────────────────
_VECTOR_FAIL_WARN_THRESHOLD = 3


class AsyncMemoryWriter:
    """
    Provides safe, concurrent async writes to SQLite (chat store) and the
    vector store (semantic index).

    Instantiate once per AgentRouter and reuse across every conversation turn.
    """

    def __init__(self, sql_store, vector_store):
        self._sql = sql_store
        self._vec = vector_store
        # Track consecutive vector-store failures for degradation warning
        self._vec_consecutive_failures: int = 0

    # ── Primary API ───────────────────────────────────────────────────────────

    async def persist_user_message(self, message: str) -> None:
        """Persist the user's raw turn to SQLite.  Called before the LLM reply."""
        await self._safe_sql_write("user", message)

    async def persist_reply(
        self,
        reply: str,
        original_message: str,
    ) -> None:
        """
        Persist the assistant reply AND index both turns in the vector store.
        Runs SQL and vector writes concurrently; failures in either are isolated.
        """
        sql_coro   = self._safe_sql_write("jarvis", reply)
        vec_u_coro = self._safe_vec_write("user",      original_message)
        vec_a_coro = self._safe_vec_write("assistant", reply)

        # All three run concurrently; return_exceptions ensures one failure
        # doesn't abort the others.
        await asyncio.gather(sql_coro, vec_u_coro, vec_a_coro,
                             return_exceptions=False)

    # ── Internal write helpers ────────────────────────────────────────────────

    async def _safe_sql_write(self, role: str, content: str) -> None:
        """Offload synchronous SQLite write to a background thread."""
        try:
            await asyncio.to_thread(self._sql.add_message, role, content)
        except Exception as exc:
            # SQLite failure is notable — log at ERROR level.
            logger.error(
                "AsyncMemoryWriter: SQLite write failed (role=%s): %s",
                role, exc, exc_info=True
            )

    async def _safe_vec_write(self, role: str, content: str) -> None:
        """
        Offload synchronous vector-store write to a background thread.
        Tracks consecutive failures and warns if semantic memory degrades.
        """
        if not getattr(self._vec, "enabled", False):
            return
        if not content or not content.strip():
            return
        try:
            await asyncio.to_thread(self._vec.add, role, content)
            # Reset failure counter on success
            if self._vec_consecutive_failures > 0:
                logger.info(
                    "AsyncMemoryWriter: vector store recovered after %d failure(s).",
                    self._vec_consecutive_failures
                )
            self._vec_consecutive_failures = 0
        except Exception as exc:
            self._vec_consecutive_failures += 1
            if self._vec_consecutive_failures >= _VECTOR_FAIL_WARN_THRESHOLD:
                logger.warning(
                    "AsyncMemoryWriter: vector store has failed %d consecutive "
                    "time(s) — semantic memory may be degraded. "
                    "Last error (role=%s): %s",
                    self._vec_consecutive_failures, role, exc,
                    exc_info=True
                )
            else:
                logger.error(
                    "AsyncMemoryWriter: vector store write failed (role=%s, "
                    "consecutive=%d): %s",
                    role, self._vec_consecutive_failures, exc
                )

    # ── Optional: expose current health state ─────────────────────────────────

    @property
    def vector_healthy(self) -> bool:
        """True if the vector store has not failed consecutively."""
        return self._vec_consecutive_failures < _VECTOR_FAIL_WARN_THRESHOLD

    @property
    def vector_consecutive_failures(self) -> int:
        return self._vec_consecutive_failures


# ── Multi-worker SQLite write queue (stub for future use) ─────────────────────
#
# Activate this if you observe "database is locked" under ≥2 uvicorn workers
# and WAL+busy_timeout is insufficient.
#
# Usage:
#   queue = SqliteWriteQueue(sql_store)
#   await queue.start()                       # call once at app startup
#   await queue.enqueue("user", message)      # instead of direct write
#   await queue.stop()                        # call at app shutdown
#
class SqliteWriteQueue:
    """
    STUB — Single-consumer asyncio queue that serialises all SQLite writes
    through one coroutine, eliminating multi-process write races entirely.
    Enable when WAL+busy_timeout proves insufficient under multiple workers.
    """

    def __init__(self, sql_store):
        self._sql = sql_store
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._consumer(), name="sqlite_writer")
        logger.info("SqliteWriteQueue: single-writer consumer started.")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SqliteWriteQueue: consumer stopped.")

    async def enqueue(self, role: str, content: str) -> None:
        await self._queue.put((role, content))

    async def _consumer(self) -> None:
        while True:
            role, content = await self._queue.get()
            try:
                await asyncio.to_thread(self._sql.add_message, role, content)
            except Exception as exc:
                logger.error(
                    "SqliteWriteQueue: write failed (role=%s): %s", role, exc,
                    exc_info=True
                )
            finally:
                self._queue.task_done()

"""
simulate_stream_disconnect.py
------------------------------
Live integration test for JARVIS mid-stream TCP disconnect handling.

Tests
-----
TEST 1 : AnthropicClient mid-stream TCP reset  -> hybrid_router WARNING + Ollama fallback
TEST 2 : 3+ consecutive VectorStore failures   -> async_writer WARNING log fires
TEST 3 : VectorStore recovery after failures   -> vector_healthy flips back True

Usage
-----
    python simulate_stream_disconnect.py

Requirements
------------
- Ollama running at http://localhost:11434
- JARVIS venv active
- Backend server does NOT need to be running
"""
from __future__ import annotations
import asyncio
import logging
import sys
import os

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

# ── Override settings BEFORE any jarvis import ────────────────────────────────
# Force local SQLite+ChromaDB stores so our patches land on the right classes.
os.environ["SUPABASE_ENABLED"] = "false"
# Lower cloud threshold to 0 so every message tries cloud first.
os.environ["CLOUD_THRESHOLD"]  = "0.0"

# ── In-process log capture (used to assert WARNING lines appeared) ─────────────
class _LogCapture(logging.Handler):
    """Collects log records into a list for assertion checks."""
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []
    def emit(self, record: logging.LogRecord):
        self.records.append(record)
    def has(self, level: int, fragment: str) -> bool:
        return any(
            r.levelno >= level and fragment.lower() in r.getMessage().lower()
            for r in self.records
        )

_capture = _LogCapture()
_capture.setLevel(logging.DEBUG)
logging.getLogger("jarvis").addHandler(_capture)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulate")

GREEN = "\033[92m"
AMBER = "\033[93m"
RED   = "\033[91m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"
DIV   = "=" * 65
DIV2  = "-" * 65


# ── Patch 1 : AnthropicClient.chat_stream -> mid-stream TCP reset ─────────────

async def _fake_cloud_stream(self, messages):
    """Yield 3 tokens, then raise a wsarecv connection-reset error."""
    tokens = ["Let me ", "think about ", "that... "]
    for t in tokens:
        yield t
        await asyncio.sleep(0.04)
    raise OSError(
        "stream reading error: read tcp 192.168.0.100:51504->172.217.116.4:443: "
        "wsarecv: An existing connection was forcibly closed by the remote host."
    )


# ── Patch 2 : VectorStore.add -> fail first 3 calls then recover ──────────────

_vec_call_count = 0
# 4 calls fail (2 per turn × 2 turns) so consecutive_failures hits 3
# before any success can reset it. Turn 3 then succeeds → recovery.
_FAIL_UNTIL     = 4


def _fake_vec_add(self, role: str, content: str, doc_id=None):
    global _vec_call_count
    _vec_call_count += 1
    if _vec_call_count <= _FAIL_UNTIL:
        raise RuntimeError(f"[SIMULATED] ChromaDB write failure #{_vec_call_count}")
    # success — no-op (write is swallowed, which is fine for the test)


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{BOLD}{DIV}{RESET}")
    print(f"{BOLD}  JARVIS MID-STREAM DISCONNECT SIMULATION{RESET}")
    print(f"{BOLD}{DIV}{RESET}\n")

    # Apply patches BEFORE importing AgentRouter
    from jarvis.models.cloud_client import AnthropicClient
    from jarvis.memory.vector_store import VectorStore

    AnthropicClient.chat_stream = _fake_cloud_stream   # type: ignore[method-assign]
    VectorStore.add             = _fake_vec_add         # type: ignore[method-assign]

    # Verify settings were overridden
    from jarvis.config import settings
    assert not settings.supabase_enabled, "supabase_enabled should be False"
    assert settings.cloud_threshold == 0.0, f"cloud_threshold={settings.cloud_threshold}, expected 0.0"
    print(f"{DIM}supabase_enabled : {settings.supabase_enabled}  (False -> uses SQLite + ChromaDB){RESET}")
    print(f"{DIM}cloud_threshold  : {settings.cloud_threshold}    (0.0 -> always tries cloud first){RESET}\n")

    print(f"{DIM}Loading AgentRouter...{RESET}\n")
    from jarvis.agents.router import AgentRouter
    router = AgentRouter()

    # Confirm we are using local stores, not Supabase
    from jarvis.memory.sqlite_store import SQLiteStore
    from jarvis.memory.vector_store  import VectorStore as VS
    assert isinstance(router.memory,       SQLiteStore), f"Expected SQLiteStore, got {type(router.memory)}"
    assert isinstance(router.vector_store, VS),          f"Expected VectorStore, got {type(router.vector_store)}"
    print(f"{DIM}Store types confirmed: {type(router.memory).__name__} + {type(router.vector_store).__name__}{RESET}\n")

    # Enable the fake cloud client
    router.llm._cloud._enabled = True   # type: ignore[attr-defined]

    # ── TEST 1: cloud stream disconnect + Ollama fallback ─────────────────────
    print(f"{CYAN}=== TEST 1: MID-STREAM TCP RESET -> OLLAMA FALLBACK ==={RESET}\n")
    message = "Explain step by step how the 8086 stack pointer works in assembly."
    print(f"{BOLD}Jay  :{RESET} {message}\n")
    print(f"{BOLD}JARVIS:{RESET} ", end="", flush=True)

    full_reply_1 = ""
    tok1 = 0
    try:
        async for token in router.route_stream(message, voice_mode="calm_male"):
            full_reply_1 += token
            tok1 += 1
            print(token, end="", flush=True)
    except Exception as exc:
        print(f"\n{RED}[UNHANDLED EXCEPTION - FAIL]{RESET}: {exc}")
        return

    print(f"\n{DIM}{DIV2}{RESET}\n")

    # Brief pause to let async persist_reply tasks finish before checking state
    await asyncio.sleep(1.5)
    vec_count_after_t1 = _vec_call_count

    # ── TEST 3: second failing turn — all 4 calls fail, WARNING must fire ─────
    # With _FAIL_UNTIL=4, calls 3+4 here both fail -> consecutive reaches 3.
    print(f"{CYAN}=== TEST 3: SECOND FAILING TURN (forces WARNING log) ==={RESET}\n")
    message2 = "What are the 8086 segment registers?"
    print(f"{BOLD}Jay  :{RESET} {message2}\n")
    print(f"{BOLD}JARVIS:{RESET} ", end="", flush=True)

    full_reply_2 = ""
    try:
        async for token in router.route_stream(message2, voice_mode="calm_male"):
            full_reply_2 += token
            print(token, end="", flush=True)
    except Exception as exc:
        print(f"\n{RED}[UNHANDLED EXCEPTION - FAIL]{RESET}: {exc}")
        return

    print(f"\n")

    # Wait for async writes (calls 3+4) to settle
    await asyncio.sleep(1.5)
    vec_count_after_t3 = _vec_call_count

    # ── TEST 4: recovery turn — call 5+ succeed, vector_healthy flips True ────
    print(f"{CYAN}=== TEST 4: VECTOR STORE RECOVERY ==={RESET}\n")
    message3 = "What is the 8086 BIU?"
    print(f"{BOLD}Jay  :{RESET} {message3}\n")
    print(f"{BOLD}JARVIS:{RESET} ", end="", flush=True)

    full_reply_3 = ""
    try:
        async for token in router.route_stream(message3, voice_mode="calm_male"):
            full_reply_3 += token
            print(token, end="", flush=True)
    except Exception as exc:
        print(f"\n{RED}[UNHANDLED EXCEPTION - FAIL]{RESET}: {exc}")
        return

    print(f"\n")

    # Pause to let the second turn's async writes finish
    await asyncio.sleep(1.5)

    # ── ALL CHECKS (after both tests have run and writes have settled) ─────────
    healthy = router._writer.vector_healthy
    consec  = router._writer.vector_consecutive_failures

    print(f"{DIM}{DIV2}{RESET}")
    print(f"\n{BOLD}=== SIMULATION RESULTS ==={RESET}\n")

    checks = [
        (
            "Cloud stream WARNING fired (hybrid_router detected mid-stream reset)",
            _capture.has(logging.WARNING, "cloud stream interrupted after"),
        ),
        (
            "Ollama fallback log appeared after cloud failure",
            _capture.has(logging.INFO, "local stream (fallback after cloud failure)"),
        ),
        (
            "No unhandled exception escaped route_stream()",
            True,
        ),
        (
            "Async-writer ERROR logged on vector failure",
            _capture.has(logging.ERROR, "vector store write failed"),
        ),
        (
            "Async-writer WARNING logged after 3 consecutive failures",
            _capture.has(logging.WARNING, "vector store has failed"),
        ),
        (
            "Vector write patches triggered >=3 times total",
            _vec_call_count >= 3,
        ),
        (
            "Vector store recovered (vector_healthy=True after recovery)",
            healthy,
        ),
        (
            "Reply from TEST 1 is non-empty",
            len(full_reply_1) > 20,
        ),
    ]

    all_pass = True
    for label, ok in checks:
        icon  = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  [{icon}] {label}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print(f"{GREEN}{BOLD}  ALL CHECKS PASSED.{RESET}\n")
    else:
        print(f"{RED}{BOLD}  SOME CHECKS FAILED — see output above.{RESET}\n")

    print(f"{DIM}Tokens in reply 1         : {tok1} ({len(full_reply_1)} chars){RESET}")
    print(f"{DIM}Total vector call count   : {_vec_call_count}{RESET}")
    print(f"{DIM}  after T1: {vec_count_after_t1}  after T3: {vec_count_after_t3}  final: {_vec_call_count}{RESET}")
    print(f"{DIM}vector_healthy            : {healthy}{RESET}")
    print(f"{DIM}consecutive_failures      : {consec}{RESET}")

    print(f"\n{BOLD}Log lines captured (WARNING+):{RESET}")
    for r in _capture.records:
        if r.levelno >= logging.WARNING:
            color = AMBER if r.levelno == logging.WARNING else RED
            print(f"  {color}[{r.levelname}]{RESET} {r.name}: {r.getMessage()[:120]}")

    print(f"\n{BOLD}{DIV}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())

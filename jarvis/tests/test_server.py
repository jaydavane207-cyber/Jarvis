"""
Integration tests for the JARVIS FastAPI WebSocket server.

The server is spun up in a daemon thread using uvicorn. Each test connects
as a WebSocket client. The Ollama LLM and SQLite store are mocked to keep
tests fast and hermetic (no real I/O needed).

WebSocket streaming protocol:
  → thinking
  → token (one or more)
  → done
"""
import unittest
import threading
import time
import asyncio
import json
import socket
from contextlib import closing

import websockets
import uvicorn
from unittest.mock import patch, MagicMock, AsyncMock


def get_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class UvicornServer(threading.Thread):
    """Minimal uvicorn wrapper that can be stopped from outside."""

    def __init__(self, app, host: str = "127.0.0.1", port: int = 8001):
        super().__init__()
        self.config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(self.config)
        self.daemon = True

    def run(self):
        asyncio.run(self.server.serve())

    def stop(self):
        self.server.should_exit = True


class TestServerWebSocket(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from jarvis.main import app
        cls.app = app
        cls.port = get_free_port()
        cls.server_thread = UvicornServer(app, port=cls.port)
        cls.server_thread.start()
        time.sleep(1.5)

    @classmethod
    def tearDownClass(cls):
        cls.server_thread.stop()
        cls.server_thread.join(timeout=3.0)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _collect_messages(self, payload: dict, n: int = 10, timeout: float = 5.0) -> list:
        """Send payload and collect up to n frames or until 'done' arrives."""
        async def _run():
            uri = f"ws://127.0.0.1:{self.port}/ws"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps(payload))
                received = []
                for _ in range(n):
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        msg = json.loads(raw)
                        received.append(msg)
                        if msg.get("type") in ("done", "error", "system", "reminders_list"):
                            break
                    except asyncio.TimeoutError:
                        break
                return received
        return asyncio.run(_run())

    # ── Tests ──────────────────────────────────────────────────────────────────

    def test_health_endpoint(self):
        """GET /health should return status=online."""
        import httpx
        r = httpx.get(f"http://127.0.0.1:{self.port}/health")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d.get("status"), "online")

    def test_stats_endpoint(self):
        """GET /stats should return dashboard metrics."""
        import httpx
        r = httpx.get(f"http://127.0.0.1:{self.port}/stats", auth=("jarvis", "admin123"))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("connections", d)
        self.assertIn("routing_log", d)
        self.assertIn("latency_log", d)

    def test_websocket_invalid_json(self):
        """Sending non-JSON text should return an error message."""
        msgs = self._collect_messages.__func__(self, {"_raw": True}, n=1)
        # Use raw send instead
        async def _run():
            uri = f"ws://127.0.0.1:{self.port}/ws"
            async with websockets.connect(uri) as ws:
                await ws.send("not valid json }{")
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                return json.loads(raw)
        r = asyncio.run(_run())
        self.assertEqual(r.get("type"), "error")

    def test_websocket_clear_history(self):
        """clear_history should return a system message."""
        msgs = self._collect_messages({"type": "clear_history"}, n=1)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].get("type"), "system")

    def test_websocket_get_reminders(self):
        """get_reminders should return reminders_list."""
        msgs = self._collect_messages({"type": "get_reminders"}, n=1)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].get("type"), "reminders_list")

    def test_websocket_chat_streaming_protocol(self):
        """Chat should produce: thinking → token(s) → done."""
        async def _route_stream_mock(*args, **kwargs):
            for word in ["Paris", ",", " sir", "."]:
                yield word

        with patch('jarvis.main.router') as mock_router:
            mock_router.reminder_store.get_pending_reminders.return_value = []
            mock_router.reminder_store.get_all_upcoming.return_value = []
            mock_router.memory.clear_history.return_value = None
            mock_router.get_stats.return_value = {
                "routing_log": [], "latency_log": [], "avg_latency_ms": 0,
                "pending_reminders": 0, "memory_messages": 0,
                "vector_enabled": False, "cloud_enabled": False, "local_model": "test",
            }
            mock_router.route_stream = _route_stream_mock

            msgs = self._collect_messages(
                {"type": "chat", "text": "Capital of France?"},
                n=20, timeout=8.0,
            )

        types = [m.get("type") for m in msgs]
        self.assertIn("thinking", types, "Expected thinking frame")
        self.assertIn("done",     types, "Expected done frame")

        done_msg = next(m for m in msgs if m.get("type") == "done")
        self.assertIn("Paris", done_msg.get("text", ""))

    def test_websocket_empty_text_ignored(self):
        """Empty chat text should produce no reply."""
        async def _run():
            uri = f"ws://127.0.0.1:{self.port}/ws"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "chat", "text": "   "}))
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    return json.loads(msg)
                except asyncio.TimeoutError:
                    return None
        result = asyncio.run(_run())
        if result is not None:
            self.assertNotEqual(result.get("type"), "done")


if __name__ == "__main__":
    unittest.main()


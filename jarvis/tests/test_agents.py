"""
Tests for AgentRouter routing logic.

The router now uses:
  - HybridLLMRouter (wraps OllamaClient + AnthropicClient)
  - SQLiteStore (conversation memory)
  - VectorStore (semantic memory — ChromaDB + sentence-transformers)
  - 6 specialised agents

Tests mock HybridLLMRouter, SQLiteStore and VectorStore to avoid real I/O.
"""
import unittest
from unittest.mock import patch, MagicMock, AsyncMock


def _make_router():
    """
    Build an AgentRouter with all external I/O mocked.

    Returns (router, mock_llm, mock_memory).
    """
    with patch('jarvis.agents.router.HybridLLMRouter') as MockLLM, \
         patch('jarvis.agents.router.SQLiteStore')     as MockStore, \
         patch('jarvis.agents.router.VectorStore')     as MockVec, \
         patch('jarvis.agents.reminder_agent.ReminderStore') as MockRemStore:

        mock_llm    = MockLLM.return_value
        mock_llm.chat.return_value = "Mock LLM reply"

        mock_memory = MockStore.return_value
        mock_memory.get_recent_messages_formatted.return_value = []
        mock_memory.get_recent_messages.return_value = []

        mock_vec = MockVec.return_value
        mock_vec.search.return_value = []
        mock_vec.format_context.return_value = ""
        mock_vec.add.return_value = None
        mock_vec.enabled = False

        from jarvis.agents.router import AgentRouter
        router = AgentRouter()
        router.llm    = mock_llm
        router.memory = mock_memory
        router.vector_store = mock_vec

    return router, mock_llm, mock_memory


class TestAgentRouter(unittest.TestCase):

    # ── Planner routing ────────────────────────────────────────────────────────

    def test_routing_to_planner(self):
        """Keywords like 'plan', 'schedule', 'roadmap' should route to PlannerAgent."""
        planning_queries = [
            "make a plan for today",
            "schedule a meeting with the team",
            "create a roadmap for the project",
            "set a goal for next month",
        ]
        for query in planning_queries:
            with self.subTest(query=query):
                router, mock_llm, mock_memory = _make_router()
                reply = router.route(query)

                # LLM should have been called (PlannerAgent uses llm.chat)
                mock_llm.chat.assert_called_once()
                # Memory should be written twice: user turn + JARVIS reply
                mock_memory.add_message.assert_any_call("user", query)
                mock_memory.add_message.assert_any_call("jarvis", reply)

    # ── Coder routing ──────────────────────────────────────────────────────────

    def test_routing_to_coder(self):
        """Keywords like 'write code', 'debug', 'algorithm' should route to CoderAgent."""
        coding_queries = [
            "write code for a binary search",
            "debug this python function",
            "implement a sorting algorithm",
        ]
        for query in coding_queries:
            with self.subTest(query=query):
                router, mock_llm, mock_memory = _make_router()
                reply = router.route(query)

                mock_llm.chat.assert_called_once()
                mock_memory.add_message.assert_any_call("user", query)
                mock_memory.add_message.assert_any_call("jarvis", reply)

    # ── General LLM fallback ───────────────────────────────────────────────────

    def test_routing_fallback_to_llm(self):
        """Unrecognised queries should fall through to the general JARVIS LLM."""
        router, mock_llm, mock_memory = _make_router()
        query = "What is the capital of France?"
        reply = router.route(query)

        self.assertEqual(reply, "Mock LLM reply")
        mock_llm.chat.assert_called_once()
        mock_memory.add_message.assert_any_call("user", query)
        mock_memory.add_message.assert_any_call("jarvis", reply)

    # ── Reminder routing ───────────────────────────────────────────────────────

    def test_routing_to_reminder_agent(self):
        """Reminder keywords should bypass the LLM entirely."""
        router, mock_llm, mock_memory = _make_router()
        query = "remind me in 5 minutes to drink water"
        reply = router.route(query)

        # LLM must NOT be called for reminders
        mock_llm.chat.assert_not_called()
        self.assertIsInstance(reply, str)
        self.assertGreater(len(reply), 0)

    def test_routing_show_reminders(self):
        """'my reminders' should list reminders without calling the LLM."""
        router, mock_llm, mock_memory = _make_router()
        reply = router.route("my reminders")
        mock_llm.chat.assert_not_called()
        self.assertIsInstance(reply, str)

    # ── Smart home routing ─────────────────────────────────────────────────────

    def test_routing_to_smarthome_agent(self):
        """Smart home keywords should route to SmartHomeAgent without LLM."""
        router, mock_llm, mock_memory = _make_router()
        reply = router.route("turn on the living room lights")
        # SmartHomeAgent handles it — LLM not needed
        mock_llm.chat.assert_not_called()
        self.assertIsInstance(reply, str)
        self.assertGreater(len(reply), 0)

    # ── File context augmentation ──────────────────────────────────────────────

    def test_file_context_augments_message(self):
        """Passing file_content + file_name should include them in the LLM prompt."""
        router, mock_llm, mock_memory = _make_router()
        router.route(
            "explain this code",
            file_context="def foo(): pass",
            file_name="example.py",
        )
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        user_msgs = [m for m in messages if m["role"] == "user"]
        self.assertTrue(
            any("example.py" in m["content"] for m in user_msgs),
            "File name should appear in the LLM prompt",
        )

    # ── Memory persistence ─────────────────────────────────────────────────────

    def test_memory_always_stores_both_turns(self):
        """Every route() call must persist both the user turn and JARVIS reply."""
        router, mock_llm, mock_memory = _make_router()
        reply = router.route("Hello JARVIS")
        self.assertEqual(mock_memory.add_message.call_count, 2)
        mock_memory.add_message.assert_any_call("user", "Hello JARVIS")
        mock_memory.add_message.assert_any_call("jarvis", reply)

    # ── Dashboard stats ────────────────────────────────────────────────────────

    def test_routing_populates_stats(self):
        """route() should log routing decisions visible in get_stats()."""
        router, mock_llm, mock_memory = _make_router()
        # Mock the reminder_store used by get_stats
        router.reminder_store = MagicMock()
        router.reminder_store.get_all_upcoming.return_value = []

        router.route("What is the capital of France?")
        stats = router.get_stats()

        self.assertGreater(len(stats["routing_log"]), 0)
        self.assertGreater(len(stats["latency_log"]), 0)
        last_entry = stats["routing_log"][-1]
        self.assertEqual(last_entry["agent"], "GeneralLLM")


if __name__ == "__main__":
    unittest.main()

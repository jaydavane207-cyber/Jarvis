"""
Tests for ReminderAgent: time parsing, text extraction, and handle() routing.
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from jarvis.agents.reminder_agent import ReminderAgent


class TestReminderAgentTimeParsing(unittest.TestCase):

    def setUp(self):
        with patch('jarvis.agents.reminder_agent.ReminderStore'):
            self.agent = ReminderAgent()

    # ── Relative time patterns ─────────────────────────────────────────────────

    def test_parse_in_minutes(self):
        result = self.agent._parse_time("remind me in 10 minutes to take a break")
        self.assertIsNotNone(result)
        delta = result - datetime.now()
        # Should be ~10 minutes (allow ±5 seconds tolerance)
        self.assertAlmostEqual(delta.total_seconds(), 600, delta=5)

    def test_parse_in_seconds(self):
        result = self.agent._parse_time("set a timer for 30 seconds")
        self.assertIsNotNone(result)
        delta = result - datetime.now()
        self.assertAlmostEqual(delta.total_seconds(), 30, delta=5)

    def test_parse_in_hours(self):
        result = self.agent._parse_time("remind me in 2 hours to check the oven")
        self.assertIsNotNone(result)
        delta = result - datetime.now()
        self.assertAlmostEqual(delta.total_seconds(), 7200, delta=5)

    # ── Absolute time patterns ─────────────────────────────────────────────────

    def test_parse_at_time_pm(self):
        result = self.agent._parse_time("remind me at 6 PM to call mom")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 18)
        self.assertEqual(result.minute, 0)

    def test_parse_at_time_am(self):
        result = self.agent._parse_time("set a reminder at 9 AM")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 9)

    def test_parse_at_hhmm_pm(self):
        result = self.agent._parse_time("remind me at 3:30 pm")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 15)
        self.assertEqual(result.minute, 30)

    # ── Tomorrow patterns ──────────────────────────────────────────────────────

    def test_parse_tomorrow_at(self):
        result = self.agent._parse_time("remind me tomorrow at 9 AM")
        self.assertIsNotNone(result)
        tomorrow = datetime.now() + timedelta(days=1)
        self.assertEqual(result.date(), tomorrow.date())
        self.assertEqual(result.hour, 9)

    # ── Unrecognised ───────────────────────────────────────────────────────────

    def test_parse_returns_none_for_unrecognised(self):
        result = self.agent._parse_time("Hello JARVIS")
        self.assertIsNone(result)


class TestReminderAgentTextExtraction(unittest.TestCase):

    def setUp(self):
        with patch('jarvis.agents.reminder_agent.ReminderStore'):
            self.agent = ReminderAgent()

    def test_extract_text_in_minutes(self):
        text = self.agent._extract_reminder_text("remind me in 10 minutes to drink water")
        self.assertIn("drink water", text.lower())

    def test_extract_text_at_pm(self):
        text = self.agent._extract_reminder_text("remind me at 6 PM to call mom")
        self.assertIn("call mom", text.lower())

    def test_extract_falls_back_to_full_text_if_empty(self):
        """If extraction yields nothing useful, return the full original text."""
        original = "remind me"
        result = self.agent._extract_reminder_text(original)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestReminderAgentHandle(unittest.TestCase):

    def setUp(self):
        with patch('jarvis.agents.reminder_agent.ReminderStore') as MockStore:
            self.mock_store = MockStore.return_value
            self.agent = ReminderAgent()
            self.agent.store = self.mock_store

    def test_handle_set_reminder(self):
        self.mock_store.add_reminder.return_value = 42
        reply = self.agent.handle("remind me in 5 minutes to take a break")
        self.assertIn("take a break", reply)  # reminder text extracted correctly
        self.assertIn("42", reply)            # reminder ID should appear
        self.assertIn("Understood", reply)    # JARVIS tone
        self.mock_store.add_reminder.assert_called_once()

    def test_handle_list_reminders_empty(self):
        self.mock_store.get_all_upcoming.return_value = []
        reply = self.agent.handle("show my reminders")
        self.assertIn("no upcoming", reply.lower())

    def test_handle_list_reminders_with_items(self):
        self.mock_store.get_all_upcoming.return_value = [
            {"id": 1, "text": "drink water", "fire_at": "2026-06-18 14:00:00"},
        ]
        reply = self.agent.handle("my reminders")
        self.assertIn("drink water", reply)

    def test_handle_cancel_all(self):
        reply = self.agent.handle("cancel all reminders")
        self.mock_store.clear_all_pending.assert_called_once()
        self.assertIn("cancelled", reply.lower())

    def test_handle_unparseable_time(self):
        reply = self.agent.handle("set a reminder for someday")
        self.assertIn("wasn't able", reply.lower())


if __name__ == "__main__":
    unittest.main()

"""
Tests for the One-on-One Communication Features:
  - ContactStore CRUD + interaction logging
  - CommunicationAgent._determine_mode()
  - CommunicationAgent._handle_contacts()
  - Keyword routing via _COMMUNICATION_KEYWORDS
"""
from __future__ import annotations

import os
import sys
import tempfile
import pytest

# ── Make jarvis importable from tests/ ────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jarvis.memory.contact_store import ContactStore
from jarvis.agents.communication_agent import (
    CommunicationAgent,
    _CHAT_ASSIST_KEYWORDS,
    _VOICE_CALL_KEYWORDS,
    _TRANSLATE_KEYWORDS,
    _EMOTION_KEYWORDS,
    _CONTACTS_KEYWORDS,
)
from jarvis.agents.router import _COMMUNICATION_KEYWORDS as ROUTER_COMM_KEYWORDS


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_store(tmp_path):
    """ContactStore backed by a temporary DB file."""
    db = str(tmp_path / "test_contacts.db")
    return ContactStore(db_path=db)


@pytest.fixture
def agent():
    """CommunicationAgent using a temp DB (no LLM needed for contact tests)."""
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "contacts.db")
        a = CommunicationAgent()
        a.contact_store = ContactStore(db_path=db)
        yield a


# ─────────────────────────────────────────────────────────────────────────────
# ContactStore — CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestContactStore:

    def test_add_contact_minimal(self, tmp_store):
        c = tmp_store.add_contact(name="Jay Davane")
        assert c["id"] is not None
        assert c["name"] == "Jay Davane"
        assert c["email"] == ""
        assert c["phone"] == ""

    def test_add_contact_full(self, tmp_store):
        c = tmp_store.add_contact(
            name="Rohan Mehta",
            phone="+91-9876543210",
            email="rohan@example.com",
            relationship="classmate",
            notes="Met at Mumbai Tech conference"
        )
        assert c["name"] == "Rohan Mehta"
        assert c["email"] == "rohan@example.com"
        assert c["relationship"] == "classmate"

    def test_get_contact(self, tmp_store):
        created = tmp_store.add_contact(name="Test User", email="test@test.com")
        fetched = tmp_store.get_contact(created["id"])
        assert fetched is not None
        assert fetched["name"] == "Test User"

    def test_get_nonexistent_contact(self, tmp_store):
        assert tmp_store.get_contact(99999) is None

    def test_update_contact(self, tmp_store):
        c = tmp_store.add_contact(name="Alice")
        updated = tmp_store.update_contact(c["id"], email="alice@new.com", notes="Updated note")
        assert updated["email"] == "alice@new.com"
        assert updated["notes"] == "Updated note"
        assert updated["name"] == "Alice"  # unchanged field preserved

    def test_update_contact_nonexistent(self, tmp_store):
        result = tmp_store.update_contact(99999, notes="nope")
        assert result is None

    def test_delete_contact(self, tmp_store):
        c = tmp_store.add_contact(name="ToDelete")
        assert tmp_store.delete_contact(c["id"]) is True
        assert tmp_store.get_contact(c["id"]) is None

    def test_delete_nonexistent(self, tmp_store):
        assert tmp_store.delete_contact(99999) is False

    def test_search_contacts_by_name(self, tmp_store):
        tmp_store.add_contact(name="Rohan Mehta", email="rohan@x.com")
        tmp_store.add_contact(name="Rohit Kumar", email="rohit@y.com")
        tmp_store.add_contact(name="Priya Sharma", email="priya@z.com")
        results = tmp_store.search_contacts("roh")
        assert len(results) == 2
        names = [r["name"] for r in results]
        assert "Rohan Mehta" in names
        assert "Rohit Kumar" in names

    def test_search_contacts_by_email(self, tmp_store):
        tmp_store.add_contact(name="Ananya Singh", email="ananya@gmail.com")
        results = tmp_store.search_contacts("gmail")
        assert len(results) == 1
        assert results[0]["name"] == "Ananya Singh"

    def test_search_contacts_no_results(self, tmp_store):
        results = tmp_store.search_contacts("zzznomatch999")
        assert results == []

    def test_list_all_ordered(self, tmp_store):
        tmp_store.add_contact(name="Zara")
        tmp_store.add_contact(name="Ananya")
        tmp_store.add_contact(name="Mihir")
        contacts = tmp_store.list_all()
        names = [c["name"] for c in contacts]
        assert names == sorted(names, key=str.lower)


# ─────────────────────────────────────────────────────────────────────────────
# ContactStore — Interactions
# ─────────────────────────────────────────────────────────────────────────────

class TestContactInteractions:

    def test_add_interaction(self, tmp_store):
        c = tmp_store.add_contact(name="Bob")
        i = tmp_store.add_interaction(c["id"], "Had a call about the project", "call")
        assert i["contact_id"] == c["id"]
        assert i["type"] == "call"
        assert "project" in i["summary"]

    def test_get_interactions_order(self, tmp_store):
        c = tmp_store.add_contact(name="Charlie")
        tmp_store.add_interaction(c["id"], "First meeting", "meeting")
        tmp_store.add_interaction(c["id"], "Follow-up call", "call")
        interactions = tmp_store.get_interactions(c["id"])
        assert len(interactions) == 2
        # Newest first
        assert interactions[0]["summary"] == "Follow-up call"

    def test_cascade_delete(self, tmp_store):
        """Deleting a contact must remove their interactions."""
        c = tmp_store.add_contact(name="DeleteMe")
        tmp_store.add_interaction(c["id"], "Some interaction", "chat")
        tmp_store.delete_contact(c["id"])
        interactions = tmp_store.get_interactions(c["id"])
        assert interactions == []

    def test_get_interactions_empty(self, tmp_store):
        c = tmp_store.add_contact(name="Nobody")
        assert tmp_store.get_interactions(c["id"]) == []


# ─────────────────────────────────────────────────────────────────────────────
# ContactStore — Formatting
# ─────────────────────────────────────────────────────────────────────────────

class TestContactFormatting:

    def test_format_contact_basic(self, tmp_store):
        c = tmp_store.add_contact(name="Jay", email="jay@test.com")
        card = tmp_store.format_contact(c)
        assert "Jay" in card
        assert "jay@test.com" in card

    def test_format_list_empty(self, tmp_store):
        result = tmp_store.format_list([])
        assert "No contacts found" in result

    def test_format_list_multiple(self, tmp_store):
        tmp_store.add_contact(name="Alice")
        tmp_store.add_contact(name="Bob")
        contacts = tmp_store.list_all()
        result = tmp_store.format_list(contacts)
        assert "Alice" in result
        assert "Bob" in result
        assert "2 contacts" in result


# ─────────────────────────────────────────────────────────────────────────────
# CommunicationAgent — Sub-mode detection
# ─────────────────────────────────────────────────────────────────────────────

class TestSubModeDetection:

    @pytest.mark.parametrize("message", [
        "suggest a response to this email",
        "help me reply to my boss",
        "rephrase this message",
        "make it professional please",
        "what should i say to him",
    ])
    def test_chat_assist_mode(self, agent, message):
        assert agent._determine_mode(message) == "chat_assist"

    @pytest.mark.parametrize("message", [
        "summarize call with the client",
        "give me the call summary",
        "call notes from today's meeting",
        "action items from call",
    ])
    def test_voice_call_mode(self, agent, message):
        assert agent._determine_mode(message) == "voice_call"

    @pytest.mark.parametrize("message", [
        "translate this to Spanish",
        "how do you say hello in French",
        "say this in Marathi",
        "translate the following text",
    ])
    def test_translate_mode(self, agent, message):
        assert agent._determine_mode(message) == "translate"

    @pytest.mark.parametrize("message", [
        "analyze tone of this message",
        "how does this sound to you",
        "is this too harsh",
        "soften this message",
        "detect emotion in this text",
    ])
    def test_emotion_mode(self, agent, message):
        assert agent._determine_mode(message) == "emotion"

    @pytest.mark.parametrize("message", [
        "list contacts",
        "add contact: Rohan, rohan@test.com",
        "who is Rohan",
        "delete contact: Alice",
        "my contacts",
    ])
    def test_contacts_mode(self, agent, message):
        assert agent._determine_mode(message) == "contacts"


# ─────────────────────────────────────────────────────────────────────────────
# CommunicationAgent — Contact CRUD via natural language
# ─────────────────────────────────────────────────────────────────────────────

class TestContactNaturalLanguage:

    def test_list_contacts_empty(self, agent):
        result = agent._handle_contacts("list contacts")
        assert "No contacts found" in result

    def test_add_contact_via_nl(self, agent):
        result = agent._handle_contacts("add contact: Rohan Mehta, rohan@example.com, classmate")
        assert "Rohan Mehta" in result
        assert "✅" in result

    def test_who_is_lookup(self, agent):
        agent._handle_contacts("add contact: Priya Sharma, priya@test.com, colleague")
        result = agent._handle_contacts("who is Priya")
        assert "Priya Sharma" in result

    def test_who_is_not_found(self, agent):
        result = agent._handle_contacts("who is Zorbax Xylon")
        assert "don't have" in result.lower() or "couldn't find" in result.lower()

    def test_delete_contact_by_name(self, agent):
        agent._handle_contacts("add contact: DeleteMe User, delete@test.com")
        result = agent._handle_contacts("delete contact: DeleteMe")
        assert "removed" in result.lower() or "deleted" in result.lower() or "DeleteMe" in result

    def test_list_contacts_after_add(self, agent):
        agent._handle_contacts("add contact: Alice Wonder, alice@w.com")
        result = agent._handle_contacts("list contacts")
        assert "Alice Wonder" in result

    def test_log_interaction_by_name(self, agent):
        agent._handle_contacts("add contact: TestUser, test@user.com")
        result = agent._handle_contacts("log interaction: TestUser, call, Discussed the project timeline")
        assert "TestUser" in result or "logged" in result.lower()

    def test_fallback_help_message(self, agent):
        result = agent._handle_contacts("contact manager help")
        assert "list contacts" in result.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Keyword routing integration
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordRouting:

    def test_communication_keywords_non_empty(self):
        assert len(ROUTER_COMM_KEYWORDS) > 20

    def test_all_submode_keywords_in_router_table(self):
        """Every keyword from each sub-mode must appear in the router's tuple."""
        missing = []
        for kw in (
            list(_CHAT_ASSIST_KEYWORDS)
            + list(_VOICE_CALL_KEYWORDS)
            + list(_TRANSLATE_KEYWORDS)
            + list(_EMOTION_KEYWORDS)
            + list(_CONTACTS_KEYWORDS)
        ):
            if kw not in ROUTER_COMM_KEYWORDS:
                missing.append(kw)
        assert missing == [], f"Missing from router keywords: {missing}"

    def test_sample_phrases_trigger_router(self):
        """Spot-check that sample phrases would trigger CommunicationAgent in the router."""
        sample_phrases = [
            "suggest a response to my colleague",
            "translate this to hindi",
            "analyze tone of my message",
            "list contacts",
            "summarize call from today",
        ]
        for phrase in sample_phrases:
            lower = phrase.lower()
            matched = any(kw in lower for kw in ROUTER_COMM_KEYWORDS)
            assert matched, f"Phrase not matched by router keywords: '{phrase}'"

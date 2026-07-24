"""
CommunicationAgent — One-on-One Communication Suite for JARVIS.

Five sub-modes, all powered by the HybridLLMRouter with specialized prompts:

  1. chat_assist  — Suggest responses, improve clarity, match tone
  2. voice_call   — Transcribe / summarise calls, generate follow-ups
  3. translate    — Instant message / conversation translation
  4. emotion      — Detect tone, suggest empathetic responses
  5. contacts     — Full CRUD contact manager with interaction history

Sub-mode is detected from the user message via _determine_mode().
The contacts sub-mode is handled locally (no LLM needed for CRUD ops);
the others stream through the LLM with a tuned system prompt.
"""
from __future__ import annotations

import logging
import re
from typing import AsyncGenerator
import json

from ..models.hybrid_router import HybridLLMRouter
from ..memory.contact_store import ContactStore
from .planner import get_jarvis_system_prompt
from ..voice.audio_transcriber import transcribe_audio

logger = logging.getLogger(__name__)


# ── Sub-mode keyword maps ──────────────────────────────────────────────────────

_CHAT_ASSIST_KEYWORDS = (
    "suggest response", "suggest a response", "suggest reply",
    "improve this message", "improve my message", "improve my text",
    "rephrase this", "rewrite this", "reword this",
    "make it clearer", "make this clearer", "make it professional",
    "match tone", "change tone", "help me reply", "how should i reply",
    "what should i say", "help me respond",
)

_VOICE_CALL_KEYWORDS = (
    "call summary", "summarize call", "summarise call",
    "call notes", "meeting transcript", "voice call",
    "transcribe call", "from this call", "follow-up from call",
    "action items from call", "key points from call",
    "what was discussed", "call transcript",
)

_TRANSLATE_KEYWORDS = (
    "translate this", "translate to", "translate into",
    "say this in", "how do you say", "how to say",
    "translate message", "in spanish", "in french",
    "in hindi", "in japanese", "in german", "in arabic",
    "in chinese", "in portuguese", "in marathi",
    "translate the following", "language translate",
)

_EMOTION_KEYWORDS = (
    "detect emotion", "analyze tone", "analyse tone",
    "how does this sound", "empathetic response",
    "sentiment analysis", "tone check", "tone of this",
    "emotional analysis", "how will this be received",
    "is this too harsh", "is this too formal", "sounds rude",
    "soften this", "make it kinder", "make it warmer",
)

_CONTACTS_KEYWORDS = (
    "add contact", "save contact", "new contact",
    "contact info", "who is", "tell me about",
    "interaction history", "update contact", "edit contact",
    "my contacts", "list contacts", "show contacts",
    "delete contact", "remove contact",
    "log interaction", "add interaction", "note interaction",
    "search contact", "find contact", "call ",
)


class CommunicationAgent:
    """
    Routes communication-related queries to one of five specialised sub-modes.

    Usage (same interface as all other JARVIS agents):
        async for chunk in agent.handle_stream(message, llm, history, semantic, voice_mode):
            yield chunk
    """

    def __init__(self):
        self.contact_store = ContactStore()

    # ── Sub-mode detection ─────────────────────────────────────────────────────

    def _determine_mode(self, message: str) -> str:
        msg_lower = message.lower()
        if any(k in msg_lower for k in _VOICE_CALL_KEYWORDS):
            return "voice_call"
        if any(k in msg_lower for k in _CONTACTS_KEYWORDS):
            return "contacts"
        if any(k in msg_lower for k in _TRANSLATE_KEYWORDS):
            return "translate"
        if any(k in msg_lower for k in _EMOTION_KEYWORDS):
            return "emotion"
        if any(k in msg_lower for k in _CHAT_ASSIST_KEYWORDS):
            return "chat_assist"
        # Default for any comm keyword that reached this agent
        return "chat_assist"

    # ── Skill-context injectors ────────────────────────────────────────────────

    def _get_skill_context(self, mode: str, message: str) -> str:
        base = "\n\nFor this request, you are in COMMUNICATION ASSISTANT MODE. "

        # -- Personality Mirroring (fetch recent user messages) --
        mirror_block = ""
        if hasattr(self, "router") and mode in ("chat_assist", "emotion"):
            recent = self.router.memory.get_recent_messages(limit=50)
            user_msgs = [m['content'] for m in recent if m['role'] == 'user' and len(m['content']) > 15]
            if user_msgs:
                mirror_block = (
                    "\n\n**Personality Mirroring (Crucial):**\n"
                    "Below are examples of the user's typical messaging style from past chats. "
                    "You MUST mirror this style (vocabulary, capitalization habits, tone, length) "
                    "in your suggested responses so they sound exactly like the user.\n"
                    + "\n".join(f"- \"{m}\"" for m in user_msgs[:10])
                )

        # -- Context-Aware Smart Replies (fetch contact history if name mentioned) --
        context_block = ""
        if mode == "chat_assist":
            # Very basic extraction: try to find a capitalized word or known contact name
            # A more robust way is to just search all known contact names in the message
            all_contacts = self.contact_store.list_all()
            for c in all_contacts:
                if c['name'].lower() in message.lower():
                    interactions = self.contact_store.get_interactions(c['id'], limit=3)
                    if interactions:
                        context_block = f"\n\n**Context for Contact '{c['name']}':**\n"
                        context_block += "Recent interactions you should reference or keep in mind:\n"
                        for i in interactions:
                            context_block += f"- {i['timestamp']}: {i['summary']}\n"
                    break

        if mode == "chat_assist":
            return base + (
                "The user needs help crafting or improving a message in a one-on-one conversation. "
                "Your job: (1) Suggest 2-3 alternative response options clearly labelled Option A, B, C. "
                "(2) For each option, briefly state the tone (e.g., Formal, Friendly, Assertive). "
                "(3) Point out any clarity issues in the original message. "
                "Keep responses concise and actionable. "
                "Always end with a short tip on improving the conversation."
            ) + context_block + mirror_block
        if mode == "voice_call":
            return base + (
                "The user has provided a voice call transcript or call notes. "
                "Your job: "
                "(1) **Summary** — Summarise the call in 3-5 bullet points. "
                "(2) **Key Decisions** — List any decisions made. "
                "(3) **Action Items** — List follow-up tasks with owners if mentioned. "
                "(4) **Follow-up Suggestions** — Suggest 2-3 follow-up messages or emails Jay could send. "
                "Be structured, clear, and concise. "
                "CRITICAL: If there are actionable follow-ups for the user with specific timeframes, "
                "output a JSON block at the very end of your response exactly like this:\n"
                "```json\n[\n  {\"text\": \"Task description\", \"time\": \"in 2 hours or tomorrow at 10 AM\"}\n]\n```\n"
            )
        if mode == "translate":
            return base + (
                "The user wants a translation. "
                "Your job: "
                "(1) Provide an accurate, natural-sounding translation. "
                "(2) If there are culturally nuanced phrases, briefly explain them. "
                "(3) If multiple interpretations exist, show the most common one first. "
                "(4) Provide a back-translation (the translation translated back to the source) "
                "to confirm accuracy. "
                "Always mention the source and target language clearly."
            )
        if mode == "emotion":
            return base + (
                "The user wants an emotional tone analysis of a message. "
                "Your job: "
                "(1) **Detected Tone** — Label the primary emotion(s) (e.g., frustrated, neutral, warm). "
                "(2) **How it may be received** — Explain how the recipient might interpret it. "
                "(3) **Suggested Rewrite** — Provide an empathetic, clear rewrite of the message. "
                "(4) **Tone Score** — Rate formality (1-10) and warmth (1-10). "
                "Be honest but constructive."
            ) + mirror_block
        # contacts — handled locally, no LLM skill context needed
        return base + "Assist the user with their contact management needs."

    # ── Contact manager (local, no LLM) ───────────────────────────────────────

    def _handle_contacts(self, message: str) -> str:
        """Parse the user message and perform the appropriate contact CRUD operation."""
        msg_lower = message.lower()

        # ── LIST all contacts ──────────────────────────────────────────────────
        if any(k in msg_lower for k in ("list contacts", "show contacts", "my contacts", "all contacts")):
            contacts = self.contact_store.list_all()
            return self.contact_store.format_list(contacts)

        # ── SEARCH / WHO IS ────────────────────────────────────────────────────
        who_match = re.search(
            r"(?:who is|tell me about|find contact|search contact|contact info(?:\s+for)?|search for)\s+(.+)",
            message,
            re.IGNORECASE
        )
        if who_match:
            name_query = who_match.group(1).strip().rstrip("?.,")
            contacts = self.contact_store.search_contacts(name_query)
            if not contacts:
                return f"I don't have anyone named **{name_query}** in your contacts, Jay."
            cards = []
            for c in contacts:
                cards.append(self.contact_store.format_contact(c, include_interactions=True))
            return "\n\n---\n\n".join(cards)

        # ── CALL contact ───────────────────────────────────────────────────────
        call_match = re.search(
            r"^call\s+(.+)",
            message,
            re.IGNORECASE
        )
        if call_match:
            name_query = call_match.group(1).strip().rstrip("?.,")
            contacts = self.contact_store.search_contacts(name_query)
            if not contacts:
                return f"I couldn't find {name_query} in your contacts. Please add them first using: add contact {name_query} [phone number]"
            
            if len(contacts) > 1:
                names = "\n".join(f"  • {c['name']}: {c.get('phone') or 'No number'}" for c in contacts)
                return f"I found multiple contacts for {name_query}. Which one should I call?\n{names}"
            
            contact = contacts[0]
            phone = contact.get("phone")
            if not phone:
                return f"I found {contact['name']}, but they don't have a phone number saved."
            
            from ..config import settings
            
            if not settings.twilio_sid or not settings.twilio_token or not settings.twilio_from_number:
                return f"📞 To call **{contact['name']}**, I need Twilio access. Please add `TWILIO_SID`, `TWILIO_TOKEN`, and `TWILIO_FROM_NUMBER` to your `.env` file and restart Jarvis!"
            
            try:
                from twilio.rest import Client
                import urllib.parse
                
                client = Client(settings.twilio_sid, settings.twilio_token)
                
                if not settings.user_phone_number:
                    return "📞 I need your personal phone number to initiate a two-way call. Please add `USER_PHONE_NUMBER` to your `.env` file!"
                
                # Format phone number for Twilio (assumes +91 for India if no country code)
                formatted_phone = phone.strip()
                if not formatted_phone.startswith('+'):
                    # Default to India (+91) based on user profile
                    formatted_phone = f"+91{formatted_phone}"
                
                # Create a TwiML payload to say a message, then Dial the target
                twiml = f"<Response><Say>Connecting you to {contact['name']}.</Say><Dial callerId='{settings.twilio_from_number}'>{formatted_phone}</Dial></Response>"
                twiml_url = f"http://twimlets.com/echo?Twiml={urllib.parse.quote(twiml)}"
                
                # Jarvis calls the USER first. When the user picks up, it dials the target.
                call = client.calls.create(
                    to=settings.user_phone_number,
                    from_=settings.twilio_from_number,
                    url=twiml_url
                )
                
                return f"📞 Ringing your phone first to connect you with **{contact['name']}** (Twilio Call SID: {call.sid})..."
            except ImportError:
                return "The `twilio` python package is not installed. Please run `pip install twilio`."
            except Exception as e:
                return f"❌ Failed to initiate Twilio call: {e}"

        # ── ADD contact ────────────────────────────────────────────────────────
        add_match = re.search(
            r"(?:add contact|save contact|new contact)[:\s]+(.+)",
            message,
            re.IGNORECASE
        )
        if add_match:
            raw = add_match.group(1).strip()
            phone = ""
            email = ""
            relationship = ""
            notes = ""
            # Parse comma-separated fields OR space-separated name and phone
            if "," in raw:
                parts = [p.strip() for p in raw.split(",")]
                name = parts[0] if parts else "Unknown"
                for part in parts[1:]:
                    if "@" in part:
                        email = part
                    elif re.search(r"[\d\+\-\(\)\s]{6,}", part):
                        phone = part.strip()
                    elif any(w in part.lower() for w in (
                        "friend", "colleague", "classmate", "boss", "manager",
                        "client", "family", "brother", "sister", "professor", "teacher"
                    )):
                        relationship = part
                    else:
                        notes = part
            else:
                # Try to extract phone from the end
                phone_match = re.search(r"([\d\+\-\(\)\s]{6,})$", raw)
                if phone_match:
                    phone = phone_match.group(1).strip()
                    name = raw[:phone_match.start()].strip()
                else:
                    name = raw

            contact = self.contact_store.add_contact(
                name=name, phone=phone, email=email,
                relationship=relationship, notes=notes
            )
            return (
                f"✅ Contact saved, Jay!\n\n"
                + self.contact_store.format_contact(contact)
            )

        # ── DELETE contact ─────────────────────────────────────────────────────
        del_match = re.search(
            r"(?:delete contact|remove contact)[:\s]+(.+)",
            message,
            re.IGNORECASE
        )
        if del_match:
            query = del_match.group(1).strip()
            # Try numeric ID first
            if query.isdigit():
                deleted = self.contact_store.delete_contact(int(query))
                return (
                    f"✅ Contact #{query} deleted."
                    if deleted
                    else f"❌ No contact with ID #{query} found."
                )
            # Search by name
            contacts = self.contact_store.search_contacts(query)
            if not contacts:
                return f"I couldn't find a contact named **{query}** to delete, Jay."
            if len(contacts) == 1:
                self.contact_store.delete_contact(contacts[0]["id"])
                return f"✅ **{contacts[0]['name']}** has been removed from your contacts."
            names = "\n".join(f"  • {c['name']} (ID: {c['id']})" for c in contacts)
            return (
                f"I found multiple contacts matching **{query}**. "
                f"Please specify the ID to delete:\n{names}"
            )

        # ── UPDATE contact ─────────────────────────────────────────────────────
        upd_match = re.search(
            r"(?:update contact|edit contact)[:\s]+(.+)",
            message,
            re.IGNORECASE
        )
        if upd_match:
            raw = upd_match.group(1).strip()
            parts = [p.strip() for p in raw.split(",")]
            if not parts[0].isdigit():
                return (
                    "To update a contact, say: **update contact: <ID>, <field>=<value>**\n"
                    "Example: `update contact: 3, notes=Met at Mumbai Tech event`"
                )
            contact_id = int(parts[0])
            fields = {}
            for part in parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    fields[k.strip()] = v.strip()
            if not fields:
                return "Please specify fields to update. Example: `update contact: 3, notes=Met at Mumbai Tech event`"
            updated = self.contact_store.update_contact(contact_id, **fields)
            if not updated:
                return f"❌ No contact with ID #{contact_id} found."
            return (
                f"✅ Contact updated!\n\n"
                + self.contact_store.format_contact(updated)
            )

        # ── LOG interaction ────────────────────────────────────────────────────
        log_match = re.search(
            r"(?:log interaction|add interaction|note interaction)[:\s]+(.+)",
            message,
            re.IGNORECASE
        )
        if log_match:
            raw = log_match.group(1).strip()
            parts = [p.strip() for p in raw.split(",", 2)]
            if len(parts) < 2:
                return (
                    "To log an interaction, say:\n"
                    "`log interaction: <contact_name_or_ID>, <type>, <summary>`\n"
                    "Example: `log interaction: Rohan, call, Discussed GroupSync deployment`"
                )
            id_or_name = parts[0]
            interaction_type = parts[1] if len(parts) > 1 else "general"
            summary = parts[2] if len(parts) > 2 else "No details provided."

            # Resolve name → ID
            contact_id = None
            if id_or_name.isdigit():
                contact_id = int(id_or_name)
            else:
                contacts = self.contact_store.search_contacts(id_or_name)
                if contacts:
                    contact_id = contacts[0]["id"]
            if not contact_id:
                return f"Couldn't find a contact matching **{id_or_name}**, Jay."

            interaction = self.contact_store.add_interaction(
                contact_id=contact_id,
                summary=summary,
                interaction_type=interaction_type,
            )
            contact = self.contact_store.get_contact(contact_id)
            name = contact["name"] if contact else f"#{contact_id}"
            return (
                f"✅ Interaction logged for **{name}**:\n"
                f"  • Type: {interaction['type'].upper()}\n"
                f"  • Summary: {interaction['summary']}\n"
                f"  • Time: {interaction['timestamp']}"
            )

        # ── Fallback ───────────────────────────────────────────────────────────
        contacts = self.contact_store.list_all()
        return (
            f"Here's what I can do with your contacts:\n\n"
            f"• **list contacts** — show all\n"
            f"• **who is <name>** — look up a contact\n"
            f"• **add contact: <name>, <email>, <phone>, <relationship>, <notes>**\n"
            f"• **update contact: <ID>, <field>=<value>**\n"
            f"• **delete contact: <name or ID>**\n"
            f"• **log interaction: <name/ID>, <type>, <summary>**\n\n"
            + (f"You currently have **{len(contacts)}** contact(s) saved." if contacts
               else "You have no contacts saved yet.")
        )

    async def _preprocess_message(self, message: str) -> str:
        """Transcribe any mentioned audio files before passing to LLM."""
        audio_match = re.search(r'([\w\-/\\]+\.(?:mp3|wav|m4a|ogg))', message, re.IGNORECASE)
        if audio_match:
            file_path = audio_match.group(1).strip()
            import os
            if os.path.isfile(file_path):
                transcript = await transcribe_audio(file_path)
                return f"{message}\n\n[Transcribed Audio from {file_path}]:\n{transcript}"
        return message

    def _postprocess_reminders(self, full_reply: str) -> str:
        """Extract JSON reminders from LLM output and add them to ReminderStore."""
        if not hasattr(self, "router"):
            return ""
        
        json_match = re.search(r'```json\s*(\[\s*\{.*?\}\s*\])\s*```', full_reply, re.DOTALL)
        if not json_match:
            return ""
        
        try:
            items = json.loads(json_match.group(1))
            added_count = 0
            for item in items:
                text = item.get("text")
                time_str = item.get("time", "")
                fire_at = self.router.reminder_agent._parse_time(time_str)
                if fire_at and text:
                    self.router.reminder_store.add_reminder(text, fire_at)
                    added_count += 1
            if added_count > 0:
                return f"\n\n*(I've also automatically set {added_count} reminder(s) for your action items!)*"
        except Exception as e:
            logger.error(f"Failed to parse auto-reminders: {e}")
        return ""

    # ── Public API ─────────────────────────────────────────────────────────────

    def handle(
        self,
        message: str,
        llm: HybridLLMRouter,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
    ) -> str:
        """Synchronous path (used by tests / _dispatch_sync)."""
        import asyncio
        # We need an event loop to run the async transcriber here
        try:
            loop = asyncio.get_running_loop()
            processed_message = loop.run_until_complete(self._preprocess_message(message))
        except RuntimeError:
            processed_message = asyncio.run(self._preprocess_message(message))

        mode = self._determine_mode(processed_message)
        logger.info(f"CommunicationAgent → mode: {mode}")

        if mode == "contacts":
            return self._handle_contacts(processed_message)

        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = (
            get_jarvis_system_prompt(voice_mode)
            + semantic_block
            + self._get_skill_context(mode, processed_message)
        )
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": processed_message}]
        )
        reply = llm.chat(messages)
        if mode == "voice_call":
            reminder_msg = self._postprocess_reminders(reply)
            if reminder_msg:
                # Remove the JSON block from the final output
                reply = re.sub(r'```json\s*\[\s*\{.*?\}\s*\]\s*```', '', reply, flags=re.DOTALL)
                reply += reminder_msg
        return reply

    async def handle_stream(
        self,
        message: str,
        llm: HybridLLMRouter,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
    ) -> AsyncGenerator[str, None]:
        """Async streaming path — used by the WebSocket handler."""
        processed_message = await self._preprocess_message(message)
        mode = self._determine_mode(processed_message)
        logger.info(f"CommunicationAgent streaming → mode: {mode}")

        if mode == "contacts":
            # Contacts are handled locally; yield the result as a single chunk
            yield self._handle_contacts(processed_message)
            return

        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = (
            get_jarvis_system_prompt(voice_mode)
            + semantic_block
            + self._get_skill_context(mode, processed_message)
        )
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": processed_message}]
        )
        full_reply = ""
        in_json_block = False
        async for chunk in llm.chat_stream(messages):
            full_reply += chunk
            # Hide the raw JSON block from the user as it streams
            if "```json" in chunk or in_json_block:
                in_json_block = True
                if "```\n" in full_reply.split("```json")[-1]:
                    in_json_block = False # block ended
                continue
            yield chunk
            
        if mode == "voice_call":
            reminder_msg = self._postprocess_reminders(full_reply)
            if reminder_msg:
                yield reminder_msg

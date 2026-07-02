import logging
import json
from ..models.hybrid_router import HybridLLMRouter
from .planner import get_jarvis_system_prompt
from ..memory.personal_store import PersonalStore

logger = logging.getLogger(__name__)

class PersonalAgent:
    """
    Handles Personal AI Capabilities:
    - Memory & Context
    - Goal Tracker
    - Health & Wellness
    - Financial Advisor
    - Creative Partner
    """
    def __init__(self):
        self.store = PersonalStore()

    def _determine_intent(self, message: str, llm: HybridLLMRouter) -> dict:
        """Use LLM to determine intent and extract structured data."""
        prompt = f"""
You are a Personal AI intent classifier. Given the user's message, determine the action and extract relevant data.
Return ONLY a raw JSON object with no markdown formatting.
Actions:
- 'add_health': user reports a health activity (sleep, diet, exercise). Fields: log_type, value
- 'add_finance': user reports an expense or income. Fields: log_type ('income' or 'expense'), amount (float), category, description
- 'add_goal': user wants to set a goal. Fields: title, description, target_date
- 'update_memory': user states a personal fact/preference to remember. Fields: key, value
- 'creative': user asks for creative ideas, brainstorming, design suggestions.
- 'query': user asks about their past data (how much did I spend, what are my goals, etc.)

Message: "{message}"

Example outputs:
{{"action": "add_health", "log_type": "exercise", "value": "ran 5 miles"}}
{{"action": "add_finance", "log_type": "expense", "amount": 50.0, "category": "food", "description": "lunch"}}
{{"action": "query"}}
"""
        messages = [{"role": "user", "content": prompt}]
        try:
            # We use a non-streaming chat for intent classification
            raw = llm.chat(messages)
            raw = raw.replace('```json', '').replace('```', '').strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"PersonalAgent intent parsing error: {e}")
            return {"action": "query"}

    def handle(self, message: str, llm: HybridLLMRouter, history: list, semantic: str = "", voice_mode: str = "calm_male") -> str:
        """Synchronous handler."""
        # For simplicity, fallback to handle_stream and await it if needed, but since it's sync here, we just do it synchronously.
        # Actually we just use handle_stream below for the websocket, so we don't strictly need a heavy handle().
        # But we'll implement a basic one anyway.
        return "Personal Agent processed your request."

    async def handle_stream(self, message: str, llm: HybridLLMRouter, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Asynchronous streaming handler."""
        intent = self._determine_intent(message, llm)
        action = intent.get("action", "query")
        
        system_context = ""
        action_confirmation = ""

        try:
            if action == "add_health":
                self.store.add_health_log(intent["log_type"], intent["value"])
                action_confirmation = f"I've logged your {intent['log_type']} ({intent['value']}). "
            elif action == "add_finance":
                self.store.add_financial_log(intent["log_type"], intent["amount"], intent.get("category", "general"), intent.get("description", ""))
                action_confirmation = f"I've logged your {intent['log_type']} of ${intent['amount']}. "
            elif action == "add_goal":
                self.store.add_goal(intent["title"], intent.get("description", ""), intent.get("target_date", ""))
                action_confirmation = f"I've added the goal: {intent['title']}. "
            elif action == "update_memory":
                self.store.set_memory(intent["key"], intent["value"])
                action_confirmation = f"I'll remember that {intent['key']} is {intent['value']}. "
        except Exception as e:
            logger.error(f"DB Error: {e}")

        # If it's a query or creative or just confirmation, build context from DB
        db_context = ""
        if action in ["query", "creative"] or action_confirmation:
            # Pull recent logs to give context
            goals = self.store.get_goals()[:3]
            finances = self.store.get_financial_logs(5)
            health = self.store.get_health_logs(5)
            memories = self.store.get_all_memory()
            
            db_context = "\n--- RECENT PERSONAL DATA ---\n"
            db_context += "Memories/Preferences: " + str(memories) + "\n"
            db_context += "Active Goals: " + str([g['title'] for g in goals]) + "\n"
            db_context += "Recent Finance: " + str([(f['log_type'], f['amount'], f['category']) for f in finances]) + "\n"
            db_context += "Recent Health: " + str([(h['log_type'], h['value']) for h in health]) + "\n"

        if action == "creative":
            system_context = "\n\nYou are a CREATIVE PARTNER. Brainstorm, generate ideas, and assist with designs or presentations beautifully. "
        else:
            system_context = "\n\nYou are an expert PERSONAL AI ASSISTANT acting as a Health Coach, Financial Advisor, and Goal Tracker. "

        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + system_context + db_context + "\n\n" + action_confirmation
        
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        
        async for chunk in llm.chat_stream(messages):
            yield chunk

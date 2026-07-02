import asyncio
import os
import sys

# Ensure the app can import jarvis
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jarvis.memory.personal_store import PersonalStore
from jarvis.agents.personal_agent import PersonalAgent

# Mock LLM for testing intent
class MockLLM:
    def chat(self, messages):
        # We'll just fake the json output based on the user prompt for the test
        prompt = messages[0]["content"]
        user_msg = messages[-1]["content"]
        if "spent $20" in user_msg:
            return '{"action": "add_finance", "log_type": "expense", "amount": 20.0, "category": "food"}'
        elif "ran 5km" in user_msg:
            return '{"action": "add_health", "log_type": "exercise", "value": "ran 5km"}'
        elif "goal to master python" in user_msg:
            return '{"action": "add_goal", "title": "Master Python"}'
        elif "remember that my favorite color is blue" in user_msg:
            return '{"action": "update_memory", "key": "favorite color", "value": "blue"}'
        return '{"action": "query"}'

    async def chat_stream(self, messages):
        yield "This is a streamed mock response from the Personal Agent."

async def run_tests():
    print("--- Starting Tests ---")
    store = PersonalStore()
    
    # 1. Test Store directly
    store.set_memory("test_key", "test_value")
    assert store.get_memory("test_key") == "test_value"
    print("OK: Memory Store working")
    
    store.add_health_log("sleep", "8 hours")
    health = store.get_health_logs()
    assert health[0]["log_type"] == "sleep"
    print("OK: Health Logs working")
    
    # 2. Test Agent routing and intent parsing
    agent = PersonalAgent()
    agent.store = store # Use the same store
    mock_llm = MockLLM()
    
    # Test inserting an expense
    print("Testing Agent: inserting expense")
    async for chunk in agent.handle_stream("I just spent $20 on lunch", mock_llm, []):
        pass
    finances = store.get_financial_logs()
    assert finances[0]["amount"] == 20.0
    print("OK: Agent parsed and inserted expense")
    
    # Test inserting a goal
    print("Testing Agent: inserting goal")
    async for chunk in agent.handle_stream("Set a goal to master python", mock_llm, []):
        pass
    goals = store.get_goals()
    assert goals[0]["title"] == "Master Python"
    print("OK: Agent parsed and inserted goal")
    
    print("--- All tests passed! ---")

if __name__ == "__main__":
    asyncio.run(run_tests())

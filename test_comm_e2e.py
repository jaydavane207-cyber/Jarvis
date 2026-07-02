import asyncio
import os
import sys

# Make jarvis importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jarvis.agents.router import AgentRouter

async def test_comm_agent():
    # Force UTF-8 for Windows console printing to avoid UnicodeEncodeError
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Initializing AgentRouter...")
    router = AgentRouter()
    
    test_queries = [
        # Chat Assist
        "Suggest a polite response to: We need you to work on Saturday.",
        # Translation
        "Translate this to Spanish: I will be late to the meeting.",
        # Voice Call
        "Summarize this call: John said he will deploy the app. Mary said she will write the tests. They agreed to finish by Friday.",
        "Summarize this audio file and give me action items: test.mp3",
        # Emotion
        "Analyze the tone of this message: What were you thinking when you wrote this garbage?",
        # Contacts (Local CRUD, shouldn't hit LLM)
        "add contact: testuser, test@example.com, friend",
        "who is testuser",
        "delete contact: testuser"
    ]
    
    print("\nStarting tests...")
    for query in test_queries:
        print(f"\n--- Query: {query} ---")
        try:
            # We'll use route_stream to mimic the WebSocket
            full_reply = ""
            async for chunk in router.route_stream(query):
                full_reply += chunk
            print(f"Reply ({len(full_reply)} chars):")
            print(full_reply[:200] + ("..." if len(full_reply) > 200 else ""))
            print("[SUCCESS]")
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_comm_agent())

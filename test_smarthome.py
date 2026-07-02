import asyncio
import sys

from jarvis.agents.smarthome_agent import SmartHomeAgent
from jarvis.models.ollama_client import OllamaClient

async def test_agent():
    print("Testing SmartHomeAgent...")
    agent = SmartHomeAgent()
    llm = OllamaClient()

    print("\n--- Test 1: Querying state ---")
    message = "Is the TV on? If so, turn it off."
    print(f"User: {message}")
    
    async for chunk in agent.handle_stream(message, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n")

    print("\n--- Test 2: Dangerous Action ---")
    message = "Unlock the front door."
    print(f"User: {message}")
    
    async for chunk in agent.handle_stream(message, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n")

if __name__ == "__main__":
    asyncio.run(test_agent())

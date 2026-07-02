import asyncio
import sys

from jarvis.agents.debugger_agent import DebuggerAgent
from jarvis.agents.smarthome_agent import SmartHomeAgent
from jarvis.agents.executor_agent import ExecutorAgent
from jarvis.models.ollama_client import OllamaClient

async def run_tests():
    llm = OllamaClient()

    print("=========================================")
    print(" 1. TESTING CODE DEBUGGER AGENT")
    print("=========================================")
    debugger = DebuggerAgent()
    message = "Debug this python code:\ndef add(a, b):\n  return a - b"
    print(f"User: {message}\n")
    print("Agent Reply:")
    async for chunk in debugger.handle_stream(message, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n\n")

    print("=========================================")
    print(" 2. TESTING IOT CONTROLLER AGENT")
    print("=========================================")
    smarthome = SmartHomeAgent()
    message1 = "Is the TV on? If so, turn it off."
    print(f"User: {message1}\n")
    print("Agent Reply:")
    async for chunk in smarthome.handle_stream(message1, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n\n")

    message2 = "Unlock the front door."
    print(f"User: {message2}\n")
    print("Agent Reply:")
    async for chunk in smarthome.handle_stream(message2, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n\n")

    print("=========================================")
    print(" 3. TESTING AUTONOMOUS TASK AGENT")
    print("=========================================")
    executor = ExecutorAgent()
    message3 = "Plan and execute: Print 'Hello World', wait 1 second, and print 'Done'."
    print(f"User: {message3}\n")
    print("Agent Reply:")
    async for chunk in executor.handle_stream(message3, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n\n")
    
    message4 = "Delete all files in this directory."
    print(f"User: {message4}\n")
    print("Agent Reply:")
    async for chunk in executor.handle_stream(message4, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n\n")

if __name__ == "__main__":
    asyncio.run(run_tests())

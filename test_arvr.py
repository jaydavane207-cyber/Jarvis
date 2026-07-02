import asyncio
import sys

from jarvis.agents.arvr_agent import ArVrAgent
from jarvis.models.ollama_client import OllamaClient

async def run_tests():
    llm = OllamaClient()

    print("=========================================")
    print(" TESTING AR/VR EXPERIENCE DESIGNER AGENT")
    print("=========================================")
    arvr = ArVrAgent()
    message = "I need to study the anatomy of the human heart. How should this be designed in VR?"
    print(f"User: {message}\n")
    print("Agent Reply:")
    async for chunk in arvr.handle_stream(message, llm, [], "", "calm_male"):
        print(chunk, end="", flush=True)
    print("\n\n")


if __name__ == "__main__":
    asyncio.run(run_tests())

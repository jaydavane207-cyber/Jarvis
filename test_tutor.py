import asyncio
import logging
import sys

# Add jarvis to path for imports
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from jarvis.agents.router import AgentRouter

logging.basicConfig(level=logging.ERROR)

async def test_features():
    router = AgentRouter()
    
    print("\n--- TEST 1: FLASHCARDS ---")
    response = router.route("Generate 3 flashcards for 8086 addressing modes")
    print(f"Agent Routed: {'TutorAgent' if 'FLASHCARD' in response else 'Unknown'}")
    print(response[:300] + "...\n")
    
    print("\n--- TEST 2: STUDY PLAN ---")
    response = router.route("Create a study plan for my microprocessor exams")
    print(f"Agent Routed: {'TutorAgent' if '|' in response else 'Unknown'}")
    print(response[:300] + "...\n")

    print("\n--- TEST 3: MIND MAP ---")
    response = router.route("Draw a mind map of the 8086 internal architecture")
    print(f"Agent Routed: {'TutorAgent' if 'MINDMAP' in response else 'Unknown'}")
    print(response[:300] + "...\n")

    print("\n--- TEST 4: QUIZ MODE ---")
    response = router.route("Quiz me on 8051 microcontroller timers")
    print(f"Agent Routed: {'TutorAgent' if 'AWAITING_ANSWER' in response else 'Unknown'}")
    print(response + "\n")

    print("\n--- TEST 5: RESEARCH ---")
    response = router.route("Search for academic papers on ARM Cortex architecture")
    print(f"Agent Routed: ResearchAgent")
    print(response[:300] + "...\n")

if __name__ == "__main__":
    asyncio.run(test_features())

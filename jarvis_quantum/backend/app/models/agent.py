from typing import List, Dict, Any, Callable
import logging

class Tool:
    def __init__(self, name: str, description: str, func: Callable):
        self.name = name
        self.description = description
        self.func = func

    def execute(self, *args, **kwargs) -> Any:
        try:
            return self.func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error executing tool {self.name}: {e}")
            return str(e)

class AutonomousAgent:
    """
    Core Autonomous Agent class for handling multi-step task execution
    and cognitive reasoning.
    """
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.tools: Dict[str, Tool] = {}
        self.memory: List[Dict[str, str]] = []

    def register_tool(self, tool: Tool):
        self.tools[tool.name] = tool
        logging.info(f"Agent {self.name} registered tool: {tool.name}")

    def add_memory(self, role: str, content: str):
        self.memory.append({"role": role, "content": content})

    def plan_execution(self, task: str) -> List[str]:
        # Simulate planning logic (e.g., calling an LLM to break down the task)
        self.add_memory("user", task)
        logging.info(f"Agent {self.name} planning task: {task}")
        # Mock plan for now
        plan = [
            f"Step 1: Analyze intent for task '{task}'",
            "Step 2: Identify required tools",
            "Step 3: Execute tools in sequence",
            "Step 4: Synthesize final output"
        ]
        self.add_memory("assistant", "Plan created: " + ", ".join(plan))
        return plan

    def execute_task(self, task: str) -> str:
        """
        Executes a complex task autonomously.
        In a real system, this loops through ReAct (Reasoning and Acting) cycles.
        """
        plan = self.plan_execution(task)
        
        # Simulate execution
        result = f"Task completed successfully by {self.name}.\nExecuted steps:\n"
        for step in plan:
            result += f"- {step}\n"
            
        self.add_memory("assistant", result)
        return result

# Core instance to be used across the app
core_agent = AutonomousAgent(name="Jarvis Core", role="Primary Orchestrator")

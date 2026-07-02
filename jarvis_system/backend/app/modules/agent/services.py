from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from app.modules.agent.models import Workflow, TaskStep
from app.modules.agent.schemas import WorkflowRequest
from app.core.zero_knowledge import zk_core
import asyncio

async def parse_objective_to_steps(objective: str):
    """
    Mock integration for generating a multi-step plan based on a high-level objective.
    In reality, this queries the local LLM.
    """
    await asyncio.sleep(1) # Simulate LLM generation time
    
    # Generic mock steps
    return [
        {"action": "search_web", "parameters": {"query": objective}, "order": 1},
        {"action": "analyze_data", "parameters": {"focus": "key entities"}, "order": 2},
        {"action": "execute_action", "parameters": {"final_step": True}, "order": 3}
    ]

async def create_workflow(db: AsyncSession, req: WorkflowRequest) -> Workflow:
    workflow = Workflow(objective=req.objective, status="running")
    db.add(workflow)
    await db.flush() # Get workflow.id

    steps_data = await parse_objective_to_steps(req.objective)
    
    for step_data in steps_data:
        encrypted_params = zk_core.encrypt_payload(step_data["parameters"])
        step = TaskStep(
            workflow_id=workflow.id,
            action=step_data["action"],
            parameters_encrypted=encrypted_params,
            order_index=step_data["order"]
        )
        db.add(step)

    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow.id).options(selectinload(Workflow.steps))
    )
    return result.scalar_one()

async def get_workflow_status(db: AsyncSession, workflow_id: int):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id).options(selectinload(Workflow.steps))
    )
    return result.scalar_one_or_none()

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.agent.schemas import WorkflowRequest, WorkflowResponse
from app.modules.agent import services

router = APIRouter()

@router.post("/execute", response_model=WorkflowResponse)
async def execute_workflow(req: WorkflowRequest, db: AsyncSession = Depends(get_db)):
    """Initiate a multi-step autonomous agent workflow based on a high-level objective."""
    return await services.create_workflow(db, req)

@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve the current status and steps of a workflow."""
    workflow = await services.get_workflow_status(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow

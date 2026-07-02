from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.modules.productivity.schemas import TaskCreate, TaskResponse
from app.modules.productivity import services

router = APIRouter()

@router.post("/tasks", response_model=TaskResponse)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Create a new task with Eisenhower matrix prioritization."""
    return await services.create_task(db, task)

@router.get("/tasks", response_model=List[TaskResponse])
async def read_tasks(db: AsyncSession = Depends(get_db)):
    """Retrieve all tasks sorted by priority."""
    return await services.get_tasks(db)

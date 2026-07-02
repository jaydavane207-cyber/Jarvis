from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict
from app.models.agent import core_agent
from app.models.work_models import Task, DataAnalysisRequest
import uuid

router = APIRouter(prefix="/work", tags=["work"])

tasks_db: List[Task] = []

class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    deadline_str: str  # ISO Format
    is_urgent: bool
    is_important: bool

class AutonomousRequest(BaseModel):
    instruction: str

@router.post("/tasks")
async def create_task(req: TaskCreateRequest):
    from datetime import datetime
    task = Task(
        id=str(uuid.uuid4()),
        title=req.title,
        description=req.description,
        priority="High" if req.is_important else "Medium",
        deadline=datetime.fromisoformat(req.deadline_str),
        is_urgent=req.is_urgent,
        is_important=req.is_important
    )
    tasks_db.append(task)
    return {"message": "Task created.", "task_id": task.id}

@router.get("/tasks/eisenhower")
async def get_eisenhower_matrix() -> Dict[str, List[Task]]:
    matrix = {
        "do_first": [t for t in tasks_db if t.is_important and t.is_urgent],
        "schedule": [t for t in tasks_db if t.is_important and not t.is_urgent],
        "delegate": [t for t in tasks_db if not t.is_important and t.is_urgent],
        "eliminate": [t for t in tasks_db if not t.is_important and not t.is_urgent],
    }
    return matrix

@router.post("/data/analyze")
async def analyze_data(req: DataAnalysisRequest):
    # Simulated Data Analyzer (representing Plotly/Matplotlib logic)
    # In a real app, this would load the CSV and generate a chart object.
    
    analysis_result = {
        "dataset": req.dataset_name,
        "columns_processed": req.columns_to_analyze,
        "chart_generated": req.chart_type,
        "insights": f"Found strong correlation in {req.columns_to_analyze[0]} over time." if req.columns_to_analyze else "No columns specified."
    }
    
    return {"status": "Analysis Complete", "report": analysis_result}

@router.post("/autonomous")
async def run_autonomous_agent(req: AutonomousRequest):
    """
    Executes a multi-step workflow autonomously via Jarvis Core.
    Example: 'Plan Goa trip'
    """
    result = core_agent.execute_task(req.instruction)
    return {"status": "Completed", "result": result}


from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TaskStepSchema(BaseModel):
    id: int
    action: str
    status: str
    order_index: int
    
    class Config:
        orm_mode = True

class WorkflowRequest(BaseModel):
    objective: str

class WorkflowResponse(BaseModel):
    id: int
    objective: str
    status: str
    created_at: datetime
    steps: List[TaskStepSchema] = []

    class Config:
        orm_mode = True

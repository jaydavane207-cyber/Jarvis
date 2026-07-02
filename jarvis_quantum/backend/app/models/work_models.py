from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    priority: str  # High, Medium, Low
    deadline: datetime
    is_urgent: bool = False
    is_important: bool = False
    status: str = "pending"

class DataAnalysisRequest(BaseModel):
    dataset_name: str
    columns_to_analyze: List[str]
    chart_type: str = "bar" # bar, line, pie

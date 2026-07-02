from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

class Note(BaseModel):
    id: str
    content: str
    tags: List[str]
    created_at: datetime = datetime.now()

class Flashcard(BaseModel):
    id: str
    front: str
    back: str
    next_review: datetime = datetime.now()
    interval: int = 1 # days
    ease_factor: float = 2.5
    repetitions: int = 0

class RAGQuery(BaseModel):
    question: str
    context_tags: Optional[List[str]] = None

class StudyPlannerRequest(BaseModel):
    topics: List[str]
    exam_date: datetime
    current_energy_level: int # 1 to 100

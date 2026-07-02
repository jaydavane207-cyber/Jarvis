from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class NoteBase(BaseModel):
    title: str
    content: str

class NoteCreate(NoteBase):
    pass

class NoteResponse(BaseModel):
    id: int
    title: str
    content: str # Decrypted for the client
    created_at: datetime
    
    class Config:
        orm_mode = True

class FlashcardBase(BaseModel):
    front: str
    back: str
    
class FlashcardResponse(FlashcardBase):
    id: int
    note_id: int
    next_review: datetime
    
    class Config:
        orm_mode = True

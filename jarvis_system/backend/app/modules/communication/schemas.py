from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ContactBase(BaseModel):
    name: str
    details: str

class ContactCreate(ContactBase):
    pass

class ContactResponse(BaseModel):
    id: int
    name: str
    details: str
    created_at: datetime
    
    class Config:
        orm_mode = True

class TranslateRequest(BaseModel):
    text: str
    target_language: str # e.g., "mr" (Marathi), "hi" (Hindi)

class TranslateResponse(BaseModel):
    original_text: str
    translated_text: str
    target_language: str

class EmotionDetectRequest(BaseModel):
    text: str

class EmotionDetectResponse(BaseModel):
    detected_emotion: str
    confidence_score: float
    deception_probability: float # JARVIS Deception Detector

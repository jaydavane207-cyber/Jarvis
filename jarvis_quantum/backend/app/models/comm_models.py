from pydantic import BaseModel
from typing import Optional, List

class TranscriptionRequest(BaseModel):
    audio_file_path: str
    extract_action_items: bool = True

class TranslationRequest(BaseModel):
    text: str
    target_lang: str

class EmotionDetectionRequest(BaseModel):
    text: str

class CommunicationAnalysisResponse(BaseModel):
    original_text: str
    emotion_detected: str
    deception_probability: float
    suggested_response: str

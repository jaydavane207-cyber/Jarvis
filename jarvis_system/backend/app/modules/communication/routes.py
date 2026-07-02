from fastapi import APIRouter
from app.modules.communication.schemas import TranslateRequest, TranslateResponse, EmotionDetectRequest, EmotionDetectResponse
from app.modules.communication import services

router = APIRouter()

@router.post("/translate", response_model=TranslateResponse)
async def translate_text(req: TranslateRequest):
    """Instantly translate text across 50+ languages (Mocked)."""
    return await services.perform_translation(req)

@router.post("/detect-emotion", response_model=EmotionDetectResponse)
async def detect_emotion(req: EmotionDetectRequest):
    """Analyze text for emotional state and potential deception."""
    return await services.analyze_emotion_and_deception(req)

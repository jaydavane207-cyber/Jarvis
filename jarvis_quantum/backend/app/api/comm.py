from fastapi import APIRouter, WebSocket
from typing import Dict
from app.models.comm_models import TranslationRequest, EmotionDetectionRequest, CommunicationAnalysisResponse

router = APIRouter(prefix="/comm", tags=["communication"])

# Simple in-memory connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Simulate real-time tone improvement and emotion detection
            await manager.send_personal_message(f"Jarvis [Empathetic Tone]: I hear you. You said: {data}", websocket)
    except Exception as e:
        manager.disconnect(websocket)

@router.post("/translate")
async def translate_text(req: TranslationRequest):
    # Stub for Instant language translator (Marathi, Hindi, English)
    return {"original": req.text, "translated": f"[Simulated {req.target_lang} Translation of '{req.text}']"}

@router.post("/analyze-emotion")
async def analyze_emotion_and_deception(req: EmotionDetectionRequest) -> CommunicationAnalysisResponse:
    # Simulated Emotion and Deception Analysis
    # In production, this would pass through a local LLM or fine-tuned model
    text_lower = req.text.lower()
    
    emotion = "Neutral"
    deception_prob = 0.05
    
    if "angry" in text_lower or "hate" in text_lower or "frustrated" in text_lower:
        emotion = "Angry/Frustrated"
    elif "happy" in text_lower or "great" in text_lower:
        emotion = "Joyful"
    elif "um" in text_lower or "uh" in text_lower or "maybe" in text_lower or "i think" in text_lower:
        emotion = "Hesitant"
        deception_prob = 0.65  # Higher probability of deception/uncertainty if hesitating
        
    suggested_response = f"Jarvis suggests a calming, professional response." if emotion == "Angry/Frustrated" else "Jarvis suggests an affirmative response."
    
    return CommunicationAnalysisResponse(
        original_text=req.text,
        emotion_detected=emotion,
        deception_probability=deception_prob,
        suggested_response=suggested_response
    )


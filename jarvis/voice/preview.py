from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import requests, io, os

router = APIRouter()

# ElevenLabs voice ID mapping — replace with your actual ElevenLabs voice IDs
VOICE_MAP = {
    "calm_male":          "pNInz6obpgDQGcFmaJgB",   # Adam
    "energetic_male":     "ErXwobaYiN019PkySvjV",   # Antoni
    "friendly_female":    "EXAVITQu4vr4xnSDxMaL",   # Bella
    "professional_female":"21m00Tcm4TlvDq8ikWAM",   # Rachel
}

PREVIEW_TEXT = "Hi Jay, I'm ready. How can I help you today?"

@router.post("/api/voice/preview")
async def voice_preview(payload: dict):
    voice_key = payload.get("voice", "calm_male").lower().replace(" ", "_")
    voice_id = VOICE_MAP.get(voice_key)

    if not voice_id:
        return {"error": f"Unknown voice: {voice_key}"}

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    # If no ElevenLabs key or it's a placeholder, use local edge-tts fallback
    if not api_key or api_key == "your_elevenlabs_api_key" or api_key == "your_api_key_here":
        return await _edge_tts_speak(voice_key, PREVIEW_TEXT)

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "text": PREVIEW_TEXT,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.75,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            }
        )

        if response.status_code == 200:
            audio_bytes = response.content
            return StreamingResponse(
                io.BytesIO(audio_bytes),
                media_type="audio/mpeg",
                headers={"Content-Disposition": "inline; filename=preview.mp3"}
            )
        else:
            # If ElevenLabs fails, fallback to local edge-tts
            return await _edge_tts_speak(voice_key, PREVIEW_TEXT)

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/voice/speak")
async def voice_speak(payload: dict):
    voice_key = payload.get("voice", "calm_male").lower().replace(" ", "_")
    text = payload.get("text", "Hello!")
    voice_id = VOICE_MAP.get(voice_key)

    if not voice_id:
        return {"error": f"Unknown voice: {voice_key}"}

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    if not api_key or api_key == "your_elevenlabs_api_key" or api_key == "your_api_key_here":
        return await _edge_tts_speak(voice_key, text)

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.75,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            }
        )

        if response.status_code == 200:
            return StreamingResponse(
                io.BytesIO(response.content),
                media_type="audio/mpeg",
                headers={"Content-Disposition": "inline; filename=speech.mp3"}
            )
        else:
            return await _edge_tts_speak(voice_key, text)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

async def _edge_tts_speak(voice_key: str, text: str):
    """Offline fallback using edge-tts for highly natural voices"""
    import edge_tts, tempfile, os

    # Map to distinct, natural Microsoft Edge Neural voices
    # Using different accents (US vs GB) ensures they sound completely distinct
    voice_map = {
        "calm_male": "en-US-ChristopherNeural",   # Deep, authoritative US male
        "energetic_male": "en-GB-RyanNeural",     # Bright, crisp British male
        "friendly_female": "en-US-AnaNeural",     # High-pitched, bright, conversational
        "professional_female": "en-US-AriaNeural" # Deep, formal, professional
    }

    voice = voice_map.get(voice_key, "en-US-AriaNeural")
    rate = "+15%" if "energetic" in voice_key else "+0%"

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()  # Close so edge-tts can write to it on Windows

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(tmp.name)

    import time
    audio = b""
    for _ in range(10):
        try:
            with open(tmp.name, "rb") as f:
                audio = f.read()
            break
        except PermissionError:
            time.sleep(0.1)

    try:
        os.unlink(tmp.name)
    except:
        pass

    return StreamingResponse(
        io.BytesIO(audio),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=preview.mp3"}
    )


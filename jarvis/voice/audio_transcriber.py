"""
AudioTranscriber — Lightweight wrapper around faster-whisper.
Lazily loads the model into memory only upon first request to keep JARVIS fast.
"""
import logging
import os
import asyncio

logger = logging.getLogger(__name__)

# Initialize model variable
_whisper_model = None
_model_lock = asyncio.Lock()


async def transcribe_audio(file_path: str) -> str:
    """
    Transcribes an audio file (.mp3, .wav, etc.) using faster-whisper.
    Returns the transcribed text.
    Loads the 'tiny' model into memory on the first call.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    global _whisper_model
    
    # Lazy load the model with a lock to prevent concurrent loading issues
    if _whisper_model is None:
        async with _model_lock:
            if _whisper_model is None:
                logger.info("Lazy-loading faster-whisper 'tiny.en' model...")
                from faster_whisper import WhisperModel
                # Using 'tiny.en' for speed and memory efficiency on CPU
                _whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                logger.info("faster-whisper model loaded successfully.")

    logger.info(f"Transcribing audio file: {file_path}")
    
    # Transcription is blocking, so run it in a thread pool to avoid freezing FastAPI
    loop = asyncio.get_running_loop()
    
    def run_transcription():
        segments, info = _whisper_model.transcribe(file_path, beam_size=5)
        text = " ".join([segment.text for segment in segments])
        return text.strip()

    try:
        transcription = await loop.run_in_executor(None, run_transcription)
        return transcription
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return f"[Transcription Failed: {e}]"

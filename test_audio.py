import asyncio
import os
import sys

# Make jarvis importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jarvis.voice.audio_transcriber import transcribe_audio
import logging

logging.basicConfig(level=logging.INFO)

async def test_transcribe():
    print("Testing transcription on test.mp3...")
    result = await transcribe_audio("test.mp3")
    print("\nResult:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_transcribe())

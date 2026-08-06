"""
Unit tests for JARVIS Voice Barge-In & Audio API Endpoints.
Tests:
  1. /api/voice/speak TTS generation
  2. /api/voice/transcribe faster-whisper endpoint
  3. /ws WebSocket stream cancellation & barge-in signal handling
"""
import pytest
import os
import json
from fastapi.testclient import TestClient
from jarvis.main import app

client = TestClient(app)

def test_voice_speak_endpoint():
    """Test /api/voice/speak endpoint returns valid audio response."""
    response = client.post(
        "/api/voice/speak",
        json={"text": "Test speech for voice bargein unit test.", "voice": "calm_male"}
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") in ("audio/mpeg", "audio/mp3")
    assert len(response.content) > 0

def test_voice_transcribe_endpoint(tmp_path):
    """Test /api/voice/transcribe endpoint accepts audio uploads."""
    # Create a small dummy audio wav file
    wav_file = tmp_path / "test.wav"
    # Simple 1-second silent WAV header + PCM audio bytes
    wav_header = (
        b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00'
        b'\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
    )
    wav_file.write_bytes(wav_header)

    with open(wav_file, "rb") as f:
        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("test.wav", f, "audio/wav")}
        )

    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert data["success"] is True

def test_websocket_barge_in_cancellation():
    """Test WebSocket accepts cancel_stream signal and returns barge_in_ack."""
    with client.websocket_connect("/ws") as websocket:
        # Send barge_in signal
        websocket.send_json({"type": "cancel_stream"})
        data = websocket.receive_json()
        assert data.get("type") == "barge_in_ack"
        assert "Go ahead" in data.get("text", "")

if __name__ == "__main__":
    pytest.main(["-v", __file__])

from pydantic import BaseModel
from typing import List, Dict

class NeuralTelemetryPayload(BaseModel):
    device_id: str
    timestamp: float
    channels: Dict[str, float] # e.g., 'AF3': 42.1, 'F7': 39.5
    inferred_intent: str = "" # JARVIS parses this on the fly

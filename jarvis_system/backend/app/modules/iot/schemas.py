from pydantic import BaseModel
from typing import List, Dict, Optional

class IoTDeviceState(BaseModel):
    device_id: str
    device_type: str # thermostat, lock, light
    current_state: Dict[str, str]

class PredictHomeEnvRequest(BaseModel):
    user_location: str # e.g., "leaving_office"
    estimated_arrival_minutes: int

class PredictHomeEnvResponse(BaseModel):
    actions_triggered: List[str]
    energy_optimization_mode: bool

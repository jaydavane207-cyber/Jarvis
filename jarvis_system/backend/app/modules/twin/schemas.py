from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RotateIdentityRequest(BaseModel):
    target_layer: str # test, partial, real
    biometric_signature: str # A mocked biometric string for validation

class RotateIdentityResponse(BaseModel):
    status: str
    current_layer: str
    rotation_timestamp: datetime
    quantum_container_id: Optional[str] = None

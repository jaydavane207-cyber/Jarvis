from pydantic import BaseModel
from typing import List, Dict

class SpatialObject(BaseModel):
    id: str
    type: str # window, widget, avatar
    position: Dict[str, float] # x, y, z
    rotation: Dict[str, float] # rx, ry, rz

class EnvironmentDescriptorResponse(BaseModel):
    environment_name: str
    ambient_lighting: str
    objects: List[SpatialObject]

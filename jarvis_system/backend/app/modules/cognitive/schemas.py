from pydantic import BaseModel
from typing import List, Dict

class SynthesizeRequest(BaseModel):
    concepts: List[str]
    context_depth: str = "deep" # shallow, deep

class SynthesizeResponse(BaseModel):
    synthesized_idea: str
    supporting_nodes: List[Dict[str, str]]

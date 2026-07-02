from fastapi import APIRouter
from app.modules.arvr.schemas import EnvironmentDescriptorResponse
from app.modules.arvr import services

router = APIRouter()

@router.get("/environment", response_model=EnvironmentDescriptorResponse)
async def get_3d_environment():
    """Generate dynamic spatial environment coordinates for AR/VR headsets."""
    return await services.generate_dynamic_environment()

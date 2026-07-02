from fastapi import APIRouter
from app.modules.iot.schemas import PredictHomeEnvRequest, PredictHomeEnvResponse
from app.modules.iot import services

router = APIRouter()

@router.post("/home/predict", response_model=PredictHomeEnvResponse)
async def predict_home_env(req: PredictHomeEnvRequest):
    """Predictive IoT automation based on user location and telemetry."""
    return await services.predict_home_environment(req)

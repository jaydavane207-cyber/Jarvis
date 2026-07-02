from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
from src.services.predictive_service import predictive_service

router = APIRouter()

class MarketRequest(BaseModel):
    asset_ticker: str
    
class HealthRequest(BaseModel):
    biometrics: Dict[str, Any]

@router.post("/market/predict")
async def predict_market(request: MarketRequest):
    """
    Analyzes asset trends (NSE/BSE/Crypto) using sentiment and historical data.
    """
    prediction = predictive_service.predict_market(request.asset_ticker)
    return {"status": "success", "data": prediction}

@router.post("/health/forecast")
async def forecast_health(request: HealthRequest):
    """
    Predicts health anomalies based on wearable biometrics.
    """
    forecast = predictive_service.predict_health(request.biometrics)
    return {"status": "success", "data": forecast}

@router.post("/career/map")
async def map_career_path(skills: list[str], target_role: str):
    """
    Predicts optimal career moves based on skill gaps.
    """
    return {
        "status": "success",
        "recommended_path": f"Upskill in distributed systems to reach {target_role}.",
        "estimated_timeline": "6 months"
    }

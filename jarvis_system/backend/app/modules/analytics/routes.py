from fastapi import APIRouter
from app.modules.analytics.schemas import (
    MarketPredictionRequest, MarketPredictionResponse,
    CareerMapperRequest, CareerMapperResponse
)
from app.modules.analytics import services

router = APIRouter()

@router.post("/market", response_model=MarketPredictionResponse)
async def predict_market(req: MarketPredictionRequest):
    """Predict stock/crypto movements localized for NSE/BSE."""
    return await services.predict_market_trend(req)

@router.post("/career", response_model=CareerMapperResponse)
async def map_career(req: CareerMapperRequest):
    """Predict optimal career moves based on skill gaps."""
    return await services.map_career_path(req)

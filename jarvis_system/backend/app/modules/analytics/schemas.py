from pydantic import BaseModel
from typing import List

class MarketPredictionRequest(BaseModel):
    ticker: str
    exchange: str = "NSE" # NSE, BSE, etc.

class MarketPredictionResponse(BaseModel):
    ticker: str
    trend_direction: str
    confidence_score: float
    key_drivers: List[str]
    risk_factors: List[str]

class CareerMapperRequest(BaseModel):
    current_role: str
    skills: List[str]

class CareerMapperResponse(BaseModel):
    recommended_path: str
    missing_skills: List[str]
    expected_timeline_months: int

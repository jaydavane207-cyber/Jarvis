from pydantic import BaseModel
from typing import List, Optional

class MarketPredictionRequest(BaseModel):
    ticker: str
    timeframe: str # short-term, mid-term, long-term
    market: str = "NSE" # NSE, BSE, NASDAQ

class MarketPredictionResponse(BaseModel):
    ticker: str
    trend: str
    confidence_score: float
    key_drivers: List[str]
    risk_factors: List[str]

class AcademicPredictionRequest(BaseModel):
    subject: str
    study_hours_logged: float
    average_quiz_score: float

class AcademicPredictionResponse(BaseModel):
    subject: str
    predicted_score_range: str
    confidence_score: float
    recommended_focus: List[str]

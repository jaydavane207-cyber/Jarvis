from pydantic import BaseModel
from typing import Optional

class UPIFraudCheckRequest(BaseModel):
    vpa: str # Virtual Payment Address (UPI ID)
    amount: float
    merchant_category_code: Optional[str] = None

class UPIFraudCheckResponse(BaseModel):
    vpa: str
    is_safe: bool
    risk_score: float # 0.0 to 1.0
    warning_message: Optional[str] = None

class IRCTCBookingRequest(BaseModel):
    source_station: str
    destination_station: str
    date: str
    class_preference: str

class IRCTCBookingResponse(BaseModel):
    train_options_found: int
    auto_booked: bool
    pnr_status: Optional[str] = None

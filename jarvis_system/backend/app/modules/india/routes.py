from fastapi import APIRouter
from app.modules.india.schemas import (
    UPIFraudCheckRequest, UPIFraudCheckResponse,
    IRCTCBookingRequest, IRCTCBookingResponse
)
from app.modules.india import services

router = APIRouter()

@router.post("/upi/fraud-check", response_model=UPIFraudCheckResponse)
async def check_upi_fraud(req: UPIFraudCheckRequest):
    """Predict and prevent UPI scams using localized fraud patterns."""
    return await services.validate_upi_fraud(req)

@router.post("/irctc/book", response_model=IRCTCBookingResponse)
async def book_irctc(req: IRCTCBookingRequest):
    """Automate IRCTC train booking."""
    return await services.book_irctc_ticket(req)

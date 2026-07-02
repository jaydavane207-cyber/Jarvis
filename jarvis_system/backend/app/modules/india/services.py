import asyncio
import re
from app.modules.india.schemas import (
    UPIFraudCheckRequest, UPIFraudCheckResponse,
    IRCTCBookingRequest, IRCTCBookingResponse
)

async def validate_upi_fraud(req: UPIFraudCheckRequest) -> UPIFraudCheckResponse:
    """
    Mock integration for UPI transaction shield.
    Evaluates real-time fraud metrics.
    """
    await asyncio.sleep(0.4)
    
    # Generic mockup: Block if the VPA looks highly suspicious or amount is massive for unknown merchant
    suspicious_patterns = [r"kyc", r"refund", r"cashback"]
    is_suspicious = any(re.search(pat, req.vpa.lower()) for pat in suspicious_patterns)
    
    risk = 0.89 if is_suspicious else 0.05
    
    return UPIFraudCheckResponse(
        vpa=req.vpa,
        is_safe=not is_suspicious,
        risk_score=risk,
        warning_message="Suspicious keyword detected in UPI handle." if is_suspicious else None
    )

async def book_irctc_ticket(req: IRCTCBookingRequest) -> IRCTCBookingResponse:
    """
    Mock integration for Railway booking automation.
    """
    await asyncio.sleep(1.2) # Simulate IRCTC API latency
    
    return IRCTCBookingResponse(
        train_options_found=4,
        auto_booked=True,
        pnr_status="CONFIRMED (Mock)"
    )

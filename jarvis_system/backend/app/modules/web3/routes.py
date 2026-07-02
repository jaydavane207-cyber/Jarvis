from fastapi import APIRouter
from app.modules.web3.schemas import (
    WalletBalanceResponse, 
    SmartContractAuditRequest, 
    SmartContractAuditResponse
)
from app.modules.web3 import services

router = APIRouter()

@router.get("/wallet/{address}/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(address: str):
    """Retrieve wallet balance and yield farming status."""
    return await services.check_wallet_balance(address)

@router.post("/audit", response_model=SmartContractAuditResponse)
async def audit_contract(req: SmartContractAuditRequest):
    """Scan a smart contract for vulnerabilities."""
    return await services.audit_smart_contract(req)

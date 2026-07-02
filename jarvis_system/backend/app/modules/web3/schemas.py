from pydantic import BaseModel
from typing import List, Optional

class WalletBalanceResponse(BaseModel):
    public_address: str
    chain: str
    balance_usd: float
    is_yield_farming: bool

class SmartContractAuditRequest(BaseModel):
    contract_code: str

class SmartContractAuditResponse(BaseModel):
    vulnerabilities_found: int
    risk_level: str # low, medium, high, critical
    details: List[str]

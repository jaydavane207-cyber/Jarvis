from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta
from src.core.config import settings
from src.security.quantum_crypto import quantum_crypto
from src.security.zero_knowledge import ZeroKnowledgeProof
from src.security.digital_twin import digital_twin_manager

router = APIRouter()

class TwinRequest(BaseModel):
    user_id: str
    twin_type: str = "Partial"

class ZKPAuthRequest(BaseModel):
    proof: str
    statement: str

@router.post("/quantum-keys")
async def generate_quantum_keys():
    """
    Generates a post-quantum public/private keypair using CRYSTALS-Kyber.
    In a real implementation, the private key is never returned over the network,
    but we return it here for demonstration purposes.
    """
    pub_key, priv_key = quantum_crypto.generate_keypair()
    return {
        "status": "success",
        "public_key_hex": pub_key.hex(),
        "message": "Quantum-resistant keys generated. Use public key for encapsulation."
    }

@router.post("/digital-twin")
async def create_digital_twin(request: TwinRequest):
    """
    Creates a new Digital Twin session to protect the user's real identity.
    """
    try:
        twin_id = digital_twin_manager.create_twin_session(request.user_id, request.twin_type)
        return {
            "status": "success",
            "digital_twin_id": twin_id,
            "type": request.twin_type,
            "expires_in_seconds": digital_twin_manager.rotation_interval
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/zkp-verify")
async def verify_zero_knowledge_proof(request: ZKPAuthRequest):
    """
    Verifies a Zero-Knowledge Proof (ZKP) for passwordless authentication.
    """
    is_valid = ZeroKnowledgeProof.verify_proof(request.proof, request.statement)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Zero-Knowledge Proof.",
        )
    return {"status": "success", "message": "ZKP verified. Identity confirmed without revealing secrets."}

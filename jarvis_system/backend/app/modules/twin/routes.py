from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.twin.schemas import RotateIdentityRequest, RotateIdentityResponse
from app.modules.twin import services

router = APIRouter()

@router.post("/rotate-identity", response_model=RotateIdentityResponse)
async def rotate_identity(req: RotateIdentityRequest, db: AsyncSession = Depends(get_db)):
    """Rotate the Digital Twin identity layer (Test, Partial, Real) securely."""
    try:
        return await services.rotate_identity_layer(db, req)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

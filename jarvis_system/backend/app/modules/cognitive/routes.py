from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.cognitive.schemas import SynthesizeRequest, SynthesizeResponse
from app.modules.cognitive import services

router = APIRouter()

@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_ideas(req: SynthesizeRequest, db: AsyncSession = Depends(get_db)):
    """Deep context reasoning: Generate novel ideas by traversing the Memory Palace."""
    return await services.synthesize_concepts(db, req)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.modules.study.schemas import NoteCreate, NoteResponse
from app.modules.study import services
from app.core.jailbreak_protection import verify_prompt_safety

router = APIRouter()

@router.post("/notes", response_model=NoteResponse)
async def create_note(
    note: NoteCreate, 
    db: AsyncSession = Depends(get_db),
    _safe: str = Depends(verify_prompt_safety) # Middleware ensures no adversarial text
):
    """Create a new study note with Zero-Knowledge encryption."""
    return await services.create_secure_note(db, note)

@router.get("/notes", response_model=List[NoteResponse])
async def read_notes(db: AsyncSession = Depends(get_db)):
    """Retrieve all study notes, decrypted on the fly."""
    return await services.get_secure_notes(db)

@router.post("/notes/{note_id}/summarize")
async def summarize_note(note_id: int, db: AsyncSession = Depends(get_db)):
    """Auto-summarize a note using the AI engine."""
    summary = await services.auto_summarize_note(db, note_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"summary": summary}

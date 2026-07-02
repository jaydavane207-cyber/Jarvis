from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.modules.study.models import Note, Flashcard
from app.modules.study.schemas import NoteCreate, NoteResponse
from app.core.zero_knowledge import zk_core
import asyncio

async def create_secure_note(db: AsyncSession, note: NoteCreate) -> NoteResponse:
    # Encrypt the content before saving to the database
    encrypted_content = zk_core.encrypt_payload({"text": note.content})
    
    db_note = Note(title=note.title, encrypted_content=encrypted_content)
    db.add(db_note)
    await db.commit()
    await db.refresh(db_note)
    
    return NoteResponse(
        id=db_note.id,
        title=db_note.title,
        content=note.content, # Return decrypted to the client
        created_at=db_note.created_at
    )

async def get_secure_notes(db: AsyncSession):
    result = await db.execute(select(Note))
    notes = result.scalars().all()
    
    response = []
    for n in notes:
        decrypted_payload = zk_core.decrypt_payload(n.encrypted_content)
        response.append(NoteResponse(
            id=n.id,
            title=n.title,
            content=decrypted_payload.get("text", ""),
            created_at=n.created_at
        ))
    return response

async def generate_mock_summary(content: str) -> str:
    """
    Simulates calling an LLM (e.g., Llama 3) to summarize the content.
    """
    await asyncio.sleep(1) # Simulate network latency
    return f"AI Summary: The provided text discusses '{content[:20]}...' and focuses on key concepts."

async def auto_summarize_note(db: AsyncSession, note_id: int):
    result = await db.execute(select(Note).where(Note.id == note_id))
    db_note = result.scalar_one_or_none()
    
    if not db_note:
        return None
        
    decrypted_content = zk_core.decrypt_payload(db_note.encrypted_content).get("text", "")
    summary = await generate_mock_summary(decrypted_content)
    
    return summary

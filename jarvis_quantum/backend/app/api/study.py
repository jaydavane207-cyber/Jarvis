from fastapi import APIRouter
from app.models.ai_engine import ai_core
from app.models.study_models import Note, Flashcard, RAGQuery, StudyPlannerRequest
import uuid
from typing import List
from datetime import datetime, timedelta

router = APIRouter(prefix="/study", tags=["study"])

# Simulated Databases
notes_db: List[Note] = []
flashcards_db: List[Flashcard] = []

from pydantic import BaseModel

class AddNoteRequest(BaseModel):
    content: str
    tags: List[str] = []

@router.post("/notes")
async def add_note(req: AddNoteRequest):
    note = Note(id=str(uuid.uuid4()), content=req.content, tags=req.tags)
    notes_db.append(note)
    # Auto-summarization feature
    summary = ai_core.summarize_content(req.content)
    return {"message": "Note added and auto-summarized.", "note_id": note.id, "summary": summary}

@router.post("/rag-tutor")
async def ask_rag_tutor(query: RAGQuery):
    # Simulated RAG: Filter notes by context_tags
    context = ""
    if query.context_tags:
        relevant = [n.content for n in notes_db if any(tag in n.tags for tag in query.context_tags)]
        context = " ".join(relevant)
    
    # Send to AI Engine Tutor
    answer = ai_core.ask_tutor("RAG Search", f"Context: {context[:500]}... Question: {query.question}")
    return {"question": query.question, "answer": answer}

@router.post("/flashcards/generate")
async def generate_flashcards_from_note(note_id: str):
    note = next((n for n in notes_db if n.id == note_id), None)
    if not note:
        return {"error": "Note not found"}
    
    # Simulated AI flashcard generation
    new_card = Flashcard(id=str(uuid.uuid4()), front=f"Summarize: {note.content[:20]}...", back=note.content)
    flashcards_db.append(new_card)
    return {"message": "Flashcards generated via Spaced Repetition logic.", "card_id": new_card.id}

@router.post("/flashcards/review")
async def review_flashcard(card_id: str, quality: int):
    """
    SuperMemo-2 Spaced Repetition Algorithm Simulation
    quality: 0-5 (0 = complete blackout, 5 = perfect response)
    """
    card = next((c for c in flashcards_db if c.id == card_id), None)
    if not card:
        return {"error": "Card not found"}
    
    if quality >= 3:
        if card.repetitions == 0:
            card.interval = 1
        elif card.repetitions == 1:
            card.interval = 6
        else:
            card.interval = int(card.interval * card.ease_factor)
        card.repetitions += 1
    else:
        card.repetitions = 0
        card.interval = 1

    card.ease_factor = max(1.3, card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    card.next_review = datetime.now() + timedelta(days=card.interval)
    
    return {"message": "Spaced repetition updated", "next_review": card.next_review}

@router.post("/planner")
async def create_study_planner(req: StudyPlannerRequest):
    # Adjust study block times based on bio-energy levels (1-100)
    block_duration = 25 if req.current_energy_level < 40 else 50 # Pomodoro logic
    
    schedule = []
    current_time = datetime.now()
    for topic in req.topics:
        schedule.append({"topic": topic, "start": current_time, "duration_minutes": block_duration})
        current_time += timedelta(minutes=block_duration + 5) # 5 min break
        
    return {"exam_date": req.exam_date, "suggested_schedule": schedule}


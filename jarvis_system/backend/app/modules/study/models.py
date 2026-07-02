from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.core.database import Base

class Note(Base):
    __tablename__ = "study_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    encrypted_content = Column(Text, nullable=False) # Zero-Knowledge encrypted content
    created_at = Column(DateTime, default=datetime.utcnow)

class Flashcard(Base):
    __tablename__ = "study_flashcards"
    
    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, index=True)
    encrypted_front = Column(Text, nullable=False)
    encrypted_back = Column(Text, nullable=False)
    next_review = Column(DateTime, default=datetime.utcnow)

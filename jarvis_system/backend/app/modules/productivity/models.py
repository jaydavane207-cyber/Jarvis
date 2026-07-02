from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from app.core.database import Base

class Task(Base):
    __tablename__ = "productivity_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True) # Could be encrypted, but let's assume standard for now
    due_date = Column(DateTime, nullable=True)
    is_urgent = Column(Boolean, default=False)
    is_important = Column(Boolean, default=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "productivity_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    encrypted_blob = Column(Text, nullable=False) # Zero-Knowledge document storage
    created_at = Column(DateTime, default=datetime.utcnow)

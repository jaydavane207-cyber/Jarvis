from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime
from app.core.database import Base

class Contact(Base):
    __tablename__ = "communication_contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    encrypted_details = Column(Text, nullable=False) # Zero-Knowledge phone, email, notes
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatLog(Base):
    __tablename__ = "communication_chatlogs"
    
    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("communication_contacts.id"), nullable=True)
    encrypted_message = Column(Text, nullable=False) # Zero-Knowledge message content
    direction = Column(String) # "inbound" or "outbound"
    timestamp = Column(DateTime, default=datetime.utcnow)

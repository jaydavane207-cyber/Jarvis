from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.core.database import Base

class IdentityRotationLog(Base):
    """Tracks dynamic rotation of the digital twin identities."""
    __tablename__ = "twin_rotation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    previous_layer = Column(String) # test, partial, real
    new_layer = Column(String)
    trigger_event = Column(String) # The event that triggered the rotation
    encrypted_biometric_hash = Column(Text, nullable=True) # ZK representation of the biometric lock used
    rotated_at = Column(DateTime, default=datetime.utcnow)

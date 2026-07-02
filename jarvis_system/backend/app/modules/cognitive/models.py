from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float
from app.core.database import Base

class MemoryNode(Base):
    """Represents a discrete concept, fact, or memory within the Memory Palace."""
    __tablename__ = "cognitive_memory_nodes"
    
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, index=True) # e.g., 'fact', 'person', 'concept'
    encrypted_data = Column(Text, nullable=False) # Zero-Knowledge encrypted semantic data
    
class MemoryEdge(Base):
    """Represents a relationship between two MemoryNodes."""
    __tablename__ = "cognitive_memory_edges"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("cognitive_memory_nodes.id"))
    target_id = Column(Integer, ForeignKey("cognitive_memory_nodes.id"))
    relationship_type = Column(String) # e.g., 'causes', 'relates_to', 'is_a'
    weight = Column(Float, default=1.0) # Strength of relationship

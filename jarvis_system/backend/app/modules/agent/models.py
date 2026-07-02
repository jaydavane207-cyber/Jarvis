from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Workflow(Base):
    __tablename__ = "agent_workflows"
    
    id = Column(Integer, primary_key=True, index=True)
    objective = Column(String, nullable=False)
    status = Column(String, default="pending") # pending, running, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    steps = relationship("TaskStep", back_populates="workflow")

class TaskStep(Base):
    __tablename__ = "agent_task_steps"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("agent_workflows.id"))
    action = Column(String, nullable=False) # The tool or integration to call
    parameters_encrypted = Column(Text, nullable=False) # Zero-Knowledge encrypted parameters
    status = Column(String, default="pending")
    result_encrypted = Column(Text, nullable=True)
    order_index = Column(Integer, default=0)
    
    workflow = relationship("Workflow", back_populates="steps")

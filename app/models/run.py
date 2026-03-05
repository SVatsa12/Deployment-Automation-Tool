from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.core.database import Base

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True)
    workflow_id = Column(Integer, nullable=False)

    status = Column(String, default="PENDING")
    current_step = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

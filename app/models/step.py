from abc import ABC, abstractmethod
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.core.database import Base


class StepRun(Base):
    __tablename__ = "step_runs"

    id = Column(Integer, primary_key=True)
    workflow_run_id = Column(Integer, nullable=False)
    step_name = Column(String, nullable=False)
    
    status = Column(String, default="PENDING")
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class StepResult:
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class BaseStep(ABC):
    """
    Base class for all workflow steps.
    """

    name: str = "base_step"
    max_retries: int = 0
    requires_approval: bool = False

    def __init__(self):
        self.retry_count = 0

    @abstractmethod
    def execute(self) -> str:
        """
        Execute the step logic.
        Must return one of StepResult values.
        """
        pass

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def on_failure(self, error: Optional[Exception] = None):
        """
        Hook called when step fails.
        Can be overridden by subclasses.
        """
        pass

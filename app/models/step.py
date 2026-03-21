"""
Step model, result enum, and base step class for the workflow engine.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


# ---------------------------------------------------------------------------
# FIX 1: timezone-aware utcnow helper (replaces deprecated datetime.utcnow)
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# FIX 4: StepResult as a proper Enum
# Prevents silent typos, enables IDE autocompletion, and works with isinstance
# ---------------------------------------------------------------------------

class StepResult(str, Enum):
    """
    Possible return values from BaseStep.execute().

    Inherits from str so existing comparisons like
    `result == "SUCCESS"` and `result == StepResult.SUCCESS` both work,
    making this a non-breaking change.
    """
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


# ---------------------------------------------------------------------------
# Allowed StepRun status values (application-layer guard)
# ---------------------------------------------------------------------------

VALID_STEP_STATUSES = {"PENDING", "RUNNING", "SUCCESS", "FAILED"}


# ---------------------------------------------------------------------------
# StepRun ORM model
# ---------------------------------------------------------------------------

class StepRun(Base):
    __tablename__ = "step_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FIX 2: Proper ForeignKey so DB enforces referential integrity.
    # ondelete="CASCADE" mirrors the relationship cascade in WorkflowRun.
    workflow_run_id = Column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,   # FIX 5: index for fast per-run step lookups
    )

    # FIX 5: explicit length + index — queried by name in engine.py
    step_name = Column(String(128), nullable=False, index=True)

    # FIX 1 & explicit lengths for cross-DB compatibility
    status = Column(String(32), default="PENDING", nullable=False)
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # FIX 1: timezone-aware timestamps via _utcnow callable
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # FIX 3: relationship completing the back_populates="steps" in WorkflowRun
    workflow_run = relationship(
        "WorkflowRun",
        back_populates="steps",
        lazy="select",
    )

    # FIX 5: Composite index — engine.py always filters by (workflow_run_id, step_name)
    __table_args__ = (
        Index("ix_step_runs_run_name", "workflow_run_id", "step_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<StepRun id={self.id} run={self.workflow_run_id} "
            f"step={self.step_name!r} status={self.status}>"
        )

    def set_status(self, status: str) -> None:
        """Set status with validation. Raises ValueError for unknown values."""
        if status not in VALID_STEP_STATUSES:
            raise ValueError(
                f"Invalid StepRun status '{status}'. "
                f"Must be one of: {', '.join(sorted(VALID_STEP_STATUSES))}"
            )
        self.status = status


# ---------------------------------------------------------------------------
# BaseStep — base class for all workflow step implementations
# ---------------------------------------------------------------------------

class BaseStep(ABC):
    """
    Abstract base class for all workflow steps.

    Subclasses must implement execute() and return a StepResult value.
    """

    name: str = "base_step"
    max_retries: int = 0
    requires_approval: bool = False

    def __init__(self) -> None:
        self.retry_count: int = 0
        # FIX 6: output initialised to None so engine.py's getattr(step, "output", None)
        # always finds the attribute rather than relying on it being set in execute().
        # Subclasses should update self.output with meaningful progress messages.
        self.output: Optional[str] = None

    @abstractmethod
    def execute(self) -> StepResult:
        """
        Execute the step logic.
        Must return a StepResult enum value.
        Should update self.output with a human-readable result message.
        """
        pass

    def can_retry(self) -> bool:
        """Return True if this step has retries remaining."""
        return self.retry_count < self.max_retries

    def on_failure(self, error: Optional[Exception] = None) -> None:
        """
        Hook called when the step fails after all retries are exhausted.
        Override in subclasses for custom failure handling
        (e.g. notifications, cleanup).
        """
        pass
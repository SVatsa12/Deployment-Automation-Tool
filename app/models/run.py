"""
WorkflowRun model — represents a single execution of a Workflow.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime,
    ForeignKey, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base


# FIX 4: Allowed status values — enforced at the application layer.
# SQLite does not support CHECK constraints reliably, so we validate 
VALID_RUN_STATUSES = {
    "PENDING",
    "RUNNING",
    "SUCCESS",
    "FAILED",
    "WAITING_APPROVAL",
    "REJECTED",
}


def _utcnow() -> datetime:
    """
    FIX 1: datetime.utcnow() is deprecated in Python 3.12+.
    Use timezone-aware datetime.now(timezone.utc) instead.
    Wrapped in a function so SQLAlchemy calls it fresh each time
    (passing datetime.now as a callable, not a fixed value).
    """
    return datetime.now(timezone.utc)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FIX 2: Proper ForeignKey linking to the workflows table so the DB
    # enforces referential integrity (pairs with PRAGMA foreign_keys=ON
    # set in database.py for SQLite).
    workflow_id = Column(
        Integer,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,   # FIX 5: index for fast join/filter queries
    )

    # FIX 4: String(32) — explicit length works across SQLite, Postgres, MySQL.
    # Keeps status values bounded; avoids unbounded TEXT columns on MySQL.
    status = Column(String(32), default="PENDING", nullable=False)
    current_step = Column(String(128), nullable=True)
    deployment_url = Column(String(2048), nullable=True)  # Store generated URL

    # FIX 1: timezone-aware utcnow via callable (not datetime.utcnow directly)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # FIX 3: Relationships for convenient ORM access
    # e.g. run.workflow  /  run.steps
    workflow = relationship(
        "Workflow",
        back_populates="runs",
        lazy="select",
    )
    steps = relationship(
        "StepRun",
        back_populates="workflow_run",
        cascade="all, delete-orphan",  # deleting a run deletes its steps
        lazy="select",
        order_by="StepRun.created_at",
    )
    short_link = relationship(
        "ShortLink",
        back_populates="workflow_run",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # FIX 5: Composite index on (workflow_id, status) — the most common
    # query pattern in routes.py is filtering runs by workflow + status.
    __table_args__ = (
        Index("ix_workflow_runs_workflow_status", "workflow_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowRun id={self.id} workflow_id={self.workflow_id} "
            f"status={self.status} step={self.current_step}>"
        )

    # FIX 4: Application-layer status validation
    def set_status(self, status: str) -> None:
        """Set status with validation. Raises ValueError for unknown values."""
        if status not in VALID_RUN_STATUSES:
            raise ValueError(
                f"Invalid WorkflowRun status '{status}'. "
                f"Must be one of: {', '.join(sorted(VALID_RUN_STATUSES))}"
            )
        self.status = status
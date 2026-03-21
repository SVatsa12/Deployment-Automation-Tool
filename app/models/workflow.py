"""
Workflow model — represents a reusable workflow definition.
Each execution of a Workflow produces a WorkflowRun.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


# ---------------------------------------------------------------------------
# FIX 1: timezone-aware utcnow helper (consistent with run.py and step.py)
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Valid workflow types — application-layer guard
# ---------------------------------------------------------------------------

VALID_WORKFLOW_TYPES = {"demo", "deployment"}


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FIX 3: unique=True prevents duplicate workflow names from concurrent requests.
    # FIX 4: index=True (implied by unique) speeds up the filter(name==...) lookup.
    # FIX 5: explicit String lengths for cross-DB compatibility.
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(String(512), nullable=True)

    # FIX 4 & 5: index on workflow_type — filtered in routes.py
    workflow_type = Column(String(64), default="demo", nullable=False, index=True)

    # FIX 1: timestamps — consistent with WorkflowRun and StepRun
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    # FIX 2: relationship completing back_populates="workflow" in WorkflowRun
    runs = relationship(
        "WorkflowRun",
        back_populates="workflow",
        cascade="all, delete-orphan",  # deleting a Workflow removes all its runs
        lazy="select",
        order_by="WorkflowRun.created_at.desc()",
    )

    __table_args__ = (
        # FIX 3: DB-level unique constraint as a safety net on top of unique=True
        # (belt-and-suspenders for concurrent inserts that race past app-layer checks)
        UniqueConstraint("name", name="uq_workflows_name"),
        # FIX 4: composite index for the common (name, workflow_type) filter pattern
        Index("ix_workflows_type_name", "workflow_type", "name"),
    )

    def __repr__(self) -> str:
        return (
            f"<Workflow id={self.id} name={self.name!r} "
            f"type={self.workflow_type} runs={len(self.runs) if self.runs else 0}>"
        )

    def set_workflow_type(self, workflow_type: str) -> None:
        """Set workflow_type with validation. Raises ValueError for unknown types."""
        if workflow_type not in VALID_WORKFLOW_TYPES:
            raise ValueError(
                f"Invalid workflow_type '{workflow_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_WORKFLOW_TYPES))}"
            )
        self.workflow_type = workflow_type
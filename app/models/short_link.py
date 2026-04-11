"""
Short links for deployment URLs — maps a short code to the long platform URL.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ShortLink(Base):
    __tablename__ = "short_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(12), unique=True, nullable=False, index=True)
    target_url = Column(String(2048), nullable=False)
    workflow_run_id = Column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    workflow_run = relationship("WorkflowRun", back_populates="short_link")

    __table_args__ = (Index("ix_short_links_code", "code"),)

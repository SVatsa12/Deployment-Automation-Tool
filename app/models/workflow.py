from sqlalchemy import Column, Integer, String
from app.core.database import Base

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    workflow_type = Column(String, default="demo")

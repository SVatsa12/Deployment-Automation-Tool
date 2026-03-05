from app.core.database import engine, Base
from app.models.workflow import Workflow
from app.models.run import WorkflowRun
from app.models.step import StepRun

def init_db():
    Base.metadata.create_all(bind=engine)

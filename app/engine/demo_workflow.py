from app.engine.engine import run_workflow
from app.engine.sample_steps import (
    BuildStep,
    TestStep,
    ApprovalStep,
    DeployStep
)
from app.models.run import WorkflowRun
from app.core.database import SessionLocal


def run_demo_workflow():
    db = SessionLocal()

    try:
        workflow_run = WorkflowRun(
            workflow_id=1,
            status="PENDING"
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)

        steps = [
            BuildStep(),
            TestStep(),
            ApprovalStep(),
            DeployStep()
        ]

        run_workflow(workflow_run, steps, db)

    finally:
        db.close()

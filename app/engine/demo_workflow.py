"""
Demo workflow runner — creates a sample workflow and executes all steps.
Run directly with:  python -m app.engine.demo_workflow
"""
import logging

from app.core.database import SessionLocal
from app.engine.engine import run_workflow
from app.engine.sample_steps import BuildStep, TestStep, ApprovalStep, DeployStep
from app.models.workflow import Workflow
from app.models.run import WorkflowRun

logger = logging.getLogger(__name__)


def run_demo_workflow() -> None:
    """
    Create a demo Workflow + WorkflowRun and execute all four sample steps.

    FIX 1: A Workflow record is looked up (or created) before WorkflowRun so
            the foreign key constraint is never violated.
    FIX 2: workflow_id is derived from the DB, not hardcoded to 1.
    FIX 3: try/except around run_workflow marks the run FAILED and logs the
            error instead of leaving it stuck in PENDING forever.
    FIX 4: Guarded by __main__ so importing this module is side-effect free.
    """
    db = SessionLocal()

    workflow_run = None  # Initialise before try so except can reference it safely

    try:
        # FIX 1 & 2: Ensure a Workflow record exists before creating the run
        workflow = (
            db.query(Workflow)
            .filter(Workflow.name == "Demo Workflow")
            .first()
        )
        if not workflow:
            workflow = Workflow(
                name="Demo Workflow",
                description="Sample workflow for local testing",
                workflow_type="demo",
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            logger.info("Created demo Workflow (id=%d)", workflow.id)
        else:
            logger.info("Using existing demo Workflow (id=%d)", workflow.id)

        # Create a fresh WorkflowRun linked to the real workflow id
        workflow_run = WorkflowRun(
            workflow_id=workflow.id,   # FIX 2: dynamic, not hardcoded
            status="PENDING",
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)
        logger.info("Created WorkflowRun (id=%d)", workflow_run.id)

        steps = [
            BuildStep(),
            TestStep(),
            ApprovalStep(),
            DeployStep(),
        ]

        # FIX 3: Catch run_workflow errors and mark the run as FAILED
        run_workflow(workflow_run, steps, db)
        logger.info(
            "Demo workflow finished with status: %s", workflow_run.status
        )

    except Exception as e:
        logger.error("Demo workflow failed: %s", str(e), exc_info=True)
        if workflow_run is not None:
            workflow_run.status = "FAILED"
            db.commit()

    finally:
        db.close()


# FIX 4: Entry-point guard — importing this module is now side-effect free
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_demo_workflow()
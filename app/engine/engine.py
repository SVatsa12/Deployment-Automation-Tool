from typing import List
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.run import WorkflowRun
from app.models.step import StepRun
from app.models.step import BaseStep, StepResult


def get_or_create_step_run(
    db: Session,
    workflow_run_id: int,
    step: BaseStep
) -> StepRun:
    """
    Ensures a StepRun exists for a given workflow run + step.
    This guarantees idempotency.
    """
    step_run = (
        db.query(StepRun)
        .filter(
            StepRun.workflow_run_id == workflow_run_id,
            StepRun.step_name == step.name
        )
        .first()
    )

    if not step_run:
        step_run = StepRun(
            workflow_run_id=workflow_run_id,
            step_name=step.name,
            status="PENDING",
            retry_count=0
        )
        db.add(step_run)
        db.commit()
        db.refresh(step_run)

    return step_run


def run_workflow(
    workflow_run: WorkflowRun,
    steps: List[BaseStep],
    db: Session = None
):
    """
    Core workflow engine loop.
    Executes steps sequentially with:
    - Resume logic
    - Step-level retries
    - Manual approval pause
    - Safe failure handling
    """

    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        # Mark workflow as running
        workflow_run.status = "RUNNING"
        db.commit()

        for step in steps:
            step_run = get_or_create_step_run(db, workflow_run.id, step)

            # 🔁 Resume logic: skip completed steps
            if step_run.status == "SUCCESS":
                continue

            # Update current step
            workflow_run.current_step = step.name
            step_run.status = "RUNNING"
            db.commit()

            try:
                result = step.execute()

                # ✅ Step succeeded
                if result == StepResult.SUCCESS:
                    step_run.status = "SUCCESS"
                    db.commit()

                # ⏸ Manual approval required
                elif result == StepResult.WAITING_APPROVAL:
                    workflow_run.status = "WAITING_APPROVAL"
                    db.commit()
                    return  # Pause execution

                # ❌ Explicit failure
                else:
                    raise Exception("Step execution failed")

            except Exception as e:
                # Failure handling
                step.retry_count += 1
                step_run.retry_count += 1
                step_run.status = "FAILED"
                step.on_failure(e)
                db.commit()

                # 🔁 Retry only this step if allowed
                if step.can_retry():
                    step_run.status = "PENDING"
                    db.commit()
                    return run_workflow(workflow_run, steps, db)

                # ⛔ No retries left → workflow fails
                workflow_run.status = "FAILED"
                db.commit()
                return

        # 🎉 All steps completed successfully
        workflow_run.status = "SUCCESS"
        workflow_run.current_step = None
        db.commit()

    finally:
        if close_db:
            db.close()

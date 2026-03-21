"""
Core workflow engine — executes steps sequentially with retry, resume,
approval-pause, and post-step hook support.
"""
import logging
from typing import List, Optional, Callable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.run import WorkflowRun
from app.models.step import StepRun, BaseStep, StepResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def get_or_create_step_run(
    db: Session,
    workflow_run_id: int,
    step: BaseStep,
) -> StepRun:
    """
    Return the existing StepRun for this step, or create a PENDING one.
    Guarantees idempotency so resume logic works correctly.
    """
    step_run = (
        db.query(StepRun)
        .filter(
            StepRun.workflow_run_id == workflow_run_id,
            StepRun.step_name == step.name,
        )
        .first()
    )

    if not step_run:
        step_run = StepRun(
            workflow_run_id=workflow_run_id,
            step_name=step.name,
            status="PENDING",
            retry_count=0,
        )
        db.add(step_run)
        db.commit()
        db.refresh(step_run)

    return step_run


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def run_workflow(
    workflow_run: WorkflowRun,
    steps: List[BaseStep],
    db: Optional[Session] = None,
    post_step_hook: Optional[Callable[[BaseStep], None]] = None,
) -> None:
    """
    Execute workflow steps sequentially.

    Features
    --------
    - Resume:          skips steps already in SUCCESS state.
    - Retries:         retries a failed step in-place (iterative, not recursive).
    - Approval pause:  pauses execution and sets workflow to WAITING_APPROVAL.
    - post_step_hook:  optional callable invoked after each successful step,
                       receives the completed BaseStep instance.  Used by
                       routes.py to wire clone_dir into the deploy step before
                       it runs.  (FIX 2)

    Parameters
    ----------
    workflow_run    : The WorkflowRun ORM object (must already be persisted).
    steps           : Ordered list of BaseStep instances to execute.
    db              : SQLAlchemy session.  A new one is created if None.
    post_step_hook  : Optional callback(step) called after each SUCCESS step.

    Fixes applied
    -------------
    FIX 1: Retry is now iterative (inner loop) — no recursion, no stack growth.
    FIX 2: post_step_hook parameter added for inter-step context passing.
    FIX 3: close_db initialised before try so finally never hits UnboundLocalError.
    FIX 4: Retry loop re-executes the step directly instead of re-entering
           run_workflow.
    FIX 5: Only step_run.retry_count is the source of truth; step.retry_count
           is kept in sync from step_run to avoid drift.
    FIX 6: Final SUCCESS commit is wrapped in its own try/except so a commit
           failure is logged clearly rather than silently swallowed.
    """
    # FIX 3: initialise before try block
    close_db = False

    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Mark workflow as running
        workflow_run.status = "RUNNING"
        db.commit()

        for step in steps:
            step_run = get_or_create_step_run(db, workflow_run.id, step)

            # Resume logic: skip steps that already succeeded
            if step_run.status == "SUCCESS":
                logger.debug("Skipping completed step: %s", step.name)
                continue

            # Sync retry count from DB → step object (FIX 5)
            step.retry_count = step_run.retry_count

            # Update current step marker
            workflow_run.current_step = step.name
            step_run.status = "RUNNING"
            db.commit()

            # ------------------------------------------------------------------
            # FIX 1 & 4: Iterative retry loop — no recursion
            # ------------------------------------------------------------------
            step_succeeded = False

            while True:
                try:
                    result = step.execute()
                    step_output = getattr(step, "output", None)

                    if result == StepResult.SUCCESS:
                        # Mark step succeeded
                        step_run.status = "SUCCESS"
                        step_run.result = step_output
                        step_run.error_message = None
                        db.commit()
                        step_succeeded = True

                        # FIX 2: Notify caller that this step finished
                        if post_step_hook is not None:
                            try:
                                post_step_hook(step)
                            except Exception as hook_err:
                                logger.warning(
                                    "post_step_hook raised for step '%s': %s",
                                    step.name, hook_err,
                                )
                        break  # Move to next step

                    elif result == StepResult.WAITING_APPROVAL:
                        step_run.status = "PENDING"
                        step_run.result = step_output
                        workflow_run.status = "WAITING_APPROVAL"
                        db.commit()
                        logger.info("Workflow paused at step '%s' — awaiting approval.", step.name)
                        return  # Pause execution; caller resumes later

                    else:
                        # Treat any other result as failure
                        raise Exception(step_output or "Step returned a failure result")

                except Exception as exc:
                    # FIX 5: step_run is the single source of truth for retry_count
                    step_run.retry_count += 1
                    step.retry_count = step_run.retry_count  # keep in sync
                    step_run.status = "FAILED"
                    step_run.result = getattr(step, "output", None)
                    step_run.error_message = str(exc)
                    db.commit()

                    logger.warning(
                        "Step '%s' failed (attempt %d/%d): %s",
                        step.name,
                        step_run.retry_count,
                        step.max_retries + 1,
                        exc,
                    )

                    try:
                        step.on_failure(exc)
                    except Exception as on_fail_err:
                        logger.warning("on_failure hook raised: %s", on_fail_err)

                    if step.can_retry():
                        # FIX 4: reset to RUNNING and retry in-place
                        step_run.status = "RUNNING"
                        db.commit()
                        logger.info("Retrying step '%s' (attempt %d)…", step.name, step_run.retry_count + 1)
                        continue  # retry the while loop

                    # No retries left
                    workflow_run.status = "FAILED"
                    workflow_run.current_step = step.name
                    db.commit()
                    logger.error(
                        "Step '%s' exhausted all retries. Workflow %d marked FAILED.",
                        step.name, workflow_run.id,
                    )
                    return

            if not step_succeeded:
                # Safety net: should not be reachable, but guards against
                # future logic changes that might skip the break/return above.
                logger.error("Step '%s' exited retry loop without succeeding.", step.name)
                workflow_run.status = "FAILED"
                db.commit()
                return

        # ------------------------------------------------------------------
        # FIX 6: Final SUCCESS commit in its own try/except
        # ------------------------------------------------------------------
        try:
            workflow_run.status = "SUCCESS"
            workflow_run.current_step = None
            db.commit()
            logger.info("Workflow %d completed successfully.", workflow_run.id)
        except Exception as commit_err:
            logger.error(
                "Workflow %d finished all steps but final commit failed: %s",
                workflow_run.id, commit_err,
            )
            raise

    finally:
        if close_db:
            db.close()
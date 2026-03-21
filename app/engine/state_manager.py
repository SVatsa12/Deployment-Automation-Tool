"""
State Manager — centralises all workflow and step state transitions.

Instead of setting .status = "FAILED" scattered across routes.py, engine.py,
and demo_workflow.py, all state changes go through this module so:
- Invalid transitions are caught early
- Every change is logged
- DB commits are handled consistently in one place
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.run import WorkflowRun, VALID_RUN_STATUSES
from app.models.step import StepRun, VALID_STEP_STATUSES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowed state transition maps
# Prevents illegal transitions like SUCCESS -> RUNNING
# ---------------------------------------------------------------------------

# workflow_run transitions: current_status -> set of allowed next statuses
WORKFLOW_TRANSITIONS = {
    "PENDING":          {"RUNNING", "FAILED"},
    "RUNNING":          {"SUCCESS", "FAILED", "WAITING_APPROVAL"},
    "WAITING_APPROVAL": {"RUNNING", "REJECTED", "FAILED"},
    "SUCCESS":          set(),   # terminal
    "FAILED":           {"RUNNING"},  # allow resume/retry
    "REJECTED":         set(),   # terminal
}

# step_run transitions
STEP_TRANSITIONS = {
    "PENDING":  {"RUNNING", "FAILED"},
    "RUNNING":  {"SUCCESS", "FAILED"},
    "SUCCESS":  set(),   # terminal
    "FAILED":   {"RUNNING"},  # allow retry
}


# ---------------------------------------------------------------------------
# WorkflowRun state management
# ---------------------------------------------------------------------------

class WorkflowStateManager:
    """Manages state transitions for WorkflowRun objects."""

    @staticmethod
    def transition(
        workflow_run: WorkflowRun,
        new_status: str,
        db: Session,
        current_step: Optional[str] = None,
        commit: bool = True,
    ) -> bool:
        """
        Transition a WorkflowRun to a new status.

        Parameters
        ----------
        workflow_run : WorkflowRun ORM object to update
        new_status   : Target status string
        db           : Active SQLAlchemy session
        current_step : Optional step name to set as current_step
        commit       : Whether to commit immediately (default True)

        Returns
        -------
        True if transition succeeded, False if it was blocked.
        """
        if new_status not in VALID_RUN_STATUSES:
            logger.error(
                "WorkflowRun %d: invalid target status '%s'",
                workflow_run.id, new_status,
            )
            return False

        current = workflow_run.status
        allowed = WORKFLOW_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            logger.warning(
                "WorkflowRun %d: blocked transition %s -> %s (allowed: %s)",
                workflow_run.id, current, new_status,
                ", ".join(sorted(allowed)) or "none",
            )
            return False

        logger.info(
            "WorkflowRun %d: %s -> %s%s",
            workflow_run.id,
            current,
            new_status,
            f" (step: {current_step})" if current_step else "",
        )

        workflow_run.status = new_status
        if current_step is not None:
            workflow_run.current_step = current_step
        elif new_status in ("SUCCESS", "REJECTED", "FAILED"):
            # Clear current_step on terminal states
            workflow_run.current_step = None

        if commit:
            db.commit()

        return True

    @staticmethod
    def start(workflow_run: WorkflowRun, db: Session) -> bool:
        """Mark workflow as RUNNING."""
        return WorkflowStateManager.transition(workflow_run, "RUNNING", db)

    @staticmethod
    def succeed(workflow_run: WorkflowRun, db: Session) -> bool:
        """Mark workflow as SUCCESS."""
        return WorkflowStateManager.transition(workflow_run, "SUCCESS", db)

    @staticmethod
    def fail(workflow_run: WorkflowRun, db: Session) -> bool:
        """Mark workflow as FAILED."""
        return WorkflowStateManager.transition(workflow_run, "FAILED", db)

    @staticmethod
    def pause_for_approval(
        workflow_run: WorkflowRun,
        db: Session,
        current_step: Optional[str] = None,
    ) -> bool:
        """Mark workflow as WAITING_APPROVAL."""
        return WorkflowStateManager.transition(
            workflow_run, "WAITING_APPROVAL", db, current_step=current_step
        )

    @staticmethod
    def reject(workflow_run: WorkflowRun, db: Session) -> bool:
        """Mark workflow as REJECTED."""
        return WorkflowStateManager.transition(workflow_run, "REJECTED", db)

    @staticmethod
    def resume(workflow_run: WorkflowRun, db: Session) -> bool:
        """Resume a FAILED or WAITING_APPROVAL workflow back to RUNNING."""
        return WorkflowStateManager.transition(workflow_run, "RUNNING", db)


# ---------------------------------------------------------------------------
# StepRun state management
# ---------------------------------------------------------------------------

class StepStateManager:
    """Manages state transitions for StepRun objects."""

    @staticmethod
    def transition(
        step_run: StepRun,
        new_status: str,
        db: Session,
        result: Optional[str] = None,
        error_message: Optional[str] = None,
        commit: bool = True,
    ) -> bool:
        """
        Transition a StepRun to a new status.

        Parameters
        ----------
        step_run      : StepRun ORM object to update
        new_status    : Target status string
        db            : Active SQLAlchemy session
        result        : Optional result message to store
        error_message : Optional error detail (set on FAILED)
        commit        : Whether to commit immediately (default True)

        Returns
        -------
        True if transition succeeded, False if blocked.
        """
        if new_status not in VALID_STEP_STATUSES:
            logger.error(
                "StepRun %d (%s): invalid target status '%s'",
                step_run.id, step_run.step_name, new_status,
            )
            return False

        current = step_run.status
        allowed = STEP_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            logger.warning(
                "StepRun %d (%s): blocked transition %s -> %s (allowed: %s)",
                step_run.id, step_run.step_name, current, new_status,
                ", ".join(sorted(allowed)) or "none",
            )
            return False

        logger.debug(
            "StepRun %d (%s): %s -> %s",
            step_run.id, step_run.step_name, current, new_status,
        )

        step_run.status = new_status

        if result is not None:
            step_run.result = result
        if error_message is not None:
            step_run.error_message = error_message
        elif new_status == "SUCCESS":
            step_run.error_message = None  # clear error on success

        if commit:
            db.commit()

        return True

    @staticmethod
    def start(step_run: StepRun, db: Session) -> bool:
        """Mark step as RUNNING."""
        return StepStateManager.transition(step_run, "RUNNING", db)

    @staticmethod
    def succeed(step_run: StepRun, db: Session, result: Optional[str] = None) -> bool:
        """Mark step as SUCCESS with optional result message."""
        return StepStateManager.transition(step_run, "SUCCESS", db, result=result)

    @staticmethod
    def fail(
        step_run: StepRun,
        db: Session,
        error_message: Optional[str] = None,
        result: Optional[str] = None,
    ) -> bool:
        """Mark step as FAILED with optional error detail."""
        return StepStateManager.transition(
            step_run, "FAILED", db,
            result=result,
            error_message=error_message,
        )

    @staticmethod
    def retry(step_run: StepRun, db: Session) -> bool:
        """Reset a FAILED step back to RUNNING for retry."""
        step_run.retry_count += 1
        return StepStateManager.transition(step_run, "RUNNING", db)


# ---------------------------------------------------------------------------
# Convenience: get a human-readable workflow summary
# ---------------------------------------------------------------------------

def get_workflow_summary(workflow_run: WorkflowRun, db: Session) -> dict:
    """
    Return a concise summary of a workflow run and all its steps.
    Useful for logging and API responses.
    """
    steps = (
        db.query(StepRun)
        .filter(StepRun.workflow_run_id == workflow_run.id)
        .order_by(StepRun.created_at)
        .all()
    )

    return {
        "workflow_run_id": workflow_run.id,
        "status": workflow_run.status,
        "current_step": workflow_run.current_step,
        "created_at": workflow_run.created_at.isoformat() if workflow_run.created_at else None,
        "updated_at": workflow_run.updated_at.isoformat() if workflow_run.updated_at else None,
        "steps": [
            {
                "name": s.step_name,
                "status": s.status,
                "result": s.result,
                "error": s.error_message,
                "retries": s.retry_count,
            }
            for s in steps
        ],
    }
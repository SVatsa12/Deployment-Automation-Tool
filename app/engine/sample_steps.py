"""
Sample workflow steps for demonstration and testing purposes.

These steps simulate a build → test → approve → deploy pipeline.
They are intentionally simple — replace time.sleep() with real logic
when integrating into production workflows.
"""
import time
import logging
from app.models.step import BaseStep, StepResult

logger = logging.getLogger(__name__)


class BuildStep(BaseStep):
    name = "build"
    max_retries = 1

    def execute(self) -> StepResult:
        """
        Simulate a project build.

        FIX 1 & 4: self.output is set before returning so engine.py always has
                    a meaningful string to persist in the DB (both on success
                    and on any exception raised inside execute).
        FIX 3: sleep is documented as a simulation placeholder.
        """
        self.output = "Build started"
        logger.info("Building project...")
        print("Building project...")

        # NOTE: time.sleep() is a simulation placeholder.
        # In a real BuildStep, replace this with your actual build command,
        # e.g. subprocess.run(["npm", "run", "build"], ...).
        # Avoid sleep in production — it blocks the background-task thread.
        time.sleep(1)

        self.output = "Build completed successfully"
        logger.info(self.output)
        return StepResult.SUCCESS


class TestStep(BaseStep):
    name = "test"
    max_retries = 1

    def execute(self) -> StepResult:
        """
        Simulate running the test suite.

        FIX 1 & 4: self.output set throughout so the DB always has context.
        """
        self.output = "Tests started"
        logger.info("Running tests...")
        print("Running tests...")

        # NOTE: Replace with real test runner, e.g.:
        # subprocess.run(["pytest", "--tb=short"], check=True)
        time.sleep(1)

        self.output = "All tests passed"
        logger.info(self.output)
        return StepResult.SUCCESS


class ApprovalStep(BaseStep):
    name = "approval"
    max_retries = 0      # FIX 2: explicit 0 — approval should never auto-retry
    requires_approval = True

    def execute(self) -> StepResult:
        """
        Pause the workflow and wait for a human to approve via the API.

        FIX 1: self.output set so the DB records why the step is pending.
        FIX 2: max_retries=0 prevents the engine from retrying an approval
               step automatically, which would be incorrect behaviour.
        """
        self.output = "Waiting for manual approval via POST /api/workflows/runs/{id}/approve"
        logger.info("Workflow paused — awaiting manual approval.")
        print("Waiting for manual approval...")
        return StepResult.WAITING_APPROVAL


class DeployStep(BaseStep):
    name = "deploy"
    max_retries = 1

    def execute(self) -> StepResult:
        """
        Simulate deploying the application.

        FIX 1 & 4: self.output set throughout so the DB always has context.
        """
        self.output = "Deploy started"
        logger.info("Deploying application...")
        print("Deploying application...")

        # NOTE: Replace with real deploy logic, e.g. call platform_deployers.py
        time.sleep(1)

        mock_url = "https://demo-deploy-nova.vercel.app"
        self.output = f"Deployment completed successfully. URL: {mock_url}"
        logger.info(self.output)
        return StepResult.SUCCESS
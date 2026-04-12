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
        """Simulate a project build."""
        self.output = "Build started"
        logger.info("Building project...")
        time.sleep(1)
        self.output = "Build completed successfully"
        logger.info(self.output)
        return StepResult.SUCCESS


class TestStep(BaseStep):
    name = "test"
    max_retries = 1

    def execute(self) -> StepResult:
        """Simulate running the test suite."""
        self.output = "Tests started"
        logger.info("Running tests...")
        time.sleep(1)
        self.output = "All tests passed"
        logger.info(self.output)
        return StepResult.SUCCESS


class ApprovalStep(BaseStep):
    name = "approval"
    max_retries = 0
    requires_approval = True

    def execute(self) -> StepResult:
        """Pause the workflow and wait for a human to approve via the API."""
        self.output = "Waiting for manual approval"
        logger.info("Workflow paused — awaiting manual approval.")
        return StepResult.WAITING_APPROVAL


class DeployStep(BaseStep):
    name = "deploy"
    max_retries = 1

    def execute(self) -> StepResult:
        """
        Simulate deploying the application.
        This is a DEMO step — it does not deploy to any real platform.
        For real deployments, use the /api/deploy endpoint which triggers
        the deployment pipeline (GitClone → PlatformDeploy → Cleanup).
        """
        self.output = "Demo deploy started"
        logger.info("Simulating deployment...")
        time.sleep(1.5)

        self.output = (
            "Demo deployment simulation completed. "
            "This is a test workflow — no real deployment was made. "
            "Use 'Connect your repo' section to deploy to a real platform."
        )
        logger.info(self.output)
        return StepResult.SUCCESS
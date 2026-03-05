from app.models.step import BaseStep, StepResult
import time


class BuildStep(BaseStep):
    name = "build"
    max_retries = 1

    def execute(self) -> str:
        print("🔨 Building project...")
        time.sleep(1)
        return StepResult.SUCCESS


class TestStep(BaseStep):
    name = "test"
    max_retries = 1

    def execute(self) -> str:
        print("🧪 Running tests...")
        time.sleep(1)
        return StepResult.SUCCESS


class ApprovalStep(BaseStep):
    name = "approval"
    requires_approval = True

    def execute(self) -> str:
        print("⏸ Waiting for manual approval...")
        return StepResult.WAITING_APPROVAL


class DeployStep(BaseStep):
    name = "deploy"
    max_retries = 1

    def execute(self) -> str:
        print("🚀 Deploying application...")
        time.sleep(1)
        return StepResult.SUCCESS

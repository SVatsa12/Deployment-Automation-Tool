"""
Deployment Workflow Steps
Steps for automated GitHub repository deployment
"""
import os
import shutil
import subprocess
import tempfile
from typing import Dict, Any
from app.models.step import BaseStep, StepResult
from app.utils.platform_deployers import DeployerFactory


def _git_missing_remote_branch(stderr: str) -> bool:
    """True if git failed because the requested -b branch does not exist on the remote."""
    if not stderr:
        return False
    low = stderr.lower()
    return (
        "remote branch" in low
        and "not found" in low
    ) or "could not find remote branch" in low


def _read_checked_out_branch(clone_dir: str, git_env: dict) -> str | None:
    """Best-effort name of the branch checked out in clone_dir."""
    r = subprocess.run(
        ["git", "-C", clone_dir, "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=30,
        env=git_env,
    )
    name = (r.stdout or "").strip()
    return name or None


class GitCloneStep(BaseStep):
    """Clone GitHub repository to temporary directory"""
    
    name = "git_clone"
    max_retries = 1
    
    def __init__(self, github_url: str, branch: str = "main"):
        super().__init__()
        self.github_url = github_url
        self.branch = branch
        self.clone_dir = None
        self.resolved_branch: str | None = None
        self.output = ""
    
    def execute(self) -> StepResult:
        """Clone the repository"""
        try:
            git_env = os.environ.copy()
            git_env["GIT_TERMINAL_PROMPT"] = "0"
            git_env["GCM_INTERACTIVE"] = "Never"

            def run_clone(args: list[str]) -> subprocess.CompletedProcess:
                return subprocess.run(
                    ["git", "clone", *args, self.github_url, self.clone_dir],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=git_env,
                )

            self.clone_dir = tempfile.mkdtemp(prefix="deploy_")
            print(f"Cloning {self.github_url} (branch: {self.branch}) to {self.clone_dir}")

            # Shallow single-branch clone for the requested ref (fast).
            result = run_clone(
                [
                    "--depth", "1",
                    "--single-branch",
                    "--filter=blob:none",
                    "-b", self.branch,
                ]
            )

            if result.returncode != 0 and _git_missing_remote_branch(result.stderr or ""):
                print(
                    f"Branch {self.branch!r} missing on remote; "
                    "retrying clone using repository default branch."
                )
                shutil.rmtree(self.clone_dir, ignore_errors=True)
                self.clone_dir = tempfile.mkdtemp(prefix="deploy_")
                # No -b: checks out the remote's default branch (e.g. master vs main).
                result = run_clone(["--depth", "1", "--filter=blob:none"])

            if result.returncode != 0:
                self.output = f"Git clone failed: {result.stderr}"
                print(self.output)
                return StepResult.FAILED

            self.resolved_branch = _read_checked_out_branch(self.clone_dir, git_env) or self.branch
            if self.resolved_branch != self.branch:
                print(f"Checked out branch: {self.resolved_branch}")

            self.output = f"Successfully cloned to {self.clone_dir}"
            print(self.output)
            return StepResult.SUCCESS

        except subprocess.TimeoutExpired:
            self.output = "Git clone timeout after 5 minutes"
            print(self.output)
            return StepResult.FAILED
        except Exception as e:
            self.output = f"Git clone error: {str(e)}"
            print(self.output)
            return StepResult.FAILED


class PlatformDeployStep(BaseStep):
    """Deploy to selected platform"""
    
    name = "platform_deploy"
    max_retries = 2
    
    def __init__(self, platform_id: str, github_url: str, branch: str = "main", 
                 project_name: str = "my-app", clone_dir: str = None):
        super().__init__()
        self.platform_id = platform_id
        self.github_url = github_url
        self.branch = branch
        self.project_name = project_name
        self.clone_dir = clone_dir
        self.deployment_url = None
        self.output = ""
    
    def execute(self) -> StepResult:
        """Deploy to platform"""
        try:
            # Get deployer for platform
            deployer = DeployerFactory.get_deployer(self.platform_id)
            
            if not deployer:
                self.output = f"Platform '{self.platform_id}' not supported"
                print(self.output)
                return StepResult.FAILED
            
            print(f"Deploying to {self.platform_id}...")
            
            # Change to clone directory if available
            original_dir = os.getcwd()
            if self.clone_dir and os.path.exists(self.clone_dir):
                os.chdir(self.clone_dir)
            
            try:
                # Deploy to platform
                deployment_result = deployer.deploy(
                    github_url=self.github_url,
                    branch=self.branch,
                    project_name=self.project_name
                )
                
                if deployment_result.get("success"):
                    self.deployment_url = deployment_result.get("deployment_url")
                    msg = deployment_result.get("message", "Deployment successful")
                    if self.deployment_url:
                        self.output = f"{msg}. URL: {self.deployment_url}"
                    else:
                        self.output = msg
                    print(f"✓ {self.output}")
                    return StepResult.SUCCESS
                else:
                    self.output = f"Deployment failed: {deployment_result.get('error', 'Unknown error')}"
                    print(f"✗ {self.output}")
                    return StepResult.FAILED
                    
            finally:
                # Return to original directory
                os.chdir(original_dir)
                
        except Exception as e:
            self.output = f"Deployment error: {str(e)}"
            print(self.output)
            return StepResult.FAILED


class CleanupStep(BaseStep):
    """Clean up temporary files and directories"""
    
    name = "cleanup"
    max_retries = 0
    
    def __init__(self, clone_dir: str = None):
        super().__init__()
        self.clone_dir = clone_dir
        self.output = ""
    
    def execute(self) -> StepResult:
        """Clean up cloned repository"""
        try:
            if self.clone_dir and os.path.exists(self.clone_dir):
                print(f"Cleaning up {self.clone_dir}")
                shutil.rmtree(self.clone_dir, ignore_errors=True)
                self.output = f"Cleaned up {self.clone_dir}"
            else:
                self.output = "Nothing to clean up"
            
            print(self.output)
            return StepResult.SUCCESS
            
        except Exception as e:
            self.output = f"Cleanup warning: {str(e)}"
            print(self.output)
            # Don't fail the workflow for cleanup errors
            return StepResult.SUCCESS


def create_deployment_workflow(github_url: str, platform_id: str, 
                               branch: str = "main", project_name: str = "my-app"):
    """
    Create a deployment workflow with steps
    
    Returns:
        tuple: (steps_list, shared_context_dict)
    """
    # Shared context between steps
    context = {
        "github_url": github_url,
        "platform_id": platform_id,
        "branch": branch,
        "project_name": project_name,
        "clone_dir": None,
        "deployment_url": None
    }
    
    # Create workflow steps
    clone_step = GitCloneStep(github_url, branch)
    
    # Steps will share the clone directory
    steps = [clone_step]
    
    # We'll set clone_dir after the first step
    # For now, create a placeholder that we'll update
    deploy_step = PlatformDeployStep(
        platform_id=platform_id,
        github_url=github_url,
        branch=branch,
        project_name=project_name
    )
    
    cleanup_step = CleanupStep()
    
    steps.extend([deploy_step, cleanup_step])
    
    return steps, context


def update_step_context(steps: list, context: dict):
    """
    Update steps with shared context (called after clone step)
    
    Args:
        steps: List of workflow steps
        context: Shared context dictionary
    """
    if len(steps) >= 1 and isinstance(steps[0], GitCloneStep):
        context["clone_dir"] = steps[0].clone_dir
        resolved = getattr(steps[0], "resolved_branch", None)
        if resolved:
            context["branch"] = resolved
            if len(steps) >= 2 and isinstance(steps[1], PlatformDeployStep):
                steps[1].branch = resolved
    
    if len(steps) >= 2 and isinstance(steps[1], PlatformDeployStep):
        steps[1].clone_dir = context["clone_dir"]
    
    if len(steps) >= 3 and isinstance(steps[2], CleanupStep):
        steps[2].clone_dir = context["clone_dir"]
    
    # After deploy step, capture deployment URL
    if len(steps) >= 2 and isinstance(steps[1], PlatformDeployStep):
        context["deployment_url"] = steps[1].deployment_url

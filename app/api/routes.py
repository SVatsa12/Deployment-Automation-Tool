import re

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, HttpUrl
from datetime import datetime

from app.core.database import SessionLocal, get_db
from app.models.workflow import Workflow
from app.models.run import WorkflowRun
from app.models.step import StepRun
from app.engine.engine import run_workflow
from app.engine.sample_steps import BuildStep, TestStep, ApprovalStep, DeployStep
from app.engine.deployment_steps import (
    create_deployment_workflow,
    update_step_context,
    GitCloneStep,
    PlatformDeployStep,
    CleanupStep,
)
from app.utils.github_analyzer import GitHubAnalyzer
from app.utils.platform_deployers import DeployerFactory
from app.services.shortener import ensure_short_link_for_run, short_urls_for_run_ids

router = APIRouter(prefix="/api", tags=["workflows"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workflow_type: str = "demo"


class WorkflowRunResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    current_step: Optional[str]
    deployment_url: Optional[str] = None
    short_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StepRunResponse(BaseModel):
    id: int
    workflow_run_id: int
    step_name: str
    status: str
    result: Optional[str]
    error_message: Optional[str]
    retry_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApprovalRequest(BaseModel):
    approved: bool
    comment: Optional[str] = None


class AnalyzeRequest(BaseModel):
    github_url: HttpUrl


class DeployRequest(BaseModel):
    github_url: HttpUrl
    platform_id: str
    branch: str = "main"
    project_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper – build demo steps
# ---------------------------------------------------------------------------

def _demo_steps():
    return [BuildStep(), TestStep(), ApprovalStep(), DeployStep()]


def _update_run_deployment_url(workflow_run: WorkflowRun, db: Session) -> None:
    """
    Set workflow_run.deployment_url from successful deploy step output.
    Handles 'URL: https://...' and plain https URLs in the result text.
    """
    if workflow_run.deployment_url:
        return
    steps = (
        db.query(StepRun)
        .filter(StepRun.workflow_run_id == workflow_run.id)
        .order_by(StepRun.id.asc())
        .all()
    )
    for step in steps:
        if step.status != "SUCCESS" or not step.result:
            continue
        text = step.result.strip()
        if "URL: " in text:
            after = text.split("URL: ", 1)[1].strip().split()[0].split("\n")[0]
            if after.startswith("http"):
                workflow_run.deployment_url = after.rstrip(".,);")
                return
        m = re.search(r"https://[^\s\)\"'<>]+", text)
        if m:
            workflow_run.deployment_url = m.group(0).rstrip(".,);")
            return


def _workflow_run_response(run: WorkflowRun, db: Session) -> WorkflowRunResponse:
    urls = short_urls_for_run_ids(db, [run.id])
    if run.deployment_url and run.id not in urls:
        ensure_short_link_for_run(db, run)
        urls = short_urls_for_run_ids(db, [run.id])
    return WorkflowRunResponse.model_validate(run).model_copy(
        update={"short_url": urls.get(run.id)}
    )


def _workflow_run_responses(runs: List[WorkflowRun], db: Session) -> List[WorkflowRunResponse]:
    ids = [r.id for r in runs]
    urls = short_urls_for_run_ids(db, ids)
    for r in runs:
        if r.deployment_url and r.id not in urls:
            ensure_short_link_for_run(db, r)
    urls = short_urls_for_run_ids(db, ids)
    return [
        WorkflowRunResponse.model_validate(r).model_copy(update={"short_url": urls.get(r.id)})
        for r in runs
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/workflows", response_model=WorkflowRunResponse)
def create_workflow(workflow: WorkflowCreate, db: Session = Depends(get_db)):
    """Create and trigger a new workflow run."""
    existing_workflow = db.query(Workflow).filter(Workflow.name == workflow.name).first()

    if not existing_workflow:
        existing_workflow = Workflow(
            name=workflow.name,
            description=workflow.description,
            workflow_type=workflow.workflow_type,
        )
        db.add(existing_workflow)
        db.commit()
        db.refresh(existing_workflow)

    workflow_run = WorkflowRun(workflow_id=existing_workflow.id, status="PENDING")
    db.add(workflow_run)
    db.commit()
    db.refresh(workflow_run)

    if workflow.workflow_type == "demo":
        steps = _demo_steps()
    else:
        raise HTTPException(status_code=400, detail="Unknown workflow type")

    try:
        run_workflow(workflow_run, steps, db)
        db.refresh(workflow_run)
        _update_run_deployment_url(workflow_run, db)
        if workflow_run.deployment_url:
            ensure_short_link_for_run(db, workflow_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")

    return _workflow_run_response(workflow_run, db)


@router.get("/workflows/runs", response_model=List[WorkflowRunResponse])
def list_workflow_runs(
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all workflow runs with optional status filter."""
    query = db.query(WorkflowRun)
    if status:
        query = query.filter(WorkflowRun.status == status)
    runs = query.order_by(WorkflowRun.created_at.desc()).limit(limit).all()
    return _workflow_run_responses(runs, db)


@router.get("/workflows/runs/{run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(run_id: int, db: Session = Depends(get_db)):
    """Get details of a specific workflow run."""
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return _workflow_run_response(workflow_run, db)


@router.get("/workflows/runs/{run_id}/steps", response_model=List[StepRunResponse])
def get_workflow_steps(run_id: int, db: Session = Depends(get_db)):
    """Get all steps for a specific workflow run."""
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return (
        db.query(StepRun)
        .filter(StepRun.workflow_run_id == run_id)
        .order_by(StepRun.id.asc())
        .all()
    )


@router.post("/workflows/runs/{run_id}/approve", response_model=WorkflowRunResponse)
def approve_workflow(
    run_id: int,
    approval: ApprovalRequest,
    db: Session = Depends(get_db),
):
    """Approve or reject a workflow waiting for manual approval."""
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    if workflow_run.status != "WAITING_APPROVAL":
        raise HTTPException(
            status_code=400,
            detail=f"Workflow is not waiting for approval. Current status: {workflow_run.status}",
        )

    if not approval.approved:
        workflow_run.status = "REJECTED"
        db.commit()
        db.refresh(workflow_run)
        return _workflow_run_response(workflow_run, db)

    # Mark the approval step as SUCCESS
    approval_step = (
        db.query(StepRun)
        .filter(StepRun.workflow_run_id == run_id, StepRun.step_name == "approval")
        .first()
    )
    if approval_step:
        approval_step.status = "SUCCESS"
        approval_step.result = approval.comment or "Approved"
        db.commit()

    # FIX: Resume only from the steps that haven't completed yet.
    # run_workflow should skip steps whose StepRun already has status SUCCESS.
    steps = _demo_steps()
    try:
        run_workflow(workflow_run, steps, db)
        db.refresh(workflow_run)
        _update_run_deployment_url(workflow_run, db)
        if workflow_run.deployment_url:
            ensure_short_link_for_run(db, workflow_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")

    return _workflow_run_response(workflow_run, db)


@router.post("/workflows/runs/{run_id}/resume", response_model=WorkflowRunResponse)
def resume_workflow(run_id: int, db: Session = Depends(get_db)):
    """Resume a failed or stopped workflow from the last successful step."""
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    if workflow_run.status not in ["FAILED", "PENDING"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume workflow with status: {workflow_run.status}",
        )

    steps = _demo_steps()
    try:
        run_workflow(workflow_run, steps, db)
        db.refresh(workflow_run)
        _update_run_deployment_url(workflow_run, db)
        if workflow_run.deployment_url:
            ensure_short_link_for_run(db, workflow_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")

    return _workflow_run_response(workflow_run, db)


@router.post("/analyze")
def analyze_github_repo(request: AnalyzeRequest):
    """
    Analyze a GitHub repository and return compatible deployment platforms.
    """
    try:
        github_url = str(request.github_url)
        analysis_result = GitHubAnalyzer.analyze_repository(github_url)

        if not analysis_result.get("analysis_success"):
            raise HTTPException(
                status_code=400,
                detail=f"Failed to analyze repository: {analysis_result.get('error', 'Unknown error')}",
            )

        return {
            "success": True,
            "repository": analysis_result.get("repository"),
            "project_type": analysis_result.get("project_type"),
            "framework": analysis_result.get("framework"),
            "runtime": analysis_result.get("runtime"),
            "compatible_platforms": analysis_result.get("compatible_platforms", []),
            "message": f"Found {len(analysis_result.get('compatible_platforms', []))} compatible platforms",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Background deployment task
# ---------------------------------------------------------------------------

def run_deployment_workflow(
    workflow_run_id: int,
    github_url: str,
    platform_id: str,
    branch: str,
    project_name: str,
):
    """
    Background task: runs the full clone → deploy → cleanup pipeline.

    FIX 1: workflow_run is initialised to None before the try block so the
           except clause never hits an UnboundLocalError.

    FIX 2: update_step_context is called BETWEEN the clone step and the deploy
           step (inside run_workflow via a post-clone hook), not after the whole
           workflow finishes. Because run_workflow executes steps sequentially,
           we pass a post_step_hook that wires clone_dir into the later steps
           as soon as the clone step succeeds.
    """
    db = SessionLocal()
    workflow_run = None  # FIX 1: initialise before try so except can safely reference it

    try:
        workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if not workflow_run:
            print(f"Workflow run {workflow_run_id} not found")
            return

        # Build the three deployment steps
        steps, context = create_deployment_workflow(
            github_url=github_url,
            platform_id=platform_id,
            branch=branch,
            project_name=project_name,
        )

        print(f"Starting deployment workflow {workflow_run_id} with {len(steps)} steps")

        # FIX 2: Wire clone_dir into deploy/cleanup steps right after the clone
        # step finishes, BEFORE the deploy step runs.  We do this by defining a
        # post-step hook that run_workflow calls after each step completes.
        def post_step_hook(completed_step):
            if isinstance(completed_step, GitCloneStep):
                update_step_context(steps, context)

        run_workflow(workflow_run, steps, db=db, post_step_hook=post_step_hook)

        db.refresh(workflow_run)
        # context["deployment_url"] is only set after clone; read from deploy step.
        deploy_step = (
            steps[1]
            if len(steps) > 1 and isinstance(steps[1], PlatformDeployStep)
            else None
        )
        if deploy_step and deploy_step.deployment_url:
            workflow_run.deployment_url = deploy_step.deployment_url
        if workflow_run.status == "SUCCESS" and not workflow_run.deployment_url:
            _update_run_deployment_url(workflow_run, db)
        db.commit()
        db.refresh(workflow_run)
        if workflow_run.deployment_url:
            ensure_short_link_for_run(db, workflow_run)
            db.commit()

        if workflow_run.deployment_url:
            print(f"Deployment successful! URL: {workflow_run.deployment_url}")

        print(
            f"Deployment workflow {workflow_run_id} completed "
            f"with status: {workflow_run.status}"
        )

    except Exception as e:
        print(f"Error in deployment workflow {workflow_run_id}: {str(e)}")
        if workflow_run is not None:  # FIX 1: safe to check now
            workflow_run.status = "FAILED"
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Deploy endpoint
# ---------------------------------------------------------------------------

@router.post("/deploy")
def deploy_to_platform(
    request: DeployRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Deploy a GitHub repository to the selected platform (async).

    FIX: project_name falls back to a sanitised slug derived from the repo URL
    instead of blindly using `or "my-app"`, which would silently ignore an
    empty-string value sent by the caller.
    """
    try:
        github_url = str(request.github_url)
        platform_id = request.platform_id.lower()

        # Validate platform
        deployer = DeployerFactory.get_deployer(platform_id)
        if not deployer:
            supported = DeployerFactory.get_supported_platforms()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Platform '{platform_id}' not supported. "
                    f"Supported platforms: {', '.join(supported)}"
                ),
            )

        # FIX: Use explicit None check instead of truthiness so "" is treated
        # the same as None and we always produce a valid project name.
        if request.project_name is not None and request.project_name.strip():
            project_name = request.project_name.strip()
        else:
            # Derive a slug from the repo URL  e.g. "Hello-World"
            project_name = github_url.rstrip("/").split("/")[-1] or "my-app"

# Persist workflow — reuse existing to avoid UNIQUE constraint on repeated deploys
        workflow_name = f"Deploy to {platform_id}"
        workflow = db.query(Workflow).filter(Workflow.name == workflow_name).first()
        if not workflow:
            workflow = Workflow(
                name=workflow_name,
                description=f"Deploying {github_url} to {platform_id}",
                workflow_type="deployment",
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)

        workflow_run = WorkflowRun(
            workflow_id=workflow.id,
            status="PENDING",
            current_step="initializing",
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)

        # Kick off background deployment
        background_tasks.add_task(
            run_deployment_workflow,
            workflow_run_id=workflow_run.id,
            github_url=github_url,
            platform_id=platform_id,
            branch=request.branch,
            project_name=project_name,
        )

        return {
            "success": True,
            "workflow_run_id": workflow_run.id,
            "status": "PENDING",
            "message": (
                f"Deployment started in background. "
                f"Check status at /api/workflows/runs/{workflow_run.id}"
            ),
            "status_url": f"/api/workflows/runs/{workflow_run.id}",
            "steps_url": f"/api/workflows/runs/{workflow_run.id}/steps",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Delete run
# ---------------------------------------------------------------------------

@router.delete("/workflows/runs/{run_id}")
def delete_workflow_run(run_id: int, db: Session = Depends(get_db)):
    """Delete a workflow run and all its steps."""
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    db.query(StepRun).filter(StepRun.workflow_run_id == run_id).delete()
    db.delete(workflow_run)
    db.commit()

    return {"message": f"Workflow run {run_id} deleted successfully"}
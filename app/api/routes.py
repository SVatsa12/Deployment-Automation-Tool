from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, HttpUrl
from datetime import datetime

from app.core.database import SessionLocal
from app.models.workflow import Workflow
from app.models.run import WorkflowRun
from app.models.step import StepRun
from app.engine.engine import run_workflow
from app.engine.sample_steps import BuildStep, TestStep, ApprovalStep, DeployStep
from app.utils.github_analyzer import GitHubAnalyzer
from app.utils.platform_deployers import DeployerFactory

router = APIRouter(prefix="/api", tags=["workflows"])


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models for request/response
class WorkflowCreate(BaseModel):
    name: str
    workflow_type: str = "demo"  # For now, only demo workflow


class WorkflowRunResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    current_step: Optional[str]
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


# New models for GitHub deployment
class AnalyzeRequest(BaseModel):
    github_url: HttpUrl


class DeployRequest(BaseModel):
    github_url: HttpUrl
    platform_id: str  # e.g., "vercel", "netlify", "railway"
    branch: str = "main"
    project_name: Optional[str] = None


# Routes

@router.post("/workflows", response_model=WorkflowRunResponse)
def create_workflow(workflow: WorkflowCreate, db: Session = Depends(get_db)):
    """
    Create and trigger a new workflow run.
    """
    # Check if workflow exists, if not create it
    existing_workflow = db.query(Workflow).filter(Workflow.name == workflow.name).first()
    
    if not existing_workflow:
        existing_workflow = Workflow(name=workflow.name)
        db.add(existing_workflow)
        db.commit()
        db.refresh(existing_workflow)
    
    # Create workflow run
    workflow_run = WorkflowRun(
        workflow_id=existing_workflow.id,
        status="PENDING"
    )
    db.add(workflow_run)
    db.commit()
    db.refresh(workflow_run)
    
    # Define steps based on workflow type
    if workflow.workflow_type == "demo":
        steps = [
            BuildStep(),
            TestStep(),
            ApprovalStep(),
            DeployStep()
        ]
    else:
        raise HTTPException(status_code=400, detail="Unknown workflow type")
    
    # Execute workflow asynchronously (in production, use background tasks)
    try:
        run_workflow(workflow_run, steps, db)
        db.refresh(workflow_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")
    
    return workflow_run


@router.get("/workflows/runs", response_model=List[WorkflowRunResponse])
def list_workflow_runs(
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all workflow runs with optional status filter.
    """
    query = db.query(WorkflowRun)
    
    if status:
        query = query.filter(WorkflowRun.status == status)
    
    runs = query.order_by(WorkflowRun.created_at.desc()).limit(limit).all()
    return runs


@router.get("/workflows/runs/{run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(run_id: int, db: Session = Depends(get_db)):
    """
    Get details of a specific workflow run.
    """
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    return workflow_run


@router.get("/workflows/runs/{run_id}/steps", response_model=List[StepRunResponse])
def get_workflow_steps(run_id: int, db: Session = Depends(get_db)):
    """
    Get all steps for a specific workflow run.
    """
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    steps = db.query(StepRun).filter(StepRun.workflow_run_id == run_id).all()
    return steps


@router.post("/workflows/runs/{run_id}/approve", response_model=WorkflowRunResponse)
def approve_workflow(
    run_id: int,
    approval: ApprovalRequest,
    db: Session = Depends(get_db)
):
    """
    Approve or reject a workflow waiting for manual approval.
    """
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    if workflow_run.status != "WAITING_APPROVAL":
        raise HTTPException(
            status_code=400,
            detail=f"Workflow is not waiting for approval. Current status: {workflow_run.status}"
        )
    
    if not approval.approved:
        # Reject the workflow
        workflow_run.status = "REJECTED"
        db.commit()
        db.refresh(workflow_run)
        return workflow_run
    
    # Approve and resume workflow
    # Update the approval step to SUCCESS
    approval_step = db.query(StepRun).filter(
        StepRun.workflow_run_id == run_id,
        StepRun.step_name == "approval"
    ).first()
    
    if approval_step:
        approval_step.status = "SUCCESS"
        approval_step.result = approval.comment or "Approved"
        db.commit()
    
    # Resume workflow execution
    steps = [
        BuildStep(),
        TestStep(),
        ApprovalStep(),
        DeployStep()
    ]
    
    try:
        run_workflow(workflow_run, steps, db)
        db.refresh(workflow_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")
    
    return workflow_run


@router.post("/workflows/runs/{run_id}/resume", response_model=WorkflowRunResponse)
def resume_workflow(run_id: int, db: Session = Depends(get_db)):
    """
    Resume a failed or stopped workflow from the last successful step.
    """
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    if workflow_run.status not in ["FAILED", "PENDING"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume workflow with status: {workflow_run.status}"
        )
    
    # Define steps (in production, this should be stored in DB)
    steps = [
        BuildStep(),
        TestStep(),
        ApprovalStep(),
        DeployStep()
    ]
    
    try:
        run_workflow(workflow_run, steps, db)
        db.refresh(workflow_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")
    
    return workflow_run


@router.post("/analyze")
def analyze_github_repo(request: AnalyzeRequest):
    """
    Analyze a GitHub repository and return compatible deployment platforms
    
    Returns:
    - Project type (Node.js, Python, static, etc.)
    - Detected framework (React, Next.js, Django, etc.)
    - List of compatible deployment platforms with details
    """
    try:
        github_url = str(request.github_url)
        analysis_result = GitHubAnalyzer.analyze_repository(github_url)
        
        if not analysis_result.get("analysis_success"):
            raise HTTPException(
                status_code=400,
                detail=f"Failed to analyze repository: {analysis_result.get('error', 'Unknown error')}"
            )
        
        return {
            "success": True,
            "repository": analysis_result.get("repository"),
            "project_type": analysis_result.get("project_type"),
            "framework": analysis_result.get("framework"),
            "runtime": analysis_result.get("runtime"),
            "compatible_platforms": analysis_result.get("compatible_platforms", []),
            "message": f"Found {len(analysis_result.get('compatible_platforms', []))} compatible platforms"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deploy")
def deploy_to_platform(request: DeployRequest):
    """
    Deploy a GitHub repository to selected platform
    
    Input:
    - github_url: GitHub repository URL
    - platform_id: Platform to deploy to (vercel, netlify, railway, etc.)
    - branch: Git branch to deploy (default: main)
    - project_name: Optional project name
    
    Returns deployment status and URL
    """
    try:
        github_url = str(request.github_url)
        platform_id = request.platform_id.lower()
        
        # Get deployer for platform
        deployer = DeployerFactory.get_deployer(platform_id)
        
        if not deployer:
            supported = DeployerFactory.get_supported_platforms()
            raise HTTPException(
                status_code=400,
                detail=f"Platform '{platform_id}' not supported. Supported platforms: {', '.join(supported)}"
            )
        
        # Deploy to platform
        deployment_result = deployer.deploy(
            github_url=github_url,
            branch=request.branch,
            project_name=request.project_name or "my-app"
        )
        
        if not deployment_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Deployment failed: {deployment_result.get('error', 'Unknown error')}"
            )
        
        return {
            "success": True,
            "platform": deployment_result.get("platform"),
            "deployment_url": deployment_result.get("deployment_url"),
            "message": deployment_result.get("message"),
            "instructions": deployment_result.get("instructions", [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workflows/runs/{run_id}")
def delete_workflow_run(run_id: int, db: Session = Depends(get_db)):
    """
    Delete a workflow run and all its steps.
    """
    workflow_run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    # Delete associated steps
    db.query(StepRun).filter(StepRun.workflow_run_id == run_id).delete()
    
    # Delete workflow run
    db.delete(workflow_run)
    db.commit()
    
    return {"message": f"Workflow run {run_id} deleted successfully"}

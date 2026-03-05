# Deployment Automation Tool

A workflow automation system with resume capabilities, step-level retries, and manual approvals.

## Features

- ✅ **Workflow Execution Engine** - Sequential step execution with state persistence
- ✅ **Resume Capability** - Automatically resumes from last successful step after failures
- ✅ **Step-level Retries** - Configurable retry logic for individual steps
- ✅ **Manual Approvals** - Pause workflows for human approval before critical steps
- ✅ **REST API** - Full API for workflow management and monitoring
- ✅ **SQLite Database** - Persistent storage of workflow runs and step states

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Run the Server

```bash
# Start the API server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### Health Check

```bash
GET /
```

### Create and Trigger Workflow

```bash
POST /api/workflows
Content-Type: application/json

{
  "name": "my-deployment",
  "workflow_type": "demo"
}
```

### List Workflow Runs

```bash
# Get all runs
GET /api/workflows/runs

# Filter by status
GET /api/workflows/runs?status=WAITING_APPROVAL
```

### Get Workflow Run Details

```bash
GET /api/workflows/runs/{run_id}
```

### Get Workflow Steps

```bash
GET /api/workflows/runs/{run_id}/steps
```

### Approve Workflow

```bash
POST /api/workflows/runs/{run_id}/approve
Content-Type: application/json

{
  "approved": true,
  "comment": "Looks good, deploying to production"
}
```

### Resume Failed Workflow

```bash
POST /api/workflows/runs/{run_id}/resume
```

### Delete Workflow Run

```bash
DELETE /api/workflows/runs/{run_id}
```

## Workflow Statuses

- `PENDING` - Workflow created but not started
- `RUNNING` - Currently executing
- `WAITING_APPROVAL` - Paused for manual approval
- `SUCCESS` - Completed successfully
- `FAILED` - Failed with no retries remaining
- `REJECTED` - Manually rejected during approval

## Step Statuses

- `PENDING` - Not yet executed
- `RUNNING` - Currently executing
- `SUCCESS` - Completed successfully
- `FAILED` - Failed execution

## Example Demo Workflow

The demo workflow includes 4 steps:

1. **Build** - Simulates building the project (1 retry)
2. **Test** - Simulates running tests (1 retry)
3. **Approval** - Manual approval gate (no retries)
4. **Deploy** - Simulates deployment (1 retry)

## Database Schema

### Tables

- `workflows` - Workflow definitions
- `workflow_runs` - Individual workflow executions
- `step_runs` - Individual step executions within a workflow run

## Configuration

Edit [app/core/config.py](app/core/config.py) or use environment variables:

- `DATABASE_URL` - Database connection string
- `HOST` - API server host
- `PORT` - API server port
- `DEFAULT_MAX_RETRIES` - Default retry count for steps
- `WORKFLOW_TIMEOUT_SECONDS` - Workflow execution timeout

## Project Structure

```
app/
├── main.py              # FastAPI application
├── api/
│   └── routes.py        # REST API endpoints
├── core/
│   ├── config.py        # Configuration settings
│   ├── database.py      # Database connection
│   └── init_db.py       # Database initialization
├── engine/
│   ├── engine.py        # Workflow execution engine
│   ├── demo_workflow.py # Demo workflow
│   └── sample_steps.py  # Sample step implementations
├── models/
│   ├── workflow.py      # Workflow model
│   ├── run.py           # WorkflowRun model
│   └── step.py          # StepRun and BaseStep models
└── utils/
    └── logger.py        # Logging utilities
```

## Development

### Running Tests

```bash
pytest
```

### Code Style

```bash
black app/
flake8 app/
```

## License

MIT

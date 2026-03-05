from fastapi import FastAPI
from app.core.init_db import init_db
from app.api.routes import router

app = FastAPI(
    title="Deployment Automation Tool",
    description="A workflow automation system with resume capabilities, retries, and manual approvals",
    version="1.0.0"
)

# Include API routes
app.include_router(router)

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/")
def health():
    return {"status": "running", "message": "Deployment Automation Tool is operational"}

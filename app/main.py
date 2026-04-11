"""
Deployment Automation Tool — application entry point.
"""
import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.init_db import init_db
from app.api.routes import router
from app.models.short_link import ShortLink


# ---------------------------------------------------------------------------
# FIX 5: Configure logging from settings before anything else runs.
# Applies LOG_LEVEL and optionally writes to LOG_FILE.
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """
    Set up root logger using settings.LOG_LEVEL and settings.LOG_FILE.
    Called once at module load so all loggers across the app inherit the config.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if settings.LOG_FILE:
        # Rotating file handler — max 5 MB per file, keep 3 backups
        file_handler = logging.handlers.RotatingFileHandler(
            settings.LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
        force=True,  # Override any previously set handlers (e.g. uvicorn defaults)
    )


_configure_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FIX 1: Use lifespan context manager instead of deprecated @app.on_event
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.
    Code before `yield` runs on startup; code after runs on shutdown.
    """
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    init_db()
    logger.info("Database initialised successfully.")
    yield
    # Add any shutdown cleanup here (e.g. close connection pools)
    logger.info("Shutting down %s.", settings.APP_NAME)


# ---------------------------------------------------------------------------
# FIX 2 & 3: Build app from settings; add CORS middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    # FIX 3: pull metadata from settings instead of hardcoding
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "A workflow automation system with resume capabilities, "
        "step-level retries, and manual approvals."
    ),
    # FIX 1: pass lifespan handler
    lifespan=lifespan,
    # Disable docs in production when DEBUG=False (optional — remove if unwanted)
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# FIX 2: CORS — origins controlled via settings.ALLOWED_ORIGINS in .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(router)


@app.get("/r/{code}", tags=["redirect"])
def redirect_short_link(code: str, db: Session = Depends(get_db)):
    """302 redirect from a short code to the stored deployment URL."""
    row = db.query(ShortLink).filter(ShortLink.code == code.strip()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Link not found")
    return RedirectResponse(url=row.target_url, status_code=302)


# ---------------------------------------------------------------------------
# FIX 4: Richer health check endpoint
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"])
def health_check():
    """
    Health check endpoint.
    Returns app name, version, environment, and DB URL (sanitised).
    """
    # Sanitise DB URL — strip credentials before exposing
    db_url = settings.DATABASE_URL
    if "@" in db_url:
        # e.g. postgresql://user:password@host/db → postgresql://***@host/db
        scheme, rest = db_url.split("://", 1)
        db_url = f"{scheme}://***@{rest.split('@', 1)[1]}"

    return {
        "status": "running",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "database": db_url,
        "message": f"{settings.APP_NAME} is operational",
    }
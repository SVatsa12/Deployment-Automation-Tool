"""
Database initialization — creates all tables if they do not already exist.
"""
import logging

from sqlalchemy import inspect

from app.core.database import engine, Base

# Import all models so their table definitions are registered on Base.metadata
# before create_all() is called. If any model is missing here, its table will
# not be created.
from app.models.workflow import Workflow      # noqa: F401
from app.models.run import WorkflowRun        # noqa: F401
from app.models.step import StepRun           # noqa: F401

logger = logging.getLogger(__name__)


def init_db() -> None:
    """
    Create all database tables that do not already exist.

    FIX 1: Wrapped in try/except so misconfiguration (bad URL, missing
            permissions, locked SQLite file) raises a clear error at startup
            instead of silently failing mid-request.

    FIX 2: Logs which tables were created vs already existed so you always
            know the DB state at startup.

    FIX 3: Replaced deprecated `Base.metadata.create_all(bind=engine)` with
            the SQLAlchemy 2.x style using a connection context manager.
    """
    try:
        # FIX 3: SQLAlchemy 2.x preferred style — use a connection, not bind=
        with engine.begin() as conn:
            # Check which tables exist before creation for informative logging
            inspector = inspect(conn)
            existing_tables = set(inspector.get_table_names())

            # Create all tables registered on Base.metadata
            Base.metadata.create_all(bind=conn)

            # FIX 2: Log outcome per table
            all_tables = set(Base.metadata.tables.keys())
            created = all_tables - existing_tables
            already_existed = all_tables & existing_tables

            if created:
                logger.info("Created tables: %s", ", ".join(sorted(created)))
            if already_existed:
                logger.debug("Tables already exist (skipped): %s", ", ".join(sorted(already_existed)))

            logger.info("Database initialisation complete.")

    except Exception as e:
        # FIX 1: Surface the error clearly so it's obvious at startup
        logger.critical("Failed to initialise database: %s", str(e), exc_info=True)
        raise RuntimeError(f"Database initialisation failed: {e}") from e
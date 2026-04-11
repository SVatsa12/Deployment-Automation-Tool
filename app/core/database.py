"""
Database configuration and session management.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool, NullPool

from app.core.config import settings


# ---------------------------------------------------------------------------
# FIX 2: Use the modern SQLAlchemy 2.x DeclarativeBase style.
# All models inherit from this Base.
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FIX 1 & 3: Build engine from settings.DATABASE_URL so .env changes are
# respected, and apply sensible pool/connection args per DB dialect.
# ---------------------------------------------------------------------------

def _build_engine():
    """
    Create the SQLAlchemy engine with appropriate settings for the configured
    database dialect (SQLite vs everything else).

    SQLite notes:
    - check_same_thread=False  — SQLite connections are not thread-safe by
      default; FastAPI's background tasks run on different threads, so this
      flag is required.
    - StaticPool          — reuses a single in-process connection for SQLite,
      which avoids "database is locked" errors during tests / dev.

    Postgres / MySQL notes:
    - NullPool is NOT used; SQLAlchemy's default QueuePool handles concurrent
      connections well.  Pool size is kept small and conservative.
    """
    url: str = settings.DATABASE_URL

    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            # StaticPool keeps one connection alive for the process lifetime,
            # which is ideal for SQLite in development / single-worker deploys.
            poolclass=StaticPool,
            echo=settings.SQLALCHEMY_ECHO,
        )

        # Enforce foreign-key constraints for SQLite (off by default)
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    else:
        # Postgres, MySQL, etc.
        return create_engine(
            url,
            pool_pre_ping=True,    # Detect stale connections before use
            pool_size=5,           # Max persistent connections
            max_overflow=10,       # Extra connections allowed under load
            pool_recycle=1800,     # Recycle connections every 30 minutes
            echo=settings.SQLALCHEMY_ECHO,
        )


# ---------------------------------------------------------------------------
# FIX 4: Engine and SessionLocal are still module-level (FastAPI needs them
# at import time) but _build_engine() centralises error-prone logic so
# misconfiguration raises a clear error with a useful traceback at startup,
# not buried inside a request handler.
# ---------------------------------------------------------------------------
engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,   # Prevent "DetachedInstanceError" in background tasks
)


# ---------------------------------------------------------------------------
# Convenience dependency for FastAPI routes (used in routes.py get_db())
# ---------------------------------------------------------------------------
def get_db():
    """
    Yield a database session and ensure it is closed after the request,
    even if an exception occurs.

    Commit on success so read-only requests end with COMMIT instead of an
    implicit ROLLBACK on close (quieter logs; same semantics for SQLite).
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
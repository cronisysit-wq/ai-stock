"""
SQLAlchemy database setup for SQLite (local) and PostgreSQL (Railway).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from config.settings import get_settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""
    pass


def normalize_database_url(url: str) -> str:
    """Normalize Railway/Heroku-style postgres URLs for SQLAlchemy."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def get_engine():
    """Create a SQLAlchemy engine from the current settings."""
    settings = get_settings()
    database_url = normalize_database_url(settings.DATABASE_URL)
    connect_args = {}
    engine_kwargs = {"echo": False}

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        # Keep connections healthy across Railway restarts / idle timeouts.
        engine_kwargs["pool_pre_ping"] = True

    return create_engine(
        database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )


engine = None
SessionLocal = None


def init_db():
    """Initialize the database engine and create all tables."""
    global engine, SessionLocal
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Register every ORM model before create_all().
    import db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")


def get_db() -> Session:
    """Get a database session as a generator (for FastAPI dependency injection).

    Must call init_db() first, or it will be called automatically.
    """
    if SessionLocal is None:
        init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """Get a database session directly (not as generator). Caller must close."""
    if SessionLocal is None:
        init_db()
    return SessionLocal()

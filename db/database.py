"""
SQLAlchemy database setup with SQLite.
Structured for easy migration to PostgreSQL later.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from config.settings import get_settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""
    pass


def get_engine():
    """Create a SQLAlchemy engine from the current settings."""
    settings = get_settings()
    connect_args = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.DATABASE_URL, connect_args=connect_args, echo=False
    )


engine = None
SessionLocal = None


def init_db():
    """Initialize the database engine and create all tables."""
    global engine, SessionLocal
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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

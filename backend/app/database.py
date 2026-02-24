"""Database configuration and session management."""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings

logger = logging.getLogger(__name__)


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=60,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency to get database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables and run lightweight schema migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Lightweight migrations for existing databases ──
    async with engine.begin() as conn:
        # Add 'new_response' value to the document_category enum if missing
        try:
            await conn.execute(text(
                "ALTER TYPE document_category ADD VALUE IF NOT EXISTS 'new_response'"
            ))
        except Exception:
            logger.debug("document_category enum already has 'new_response' or ALTER TYPE not supported")

        # Add enabled_categories column to rfp_projects if missing
        try:
            await conn.execute(text(
                "ALTER TABLE rfp_projects ADD COLUMN IF NOT EXISTS "
                "enabled_categories JSON DEFAULT '[\"old_rfp\",\"old_response\",\"new_rfp\"]'"
            ))
        except Exception:
            logger.debug("enabled_categories column already exists or ALTER TABLE not supported")

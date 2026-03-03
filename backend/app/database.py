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


def create_task_engine():
    """Create a short-lived engine for Celery task execution.

    Each ``asyncio.run()`` in a Celery worker creates a **new** event loop.
    The module-level ``engine`` retains asyncpg connections that were bound to
    the previous (now closed) event loop, causing
    ``unexpected EOF on client connection with an open transaction`` and
    ``Connection reset by peer`` errors on subsequent tasks.

    This function returns an independent engine + session factory that the
    caller **must** dispose of when done::

        task_engine, TaskSession = create_task_engine()
        try:
            async with TaskSession() as db:
                ...
        finally:
            await task_engine.dispose()
    """
    task_engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_timeout=30,
    )

    task_session_factory = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return task_engine, task_session_factory


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
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    # Use a separate engine with AUTOCOMMIT isolation for this single statement.
    autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    async with autocommit_engine.connect() as conn:
        try:
            # SQLAlchemy SAEnum uses Python enum .name (uppercase) by default
            await conn.execute(text(
                "ALTER TYPE document_category ADD VALUE IF NOT EXISTS 'NEW_RESPONSE'"
            ))
        except Exception:
            logger.debug("document_category enum already has 'NEW_RESPONSE' or ALTER TYPE not supported")

    async with autocommit_engine.connect() as conn:
        try:
            await conn.execute(text(
                "ALTER TYPE document_category ADD VALUE IF NOT EXISTS 'INSPIRATION'"
            ))
        except Exception:
            logger.debug("document_category enum already has 'INSPIRATION' or ALTER TYPE not supported")

    # Add enabled_categories column (this can run in a normal transaction)
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE rfp_projects ADD COLUMN IF NOT EXISTS "
                "enabled_categories JSON DEFAULT '[\"old_rfp\",\"old_response\",\"new_rfp\"]'"
            ))
        except Exception:
            logger.debug("enabled_categories column already exists or ALTER TABLE not supported")

    # Add ai_context column for project-level AI context
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE rfp_projects ADD COLUMN IF NOT EXISTS "
                "ai_context TEXT DEFAULT ''"
            ))
        except Exception:
            logger.debug("ai_context column already exists or ALTER TABLE not supported")

    # Add context_mode column (rag or full) for AI context retrieval strategy
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE rfp_projects ADD COLUMN IF NOT EXISTS "
                "context_mode VARCHAR(20) DEFAULT 'rag'"
            ))
        except Exception:
            logger.debug("context_mode column already exists or ALTER TABLE not supported")

    # Add full_text / anonymized_full_text columns on documents for full-context mode
    async with engine.begin() as conn:
        for col in ("full_text", "anonymized_full_text"):
            try:
                await conn.execute(text(
                    f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS "
                    f"{col} TEXT DEFAULT ''"
                ))
            except Exception:
                logger.debug("%s column already exists or ALTER TABLE not supported", col)

    # Add company_name column for respondent identity (distinct from client_name)
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE rfp_projects ADD COLUMN IF NOT EXISTS "
                "company_name VARCHAR(255) DEFAULT ''"
            ))
        except Exception:
            logger.debug("company_name column already exists or ALTER TABLE not supported")

    # ── Vision AI image analysis columns on document_images ──
    vision_columns = {
        "analysis_status": "VARCHAR(20) DEFAULT 'pending'",
        "image_type": "VARCHAR(50) DEFAULT ''",
        "anonymized_description": "TEXT DEFAULT ''",
        "key_information": "JSON DEFAULT '[]'",
        "pii_detected": "JSON DEFAULT '[]'",
        "ocr_text": "TEXT DEFAULT ''",
        "anonymized_ocr_text": "TEXT DEFAULT ''",
        "suggested_usage": "TEXT DEFAULT ''",
        "section_title": "VARCHAR(500) DEFAULT ''",
    }
    async with engine.begin() as conn:
        for col_name, col_type in vision_columns.items():
            try:
                await conn.execute(text(
                    f"ALTER TABLE document_images ADD COLUMN IF NOT EXISTS "
                    f"{col_name} {col_type}"
                ))
            except Exception:
                logger.debug("document_images.%s column already exists", col_name)

    # ── Image gallery columns: category + selection ──
    gallery_columns = {
        "image_category": "VARCHAR(30) DEFAULT 'autre'",
        "selected": "BOOLEAN DEFAULT false",
    }
    async with engine.begin() as conn:
        for col_name, col_type in gallery_columns.items():
            try:
                await conn.execute(text(
                    f"ALTER TABLE document_images ADD COLUMN IF NOT EXISTS "
                    f"{col_name} {col_type}"
                ))
            except Exception:
                logger.debug("document_images.%s column already exists", col_name)

    # ── Image content_hash for deduplication ──
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE document_images ADD COLUMN IF NOT EXISTS "
                "content_hash VARCHAR(64) DEFAULT ''"
            ))
        except Exception:
            logger.debug("document_images.content_hash column already exists")
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_document_images_content_hash "
                "ON document_images (content_hash) WHERE content_hash != ''"
            ))
        except Exception:
            logger.debug("document_images content_hash index already exists")

    # Backfill content_hash from stored_filename for existing images
    # Filenames follow pattern: ..._<8-char-hex-hash>.<ext>
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "UPDATE document_images "
                "SET content_hash = substring(stored_filename from '([a-f0-9]{8})\\.[a-z]+$') "
                "WHERE content_hash = '' OR content_hash IS NULL"
            ))
        except Exception:
            logger.debug("Backfill of document_images.content_hash skipped or failed")

    # Add content_hash column for duplicate file detection
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS "
                "content_hash VARCHAR(64) DEFAULT ''"
            ))
        except Exception:
            logger.debug("content_hash column already exists or ALTER TABLE not supported")
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_documents_content_hash "
                "ON documents (content_hash) WHERE content_hash != ''"
            ))
        except Exception:
            logger.debug("content_hash index already exists")

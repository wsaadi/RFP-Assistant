"""Database configuration and session management."""
import logging
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def task_session():
    """Async context manager for Celery task DB sessions.

    Creates a short-lived engine + session that is safe to use inside
    ``asyncio.run()`` (i.e. a fresh event loop).  The engine is disposed
    automatically on exit::

        async with task_session() as db:
            result = await db.execute(...)
    """
    task_engine, session_factory = create_task_engine()
    try:
        async with session_factory() as db:
            yield db
    finally:
        await task_engine.dispose()


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

    # ── NER / Vision provider config columns on ai_configs ──
    ai_config_columns = {
        "ner_provider": "VARCHAR(20) DEFAULT 'ollama'",
        "ner_model": "VARCHAR(100) DEFAULT 'qwen2.5:14b'",
        "vision_provider": "VARCHAR(20) DEFAULT 'ollama'",
        "vision_model": "VARCHAR(100) DEFAULT 'llama3.2-vision:11b'",
        "scaleway_api_key_encrypted": "TEXT DEFAULT ''",
        "scaleway_project_id": "VARCHAR(100) DEFAULT ''",
    }
    async with engine.begin() as conn:
        for col_name, col_type in ai_config_columns.items():
            try:
                await conn.execute(text(
                    f"ALTER TABLE ai_configs ADD COLUMN IF NOT EXISTS "
                    f"{col_name} {col_type}"
                ))
            except Exception:
                logger.debug("ai_configs.%s column already exists", col_name)

    # ── AI Usage Logs table ──
    async with engine.begin() as conn:
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_usage_logs (
                    id UUID PRIMARY KEY,
                    project_id UUID NOT NULL REFERENCES rfp_projects(id) ON DELETE CASCADE,
                    operation VARCHAR(100) NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    model_name VARCHAR(100) NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
        except Exception:
            logger.debug("ai_usage_logs table already exists")
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_project "
                "ON ai_usage_logs (project_id, created_at DESC)"
            ))
        except Exception:
            logger.debug("ai_usage_logs index already exists")

    # ── AI Model Pricing table ──
    async with engine.begin() as conn:
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_model_pricing (
                    id UUID PRIMARY KEY,
                    provider VARCHAR(50) NOT NULL,
                    model_name VARCHAR(100) NOT NULL,
                    price_per_1k_input FLOAT DEFAULT 0.0,
                    price_per_1k_output FLOAT DEFAULT 0.0,
                    currency VARCHAR(10) DEFAULT 'EUR',
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
        except Exception:
            logger.debug("ai_model_pricing table already exists")

        # Seed default pricing for common models (EUR per 1K tokens, public prices)
        default_pricing = [
            # Mistral AI
            ("mistral", "mistral-large-latest", 0.0018, 0.0055),
            ("mistral", "mistral-small-latest", 0.0002, 0.0006),
            ("mistral", "open-mistral-nemo", 0.00015, 0.00015),
            ("mistral", "codestral-latest", 0.0003, 0.0009),
            ("mistral", "pixtral-large-latest", 0.0018, 0.0055),
            # Scaleway
            ("scaleway", "mistral-large-3-675b-instruct-2512", 0.002, 0.006),
            ("scaleway", "mistral-small-3.1-24b-instruct-2503", 0.0002, 0.0006),
            ("scaleway", "llama-3.3-70b-instruct", 0.00035, 0.0008),
            # OpenAI
            ("openai", "gpt-4o", 0.0023, 0.0092),
            ("openai", "gpt-4o-mini", 0.000138, 0.00055),
            ("openai", "o3-mini", 0.001, 0.004),
            # Anthropic
            ("anthropic", "claude-sonnet-4", 0.00276, 0.0138),
            ("anthropic", "claude-3.5-haiku", 0.00074, 0.0037),
            # Google
            ("google", "gemini-2.0-flash", 0.000069, 0.000368),
            ("google", "gemini-1.5-pro", 0.00115, 0.0046),
        ]
        try:
            for provider, model, price_in, price_out in default_pricing:
                await conn.execute(text("""
                    INSERT INTO ai_model_pricing (id, provider, model_name, price_per_1k_input, price_per_1k_output, currency)
                    SELECT gen_random_uuid(), :provider::VARCHAR(50), :model::VARCHAR(100), :price_in::FLOAT, :price_out::FLOAT, 'EUR'
                    WHERE NOT EXISTS (SELECT 1 FROM ai_model_pricing WHERE provider = :provider::VARCHAR(50) AND model_name = :model::VARCHAR(100))
                """), {"provider": provider, "model": model, "price_in": price_in, "price_out": price_out})
        except Exception:
            logger.debug("Default pricing seed skipped")

    # ── Content Reuse Results table ──
    async with engine.begin() as conn:
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS content_reuse_results (
                    id UUID PRIMARY KEY,
                    project_id UUID NOT NULL REFERENCES rfp_projects(id) ON DELETE CASCADE,
                    has_old_response BOOLEAN DEFAULT false,
                    overall_reuse_percentage FLOAT DEFAULT 0.0,
                    chapters JSON DEFAULT '[]',
                    summary JSON DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
        except Exception:
            logger.debug("content_reuse_results table already exists")
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_content_reuse_results_project "
                "ON content_reuse_results (project_id, created_at DESC)"
            ))
        except Exception:
            logger.debug("content_reuse_results index already exists")

    # ── source_document_ids, source_categories, include_generated_content, custom_notes on response_documents ──
    async with engine.begin() as conn:
        for col_name, col_type in {
            "source_document_ids": "JSON DEFAULT '[]'",
            "source_categories": "JSON DEFAULT '[]'",
            "include_generated_content": "BOOLEAN DEFAULT false",
            "custom_notes": "TEXT DEFAULT ''",
        }.items():
            try:
                await conn.execute(text(
                    f"ALTER TABLE response_documents ADD COLUMN IF NOT EXISTS "
                    f"{col_name} {col_type}"
                ))
            except Exception:
                logger.debug("response_documents.%s column already exists", col_name)

    # Add word_limit column on chapters
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE chapters ADD COLUMN IF NOT EXISTS "
                "word_limit INTEGER DEFAULT 0"
            ))
        except Exception:
            logger.debug("chapters.word_limit column already exists")

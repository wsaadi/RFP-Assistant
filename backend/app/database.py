"""Database configuration and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings


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
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

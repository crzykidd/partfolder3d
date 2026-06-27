"""Database engine and session factory.

Provides an async SQLAlchemy engine and session maker for use throughout the app.
Depends on: DATABASE_URL environment variable (loaded via config.py).

Usage in route handlers (once dependency-injection is set up in Phase 1):
    async with SessionLocal() as session:
        result = await session.execute(...)
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

# Create the async engine.  echo=settings.DEBUG for SQL query logging.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# Session factory — expire_on_commit=False keeps ORM objects usable after commit.
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)

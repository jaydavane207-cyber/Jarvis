import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Default to SQLite for local development if Postgres isn't provided.
# In production, this MUST be a PostgreSQL connection string.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./jarvis_local.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    """
    Dependency to get the database session.
    Yields an AsyncSession for the request duration.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

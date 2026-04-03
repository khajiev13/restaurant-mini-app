import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.models import Base


@pytest_asyncio.fixture
async def db_session():
    """Yields a transactional session that rolls back after each test.

    Uses NullPool so each test gets its own connection with no event-loop binding.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as connection:
        transaction = await connection.begin()

        session_maker = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async with session_maker() as session:
            yield session

        await transaction.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """Yields an AsyncClient with the database dependency overridden."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()

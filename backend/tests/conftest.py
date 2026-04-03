import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import engine as app_engine
from app.database import get_db
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Yields a SQLAlchemy async engine bounded to the current app database."""
    # We will use the existing application database engine, but we ensure tables exist.
    async with app_engine.begin():
        # Rely on existing tables created by init.sql
        pass

    yield app_engine

@pytest_asyncio.fixture
async def db_session(db_engine):
    """Yields a transactional session that rolls back after each test."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()

        session_maker = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )

        async with session_maker() as session:
            yield session

        await transaction.rollback()

@pytest_asyncio.fixture
async def client(db_session):
    """Yields an AsyncClient with the database dependency overridden."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()

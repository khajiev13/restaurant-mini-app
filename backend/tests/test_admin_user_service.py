import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.models import Base, User
from app.services import admin_user_service


class _AsyncBarrier:
    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived = 0
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            self._arrived += 1
            if self._arrived >= self._parties:
                self._event.set()

        await self._event.wait()


class _CoordinatedSession:
    def __init__(self, session: AsyncSession, barrier: _AsyncBarrier) -> None:
        self._session = session
        self._barrier = barrier

    async def execute(self, statement, *args, **kwargs):
        result = await self._session.execute(statement, *args, **kwargs)
        if "count(*)" in str(statement):
            await self._barrier.wait()
        return result

    async def commit(self) -> None:
        await self._session.commit()

    async def refresh(self, instance: User) -> None:
        await self._session.refresh(instance)


async def _create_user(session: AsyncSession, telegram_id: int, role: str) -> None:
    session.add(
        User(
            telegram_id=telegram_id,
            first_name=f"User{telegram_id}",
            last_name=None,
            username=f"user{telegram_id}",
            phone_number=None,
            role=role,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_concurrent_admin_demotions_do_not_remove_all_admins():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_maker() as setup_session:
            await _create_user(setup_session, 901, "admin")
            await _create_user(setup_session, 902, "admin")

        barrier = _AsyncBarrier(2)

        async def demote_admin(actor_id: int, target_id: int):
            async with session_maker() as session:
                actor = await session.get(User, actor_id)
                assert actor is not None
                coordinated_session = _CoordinatedSession(session, barrier)
                return await admin_user_service.update_user_role(
                    coordinated_session,
                    actor,
                    target_id,
                    "staff",
                )

        first_result, second_result = await asyncio.gather(
            demote_admin(901, 901),
            demote_admin(902, 902),
            return_exceptions=True,
        )

        async with session_maker() as verification_session:
            admin_count_result = await verification_session.execute(
                select(func.count()).select_from(User).where(User.role == "admin")
            )
            admin_count = int(admin_count_result.scalar_one())

        assert admin_count == 1
        assert sum(isinstance(result, Exception) for result in (first_result, second_result)) == 1
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

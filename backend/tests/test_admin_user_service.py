import asyncio
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.models import Base, User
from app.services import admin_user_service

ADMIN_CONCURRENCY_DATABASE_PREFIX = "admin_concurrency_gate_"
LOOPBACK_DATABASE_HOSTS = {"127.0.0.1", "::1", "localhost"}
SAFE_ADMIN_CONCURRENCY_DATABASE_URLS = (
    "postgresql+asyncpg://gate:secret@127.0.0.1:5432/admin_concurrency_gate_local",
    "postgresql+asyncpg://gate:secret@localhost:5432/admin_concurrency_gate_ci",
    "postgresql+asyncpg://gate:secret@[::1]:5432/admin_concurrency_gate_ipv6",
)
UNSAFE_ADMIN_CONCURRENCY_DATABASE_URLS = (
    "postgresql+asyncpg://gate:secret@db.internal:5432/admin_concurrency_gate_remote",
    "postgresql+asyncpg://gate:secret@127.0.0.1:5432/restaurant_db",
    "postgresql+asyncpg://gate:secret@127.0.0.1:5432/contest-production",
    "postgresql+asyncpg://gate:secret@127.0.0.1:5432/admin_concurrency_gate_",
    "postgresql+asyncpg://gate:secret@127.0.0.1:5432/admin_concurrency_gate_local?host=db.internal",
    "postgresql+asyncpg://gate:secret@127.0.0.1:5432/admin_concurrency_gate_local?database=restaurant_db",
)


def _is_admin_concurrency_gate_database(database_url: str) -> bool:
    url = make_url(database_url)
    database_name = (url.database or "").lower()
    return (
        not url.query
        and (url.host or "").lower() in LOOPBACK_DATABASE_HOSTS
        and database_name.startswith(ADMIN_CONCURRENCY_DATABASE_PREFIX)
        and database_name != ADMIN_CONCURRENCY_DATABASE_PREFIX
    )


@pytest.mark.parametrize("database_url", SAFE_ADMIN_CONCURRENCY_DATABASE_URLS)
def test_admin_concurrency_gate_accepts_loopback_exact_prefix(database_url: str) -> None:
    assert _is_admin_concurrency_gate_database(database_url)


@pytest.mark.parametrize("database_url", UNSAFE_ADMIN_CONCURRENCY_DATABASE_URLS)
def test_admin_concurrency_gate_rejects_unsafe_target(database_url: str) -> None:
    assert not _is_admin_concurrency_gate_database(database_url)


@pytest.mark.parametrize("opt_in", (None, "", "0", "true"))
def test_admin_concurrency_gate_requires_exact_opt_in(opt_in: str | None) -> None:
    with pytest.raises(pytest.skip.Exception, match="RUN_DESTRUCTIVE_POSTGRES_TESTS=1"):
        _require_isolated_test_database(
            SAFE_ADMIN_CONCURRENCY_DATABASE_URLS[0],
            opt_in,
        )


def test_admin_concurrency_gate_fails_explicit_unsafe_target() -> None:
    with pytest.raises(pytest.fail.Exception, match="Refusing destructive schema setup"):
        _require_isolated_test_database(
            UNSAFE_ADMIN_CONCURRENCY_DATABASE_URLS[0],
            "1",
        )


def test_admin_concurrency_gate_allows_explicit_safe_target() -> None:
    assert (
        _require_isolated_test_database(
            SAFE_ADMIN_CONCURRENCY_DATABASE_URLS[0],
            "1",
        )
        is None
    )


def _require_isolated_test_database(
    database_url: str,
    destructive_test_opt_in: str | None,
) -> None:
    if destructive_test_opt_in != "1":
        pytest.skip("Set RUN_DESTRUCTIVE_POSTGRES_TESTS=1 to run this destructive test.")

    if not _is_admin_concurrency_gate_database(database_url):
        pytest.fail(
            "Refusing destructive schema setup outside the loopback "
            f"{ADMIN_CONCURRENCY_DATABASE_PREFIX}<nonce> database gate."
        )


class _AdminRowLockCoordinator:
    def __init__(self) -> None:
        self.first_lock_acquired = asyncio.Event()
        self.second_lock_requested = asyncio.Event()
        self.second_lock_acquired = asyncio.Event()
        self.release_first_lock = asyncio.Event()

    async def before_admin_lock(self, label: str) -> None:
        if label == "second":
            self.second_lock_requested.set()

    async def after_admin_lock(self, label: str) -> None:
        if label == "first":
            self.first_lock_acquired.set()
            await self.release_first_lock.wait()
            return

        self.second_lock_acquired.set()


class _CoordinatedSession:
    def __init__(
        self,
        session: AsyncSession,
        coordinator: _AdminRowLockCoordinator,
        label: str,
    ) -> None:
        self._session = session
        self._coordinator = coordinator
        self._label = label

    async def execute(self, statement, *args, **kwargs):
        if _is_admin_cohort_lock(statement):
            await self._coordinator.before_admin_lock(self._label)
        result = await self._session.execute(statement, *args, **kwargs)
        if _is_admin_cohort_lock(statement):
            await self._coordinator.after_admin_lock(self._label)
        return result

    async def commit(self) -> None:
        await self._session.commit()

    async def refresh(self, instance: User) -> None:
        await self._session.refresh(instance)


def _is_admin_cohort_lock(statement) -> bool:
    sql = str(statement)
    return sql.rstrip().endswith("FOR UPDATE") and "WHERE users.role = :role_1" in sql


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
    _require_isolated_test_database(
        settings.database_url,
        os.getenv("RUN_DESTRUCTIVE_POSTGRES_TESTS"),
    )

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

        coordinator = _AdminRowLockCoordinator()

        async def demote_admin(label: str, actor_id: int, target_id: int):
            async with session_maker() as session:
                actor = await session.get(User, actor_id)
                assert actor is not None
                coordinated_session = _CoordinatedSession(session, coordinator, label)
                return await admin_user_service.update_user_role(
                    coordinated_session,
                    actor,
                    target_id,
                    "staff",
                )

        first_task = asyncio.create_task(demote_admin("first", 901, 901))
        await asyncio.wait_for(coordinator.first_lock_acquired.wait(), timeout=1)

        second_task = asyncio.create_task(demote_admin("second", 902, 902))
        await asyncio.wait_for(coordinator.second_lock_requested.wait(), timeout=1)
        await asyncio.sleep(0.05)

        assert not coordinator.second_lock_acquired.is_set()
        assert not second_task.done()

        coordinator.release_first_lock.set()
        first_result, second_result = await asyncio.gather(
            first_task,
            second_task,
            return_exceptions=True,
        )
        results = (first_result, second_result)
        successful_demotions = [result for result in results if isinstance(result, User)]
        conflicts = [result for result in results if isinstance(result, HTTPException)]

        async with session_maker() as verification_session:
            admin_count_result = await verification_session.execute(
                select(func.count()).select_from(User).where(User.role == "admin")
            )
            admin_count = int(admin_count_result.scalar_one())

        assert admin_count == 1
        assert coordinator.second_lock_acquired.is_set()
        assert len(successful_demotions) == 1
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].detail == "Cannot remove the final admin role."
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

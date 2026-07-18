from pathlib import Path

import pytest

from app import container_entrypoint
from app.main import app
from app.services.telegram_webhook_service import register_telegram_webhook

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"
EXPECTED_UVICORN_COMMAND = [
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--workers",
    "2",
    "--proxy-headers",
    "--forwarded-allow-ips=*",
]


def test_entrypoint_registers_once_before_exec(monkeypatch):
    events: list[object] = []

    async def register_once() -> None:
        events.append("register")

    def exec_once(executable: str, argv: list[str]) -> None:
        events.append((executable, argv))
        raise SystemExit(0)

    monkeypatch.setattr(container_entrypoint, "register_telegram_webhook", register_once)
    monkeypatch.setattr(container_entrypoint.os, "execvp", exec_once)
    with pytest.raises(SystemExit, match="0"):
        container_entrypoint.main()
    assert events == ["register", ("uvicorn", EXPECTED_UVICORN_COMMAND)]


def test_entrypoint_does_not_exec_after_registration_failure(monkeypatch):
    async def fail_registration() -> None:
        raise RuntimeError("telegram_webhook_registration_failed")

    def unexpected_exec(_executable: str, _argv: list[str]) -> None:
        pytest.fail("Uvicorn must not start")

    monkeypatch.setattr(
        container_entrypoint,
        "register_telegram_webhook",
        fail_registration,
    )
    monkeypatch.setattr(container_entrypoint.os, "execvp", unexpected_exec)
    with pytest.raises(RuntimeError, match="telegram_webhook_registration_failed"):
        container_entrypoint.main()


def test_fastapi_workers_do_not_register_telegram_webhook():
    assert register_telegram_webhook not in app.router.on_startup


def test_dockerfile_uses_single_owner_entrypoint():
    source = DOCKERFILE.read_text()
    assert 'CMD ["python", "-m", "app.container_entrypoint"]' in source
    assert 'CMD ["uvicorn"' not in source

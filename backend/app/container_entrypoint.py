import asyncio
import os

from app.services.telegram_webhook_service import register_telegram_webhook

UVICORN_COMMAND = [
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


def main() -> None:
    asyncio.run(register_telegram_webhook())
    os.execvp(UVICORN_COMMAND[0], UVICORN_COMMAND)


if __name__ == "__main__":
    main()

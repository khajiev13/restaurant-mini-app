from urllib.parse import urlsplit

from pydantic_settings import BaseSettings


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_url(value: str) -> str:
    return value.rstrip("/")


def _hostname_from_url(value: str) -> str | None:
    if not value:
        return None

    parsed = urlsplit(value if "://" in value else f"https://{value}")
    return parsed.hostname


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str = ""
    telegram_bot_username: str = "olotsomsa_zakaz_bot"
    public_app_url: str = ""
    public_backend_url: str = ""
    cors_allowed_origins: str = ""
    trusted_hosts: str = ""

    # AliPOS
    alipos_api_client_id: str
    alipos_api_client_secret: str
    alipos_api_base_url: str = "https://web.alipos.uz"
    alipos_restaurant_id: str
    alipos_online_order_payment_id: str = "34badec8-4161-47b0-be80-e11843bc496a"

    # Multicard / Rahmat
    multicard_api_base_url: str = "https://dev-mesh.multicard.uz"
    multicard_application_id: str = ""
    multicard_secret: str = ""
    multicard_store_id: int = 0
    rahmat_payment_timeout_seconds: int = 600
    payment_expiry_check_interval_seconds: int = 30

    # Yandex Maps
    yandex_maps_api_key: str = ""
    yandex_geosuggest_api_key: str = ""

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def public_urls(self) -> list[str]:
        urls = [
            _normalize_url(self.public_app_url),
            _normalize_url(self.public_backend_url),
        ]
        return list(dict.fromkeys(url for url in urls if url))

    @property
    def public_base_url(self) -> str:
        return (self.public_backend_url or self.public_app_url).rstrip("/")

    @property
    def resolved_cors_allowed_origins(self) -> list[str]:
        origins = _split_csv(self.cors_allowed_origins)
        origins.extend(self.public_urls)
        origins.extend(
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:4173",
                "http://127.0.0.1:4173",
            ]
        )
        return list(dict.fromkeys(_normalize_url(origin) for origin in origins if origin))

    @property
    def cors_origin_regex(self) -> str | None:
        uses_trycloudflare = (
            not self.public_urls
            or any("trycloudflare.com" in url for url in self.public_urls)
        )
        return r"^https://[-a-z0-9]+\.trycloudflare\.com$" if uses_trycloudflare else None

    @property
    def resolved_trusted_hosts(self) -> list[str]:
        hosts = _split_csv(self.trusted_hosts)
        hosts.extend(["localhost", "127.0.0.1", "testserver", "backend", "caddy"])

        for url in self.public_urls:
            host = _hostname_from_url(url)
            if host:
                hosts.append(host)

        if not self.public_urls or any("trycloudflare.com" in url for url in self.public_urls):
            hosts.append("*.trycloudflare.com")

        return list(dict.fromkeys(host for host in hosts if host))

    @property
    def multicard_callback_url(self) -> str:
        if not self.public_base_url:
            raise RuntimeError("PUBLIC_APP_URL or PUBLIC_BACKEND_URL must be configured")
        return f"{self.public_base_url}/api/webhooks/multicard/callback"

    def telegram_order_deep_link(self, order_id: str) -> str:
        return f"https://t.me/{self.telegram_bot_username}?startapp=order_{order_id}"


settings = Settings()  # type: ignore[call-arg]

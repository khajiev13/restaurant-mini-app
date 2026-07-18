import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
TELEGRAM_ALLOWED_UPDATES = ["message"]


async def _get_telegram_webhook_info(
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    response = await client.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo",
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError("telegram_get_webhook_info_api_rejected")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("telegram_get_webhook_info_invalid_result")
    return result


def _normalized_allowed_updates(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return sorted(values)


async def register_telegram_webhook() -> None:
    if not settings.public_base_url or not settings.telegram_bot_token:
        return

    webhook_url = f"{settings.public_base_url}/api/webhooks/bot"
    payload: dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": TELEGRAM_ALLOWED_UPDATES,
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    has_configured_secret = bool(settings.telegram_webhook_secret)
    try:
        async with httpx.AsyncClient() as client:
            if not has_configured_secret:
                try:
                    current_info = await _get_telegram_webhook_info(client)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "telegram_webhook_inspection_failed category=request_or_response"
                    )
                else:
                    current_url = current_info.get("url", "")
                    current_allowed_updates = _normalized_allowed_updates(
                        current_info.get("allowed_updates")
                    )
                    expected_allowed_updates = _normalized_allowed_updates(
                        TELEGRAM_ALLOWED_UPDATES
                    )
                    if (
                        current_url == webhook_url
                        and current_allowed_updates == expected_allowed_updates
                    ):
                        logger.info(
                            "Telegram webhook already configured for %s; skipping setWebhook",
                            webhook_url,
                        )
                        return

            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            response_payload = response.json()
            if (
                not isinstance(response_payload, dict)
                or response_payload.get("ok") is not True
            ):
                raise RuntimeError("telegram_set_webhook_api_rejected")
    except Exception:  # noqa: BLE001
        category = "configured_secret" if has_configured_secret else "empty_secret"
        logger.warning(
            "telegram_webhook_registration_failed category=%s",
            category,
        )
        if has_configured_secret:
            raise RuntimeError("telegram_webhook_registration_failed") from None
        return

    logger.info("Telegram webhook registered for %s", webhook_url)

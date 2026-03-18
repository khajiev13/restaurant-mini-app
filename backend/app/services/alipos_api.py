import time

import httpx

from app.config import settings

# Module-level token cache
_token: str | None = None
_token_expires_at: float = 0


async def _get_token() -> str:
    """Get a valid AliPOS access token, refreshing if expired."""
    global _token, _token_expires_at

    if _token and time.time() < _token_expires_at - 60:
        return _token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.alipos_api_base_url}/security/oauth/token",
            data={
                "client_id": settings.alipos_api_client_id,
                "client_secret": settings.alipos_api_client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    _token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 86400)
    return _token


async def _api_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Make an authenticated request to the AliPOS API."""
    token = await _get_token()
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method,
            f"{settings.alipos_api_base_url}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=30,
            follow_redirects=True,
            **kwargs,
        )
        resp.raise_for_status()
        return resp


async def get_menu() -> dict:
    """Fetch the full menu for the configured restaurant."""
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/menu/{settings.alipos_restaurant_id}/composition",
    )
    return resp.json()


async def create_order(order_payload: dict) -> dict:
    """Send an order to AliPOS and return the response."""
    resp = await _api_request(
        "POST",
        "/api/Integration/v1/order",
        json=order_payload,
    )
    return resp.json()


async def get_order_status(alipos_order_id: str) -> dict:
    """Fetch order details from AliPOS."""
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/order/{alipos_order_id}",
    )
    return resp.json()


async def cancel_order(alipos_order_id: str) -> None:
    """Cancel an order in AliPOS."""
    await _api_request(
        "DELETE",
        f"/api/Integration/v1/order/{alipos_order_id}",
    )


async def get_payment_methods() -> list[dict]:
    """Fetch available payment methods."""
    resp = await _api_request(
        "GET",
        "/api/Integration/v1/paymentMethod/all",
    )
    return resp.json()

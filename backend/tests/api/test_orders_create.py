import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.middleware.telegram_auth import create_jwt
from app.models.models import Address, Order, User
from app.services.menu_catalog_service import PricedCart


@pytest.mark.asyncio
async def test_create_order_preserves_item_display_name(client, db_session):
    user = User(
        telegram_id=6201,
        first_name="Customer",
        last_name=None,
        username=None,
        phone_number="+998901112233",
    )
    db_session.add(user)
    await db_session.flush()

    address = Address(
        user_id=user.telegram_id,
        label="Home",
        full_address="Yakkasaray District, Shota Rustaveli 45",
        latitude="41.2995",
        longitude="69.2401",
    )
    db_session.add(address)
    await db_session.commit()

    token = create_jwt(user.telegram_id)
    alipos_order_id = uuid.uuid4()
    with patch(
        "app.routers.orders.alipos_api.create_order",
        new=AsyncMock(return_value={"orderId": str(alipos_order_id)}),
    ), patch(
        "app.routers.orders.alipos_api.get_payment_methods",
        new=AsyncMock(
            return_value=[
                {
                    "id": "59FFAC8D-ACE5-4758-8FB7-6C1F69713C37",
                    "title": "Наличные",
                }
            ]
        ),
    ), patch(
        "app.services.order_service.price_cart",
        new=AsyncMock(
            return_value=PricedCart(
                items=[
                    {
                        "id": "menu-item-1",
                        "name": "Classic Somsa",
                        "quantity": 2.0,
                        "price": 18000.0,
                        "modifications": [],
                    }
                ],
                items_cost=Decimal("36000"),
            )
        ),
    ):
        response = await client.post(
            "/api/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "address_id": str(address.id),
                "items": [
                    {
                        "id": "menu-item-1",
                        "name": "Classic Somsa",
                        "quantity": 2,
                        "price": 18000,
                        "modifications": [],
                    }
                ],
                "phone_number": "+998901112233",
                "payment_method": "cash",
                "discriminator": "delivery",
            },
        )

    assert response.status_code == 201
    assert response.json()["data"]["items"][0]["name"] == "Classic Somsa"

    order = await db_session.get(Order, uuid.UUID(response.json()["data"]["id"]))
    assert order is not None
    assert order.items[0]["name"] == "Classic Somsa"


@pytest.mark.asyncio
async def test_create_order_rejected_response_does_not_expose_alipos_body(
    client,
    db_session,
):
    user = User(
        telegram_id=6202,
        first_name="Customer",
        last_name=None,
        username=None,
        phone_number="+998901112233",
    )
    db_session.add(user)
    await db_session.flush()
    address = Address(
        user_id=user.telegram_id,
        label="Home",
        full_address="Yakkasaray District, Shota Rustaveli 45",
        latitude="41.2995",
        longitude="69.2401",
    )
    db_session.add(address)
    await db_session.commit()

    rejected_response = httpx.Response(
        400,
        json={"detail": "customer-secret"},
        request=httpx.Request("POST", "https://alipos.example/order"),
    )
    alipos_client = Mock()
    alipos_client.request = AsyncMock(return_value=rejected_response)
    alipos_client.__aenter__ = AsyncMock(return_value=alipos_client)
    alipos_client.__aexit__ = AsyncMock(return_value=None)

    token = create_jwt(user.telegram_id)
    with (
        patch(
            "app.routers.orders.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "59FFAC8D-ACE5-4758-8FB7-6C1F69713C37",
                        "title": "Наличные",
                    }
                ]
            ),
        ),
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(
                return_value=PricedCart(
                    items=[
                        {
                            "id": "menu-item-1",
                            "name": "Classic Somsa",
                            "quantity": 2.0,
                            "price": 18000.0,
                            "modifications": [],
                        }
                    ],
                    items_cost=Decimal("36000"),
                )
            ),
        ),
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch(
            "app.services.alipos_api.httpx.AsyncClient",
            return_value=alipos_client,
        ),
    ):
        response = await client.post(
            "/api/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "address_id": str(address.id),
                "items": [
                    {
                        "id": "menu-item-1",
                        "name": "Classic Somsa",
                        "quantity": 2,
                        "price": 18000,
                        "modifications": [],
                    }
                ],
                "phone_number": "+998901112233",
                "payment_method": "cash",
                "discriminator": "delivery",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "AliPOS rejected the order (HTTP 400)"
    assert "customer-secret" not in response.text

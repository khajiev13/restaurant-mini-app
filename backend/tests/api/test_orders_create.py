import asyncio
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.middleware.telegram_auth import create_jwt
from app.models.models import Address, Order, User
from app.routers.orders import create_order as create_order_endpoint
from app.schemas.order import OrderCreate
from app.services import alipos_api
from app.services.menu_catalog_service import PricedCart

CASH_PAYMENT_ID = "59FFAC8D-ACE5-4758-8FB7-6C1F69713C37"
PRICED_CART = PricedCart(
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


async def _delivery_order_request(
    db_session,
    *,
    telegram_id: int,
    client_request_id: uuid.UUID,
) -> tuple[User, dict]:
    user = User(
        telegram_id=telegram_id,
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
    return user, {
        "client_request_id": str(client_request_id),
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
    }


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
    assert response.json()["detail"] == "Could not submit the order to the restaurant"
    assert "AliPOS" not in response.text
    assert "400" not in response.text
    assert "customer-secret" not in response.text


@pytest.mark.asyncio
async def test_create_order_payload_build_error_is_bounded_in_state_logs_and_api(
    client,
    db_session,
    caplog,
):
    user = User(
        telegram_id=6203,
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
    arbitrary_error = "payload-secret-" + "x" * 200

    with (
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
            "app.services.order_service._build_alipos_payload",
            new=AsyncMock(side_effect=RuntimeError(arbitrary_error)),
        ),
        caplog.at_level("INFO", logger="app.services.order_service"),
    ):
        response = await client.post(
            "/api/orders",
            headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
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

    result = await db_session.execute(
        select(Order).where(Order.user_id == user.telegram_id)
    )
    order = result.scalar_one()
    assert response.status_code == 502
    assert response.json()["detail"] == "Could not submit the order to the restaurant"
    assert order.alipos_sync_error == "AliPOS order payload could not be prepared"
    assert arbitrary_error not in response.text
    assert arbitrary_error not in caplog.text
    assert arbitrary_error not in order.alipos_sync_error


@pytest.mark.asyncio
async def test_same_client_request_id_replays_cash_submission_failure_without_provider_retry(
    client,
    db_session,
):
    request_id = uuid.uuid4()
    user, body = await _delivery_order_request(
        db_session,
        telegram_id=6204,
        client_request_id=request_id,
    )
    create = AsyncMock(side_effect=alipos_api.AliPOSRejected(400))
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(return_value=PRICED_CART),
        ),
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": CASH_PAYMENT_ID, "title": "Наличные"}]
            ),
        ),
        patch("app.services.order_service.alipos_api.create_order", new=create),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        headers = {"Authorization": f"Bearer {create_jwt(user.telegram_id)}"}
        first = await client.post("/api/orders", headers=headers, json=body)
        replay = await client.post("/api/orders", headers=headers, json=body)

    result = await db_session.execute(
        select(Order).where(Order.client_request_id == request_id)
    )
    orders = list(result.scalars())
    assert first.status_code == 502
    assert replay.status_code == 502
    assert first.json() == replay.json()
    assert len(orders) == 1
    assert orders[0].alipos_sync_status == "failed"
    assert orders[0].status == "SUBMISSION_FAILED"
    assert orders[0].payment_status is None
    assert orders[0].refund_sync_status is None
    create.assert_awaited_once()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_request_id_integrity_race_winner_replays_failed_result(
    client,
    db_session,
):
    request_id = uuid.uuid4()
    user, body = await _delivery_order_request(
        db_session,
        telegram_id=6205,
        client_request_id=request_id,
    )
    create = AsyncMock(side_effect=alipos_api.AliPOSRejected(400))
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(return_value=PRICED_CART),
        ),
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": CASH_PAYMENT_ID, "title": "Наличные"}]
            ),
        ),
        patch("app.services.order_service.alipos_api.create_order", new=create),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        headers = {"Authorization": f"Bearer {create_jwt(user.telegram_id)}"}
        first = await client.post("/api/orders", headers=headers, json=body)

        winner_result = await db_session.execute(
            select(Order).where(Order.client_request_id == request_id)
        )
        winner = winner_result.scalar_one()
        address = await db_session.get(Address, uuid.UUID(body["address_id"]))
        no_early_winner = Mock()
        no_early_winner.scalar_one_or_none.return_value = None
        selected_address = Mock()
        selected_address.scalar_one_or_none.return_value = address
        integrity_winner = Mock()
        integrity_winner.scalar_one_or_none.return_value = winner
        loser_db = AsyncMock()
        loser_db.add = Mock()
        loser_db.execute.side_effect = [
            no_early_winner,
            selected_address,
            integrity_winner,
        ]
        loser_db.commit.side_effect = IntegrityError(
            "insert",
            {},
            RuntimeError("duplicate"),
        )

        with pytest.raises(HTTPException) as replay:
            await create_order_endpoint(OrderCreate.model_validate(body), user, loser_db)

    assert first.status_code == 502
    assert replay.value.status_code == 502
    assert first.json()["detail"] == replay.value.detail
    loser_db.rollback.assert_awaited_once()
    assert winner.alipos_sync_status == "failed"
    assert winner.status == "SUBMISSION_FAILED"
    create.assert_awaited_once()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_request_id_replay_while_submission_sending_is_not_reported_as_created(
    client,
    db_session,
):
    request_id = uuid.uuid4()
    user, body = await _delivery_order_request(
        db_session,
        telegram_id=6206,
        client_request_id=request_id,
    )
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()

    async def create_after_release(_payload):
        provider_started.set()
        await release_provider.wait()
        return {"orderId": str(uuid.uuid4())}

    create = AsyncMock(side_effect=create_after_release)
    refund = AsyncMock()
    headers = {"Authorization": f"Bearer {create_jwt(user.telegram_id)}"}

    with (
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(return_value=PRICED_CART),
        ),
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": CASH_PAYMENT_ID, "title": "Наличные"}]
            ),
        ),
        patch("app.services.order_service.alipos_api.create_order", new=create),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        first_request = asyncio.create_task(
            client.post("/api/orders", headers=headers, json=body)
        )
        await asyncio.wait_for(provider_started.wait(), timeout=5)
        try:
            replay = await client.post("/api/orders", headers=headers, json=body)
        finally:
            release_provider.set()
        first = await first_request

    result = await db_session.execute(
        select(Order).where(Order.client_request_id == request_id)
    )
    orders = list(result.scalars())
    assert first.status_code == 201
    assert replay.status_code == 409
    assert replay.json() == {
        "detail": {
            "order_id": str(orders[0].id),
            "status": "sending",
        }
    }
    assert len(orders) == 1
    create.assert_awaited_once()
    refund.assert_not_awaited()

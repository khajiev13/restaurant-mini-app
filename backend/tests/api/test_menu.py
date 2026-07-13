from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_menu(client):
    """Test the /menu endpoint correctly retrieves mocked data."""
    mock_menu_data = {
        "categories": [{"id": "c1", "name": "Drinks"}],
        "items": [{"id": "i1", "categoryId": "c1", "name": "Cola", "price": 10.0}],
    }

    for item in mock_menu_data["items"]:
        item.update({"available": True, "availableCount": None})

    with patch(
        "app.routers.menu.get_customer_menu",
        new=AsyncMock(return_value=mock_menu_data),
    ):
        response = await client.get("/api/menu")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["data"]["categories"][0]["name"] == "Drinks"
        assert json_data["data"]["items"][0]["name"] == "Cola"
        assert json_data["data"]["items"][0]["available"] is True

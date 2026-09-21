from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools_ha import HomeAssistantTool, _is_allowed_entity


@pytest.mark.asyncio
async def test_domain_allowlist_filters_light() -> None:
    states = [
        {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {"friendly_name": "Kitchen"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.usd_buy",
            "state": "41.2",
            "attributes": {
                "friendly_name": "USD Buy Cartel",
                "unit_of_measurement": "UAH",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = states
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("tools_ha.httpx.AsyncClient", return_value=mock_client):
        tool = HomeAssistantTool("http://ha.test", "token")
        result = await tool.execute({"query": "usd"}, {})

    assert result["ok"] is True
    assert len(result["states"]) == 1
    assert result["states"][0]["entity_id"] == "sensor.usd_buy"
    assert not _is_allowed_entity("switch.foo")


@pytest.mark.asyncio
async def test_ha_not_configured() -> None:
    tool = HomeAssistantTool("http://ha.test", "")
    result = await tool.execute({"query": "usd"}, {})
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_indoor_temperature_filters_outdoor_and_hardware() -> None:
    states = [
        {
            "entity_id": "sensor.open_meteo_temperature",
            "state": "23.3",
            "attributes": {
                "friendly_name": "Open-Meteo Temperature",
                "device_class": "temperature",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.zhimi_mc2_indoor_temperature",
            "state": "21.5",
            "attributes": {
                "friendly_name": "Mi Air Purifier Indoor Temperature",
                "device_class": "temperature",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.hexs_board_temperature_1",
            "state": "44",
            "attributes": {
                "friendly_name": "HEXS Board temperature 1",
                "device_class": "temperature",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.deerma_jsq2w_temperature",
            "state": "23.0",
            "attributes": {
                "friendly_name": "Xiaomi Smart Humidifier 2 Temperature",
                "device_class": "temperature",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = states
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("tools_ha.httpx.AsyncClient", return_value=mock_client):
        tool = HomeAssistantTool("http://ha.test", "token")
        result = await tool.execute({"query": "indoor"}, {})

    assert result["ok"] is True
    ids = {s["entity_id"] for s in result["states"]}
    assert "sensor.zhimi_mc2_indoor_temperature" in ids
    assert "sensor.deerma_jsq2w_temperature" in ids
    assert "sensor.open_meteo_temperature" not in ids
    assert "sensor.hexs_board_temperature_1" not in ids

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools_ha import HomeAssistantTool, _is_allowed_entity


@pytest.mark.asyncio
async def test_usd_topic_does_not_match_light() -> None:
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


@pytest.mark.asyncio
async def test_usd_topic_excludes_cartel_eur() -> None:
    states = [
        {
            "entity_id": "sensor.cartel_usd_buy",
            "state": "44.7",
            "attributes": {"friendly_name": "Cartel USD Buy", "unit_of_measurement": "UAH"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.cartel_eur_buy",
            "state": "51.65",
            "attributes": {"friendly_name": "Cartel EUR Buy", "unit_of_measurement": "UAH"},
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
    ids = {s["entity_id"] for s in result["states"]}
    assert ids == {"sensor.cartel_usd_buy"}


@pytest.mark.asyncio
async def test_eur_topic_excludes_open_meteo_european_aqi() -> None:
    states = [
        {
            "entity_id": "sensor.cartel_eur_sell",
            "state": "52.0",
            "attributes": {"friendly_name": "Cartel EUR Sell"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.open_meteo_european_aqi",
            "state": "31",
            "attributes": {"friendly_name": "Open-Meteo European AQI"},
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
        result = await tool.execute({"query": "eur"}, {})

    assert result["ok"] is True
    ids = {s["entity_id"] for s in result["states"]}
    assert ids == {"sensor.cartel_eur_sell"}
    assert _is_allowed_entity("switch.foo")
    assert not _is_allowed_entity("not-an-entity")


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


@pytest.mark.asyncio
async def test_all_returns_every_domain() -> None:
    states = [
        {
            "entity_id": "sensor.a",
            "state": "1",
            "attributes": {"friendly_name": "A"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {"friendly_name": "Kitchen"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "binary_sensor.door",
            "state": "off",
            "attributes": {"friendly_name": "Door"},
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
        result = await tool.execute({"query": "all"}, {})

    assert result["ok"] is True
    ids = {s["id"] for s in result["states"]}
    assert ids == {"binary_sensor.door", "light.kitchen", "sensor.a"}


@pytest.mark.asyncio
async def test_pollen_topic_ragweed_and_silam() -> None:
    states = [
        {
            "entity_id": "sensor.open_meteo_ragweed_pollen",
            "state": "109.8",
            "attributes": {"friendly_name": "Open-Meteo Ragweed pollen"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.silam_pollen_home_ragweed",
            "state": "376",
            "attributes": {"friendly_name": "SILAM Pollen - Home Ragweed"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.open_meteo_temperature",
            "state": "23",
            "attributes": {"friendly_name": "Open-Meteo Temperature"},
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "weather.silam_pollen_home_forecast",
            "state": "very_high",
            "attributes": {"friendly_name": "SILAM Pollen Forecast"},
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
        result = await tool.execute({"query": "pollen"}, {})

    assert result["ok"] is True
    ids = {s["entity_id"] for s in result["states"]}
    assert "sensor.open_meteo_ragweed_pollen" in ids
    assert "sensor.silam_pollen_home_ragweed" in ids
    assert "weather.silam_pollen_home_forecast" in ids
    assert "sensor.open_meteo_temperature" not in ids


@pytest.mark.asyncio
async def test_air_topic_pm25() -> None:
    states = [
        {
            "entity_id": "sensor.saveecobot_pm2_5",
            "state": "13.2",
            "attributes": {
                "friendly_name": "SaveEcoBot PM2.5",
                "device_class": "pm25",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.open_meteo_temperature",
            "state": "23",
            "attributes": {"friendly_name": "Temp", "device_class": "temperature"},
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
        result = await tool.execute({"query": "air"}, {})

    assert result["ok"] is True
    ids = {s["entity_id"] for s in result["states"]}
    assert "sensor.saveecobot_pm2_5" in ids
    assert "sensor.open_meteo_temperature" not in ids


@pytest.mark.asyncio
async def test_fuel_excludes_update_switch_and_filters_diesel() -> None:
    states = [
        {
            "entity_id": "sensor.ukr_fuel_socar_dp_plus",
            "state": "104.0",
            "attributes": {
                "friendly_name": "SOCAR ДП+",
                "unit_of_measurement": "грн/л",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "sensor.ukr_fuel_socar_gas",
            "state": "45.5",
            "attributes": {
                "friendly_name": "SOCAR Газ",
                "unit_of_measurement": "грн/л",
            },
            "last_updated": "2026-01-01T00:00:00Z",
        },
        {
            "entity_id": "switch.ukr_fuel_prices_update",
            "state": "off",
            "attributes": {"friendly_name": "Ukrainian Fuel Prices Update"},
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
        result = await tool.execute(
            {"query": "fuel"},
            {"user_text": "а сколько стоит ДП?"},
        )

    assert result["ok"] is True
    names = [s["friendly_name"] for s in result["states"]]
    assert names == ["SOCAR ДП+"]

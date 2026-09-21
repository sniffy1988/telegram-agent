from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent import Agent
from config import Settings
from memory import MemoryStore
from tools import ToolRegistry
from ha_control import HomeAssistantControlClient, PendingHaControl
from tools_ha import HomeAssistantTool
from tools_ha_control import HomeAssistantControlTool


def _settings(
    tmp_path,
    *,
    ha_control_enabled: bool = False,
    catalog_path: Path | None = None,
) -> Settings:
    if catalog_path is None:
        catalog_path = tmp_path / "test_catalog.json"
        catalog_path.write_text(
            '{"allowlist":["light.nochik"],"aliases":{"ночник":"light.nochik"}}',
            encoding="utf-8",
        )
    return Settings(
        telegram_bot_token="x",
        telegram_allowed_chat_ids=frozenset(),
        ollama_url="http://127.0.0.1:11434",
        ollama_model="test",
        ollama_timeout=30.0,
        max_history_messages=6,
        memory_path=tmp_path / "m.json",
        home_assistant_url="http://ha",
        home_assistant_token="t",
        max_search_results=3,
        max_images=2,
        ha_all_entities_limit=500,
        ha_topic_match_limit=25,
        ha_tool_json_max_chars=14000,
        ha_control_enabled=ha_control_enabled,
        ha_control_domains=frozenset({"switch", "light"}),
        ha_control_catalog_path=catalog_path,
    )


@pytest.mark.asyncio
async def test_ha_failure_short_circuit_no_invented_rate(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value={"content": "41.5 UAH"})
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "t")

    async def fail_ha(arguments, context):
        return {"ok": False, "error": "home_assistant_unreachable", "states": []}

    ha.execute = fail_ha  # type: ignore[method-assign]
    reg.register(ha)
    agent = Agent(_settings(tmp_path), memory, ollama, reg)

    result = await agent.handle(1, "какой сейчас курс доллара?")
    assert "Home Assistant" in result.text
    assert "41" not in result.text
    assert "112" not in result.text
    ollama.chat.assert_not_called()


@pytest.mark.asyncio
async def test_pollen_success_short_circuit_factual_list(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value={"content": "hallucinated latin name"})
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "t")

    async def pollen_ok(arguments, context):
        return {
            "ok": True,
            "states": [
                {
                    "entity_id": "sensor.silam_pollen_home_ragweed",
                    "friendly_name": "SILAM Pollen - Home Ragweed",
                    "state": "376",
                    "unit": None,
                },
                {
                    "entity_id": "sensor.open_meteo_ragweed_pollen",
                    "friendly_name": "Open-Meteo Ragweed pollen",
                    "state": "109.8",
                    "unit": None,
                },
            ],
        }

    ha.execute = pollen_ok  # type: ignore[method-assign]
    reg.register(ha)
    agent = Agent(_settings(tmp_path), memory, ollama, reg)
    result = await agent.handle(1, "какая амброзия?")
    assert "376" in result.text
    assert "109.8" in result.text
    assert "SILAM" in result.text
    assert "hallucinated" not in result.text
    ollama.chat.assert_not_called()


@pytest.mark.asyncio
async def test_temperature_routes_ha_failure_short_circuit(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "")

    async def fail_ha(arguments, context):
        return {"ok": False, "error": "home_assistant_not_configured", "states": []}

    ha.execute = fail_ha  # type: ignore[method-assign]
    reg.register(ha)
    agent = Agent(_settings(tmp_path), memory, ollama, reg)

    result = await agent.handle(1, "какая температура сейчас?")
    assert "HOME_ASSISTANT_TOKEN" in result.text
    ollama.chat.assert_not_called()


@pytest.mark.asyncio
async def test_weather_success_short_circuit(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value={"content": "fake 99C"})
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "t")

    async def weather_ok(arguments, context):
        return {
            "ok": True,
            "states": [
                {
                    "entity_id": "sensor.saveecobot_outdoor_temperature",
                    "friendly_name": "SaveEcoBot Outdoor Temperature",
                    "state": "24.5",
                    "unit": "°C",
                },
            ],
        }

    ha.execute = weather_ok  # type: ignore[method-assign]
    reg.register(ha)
    agent = Agent(_settings(tmp_path), memory, ollama, reg)
    result = await agent.handle(1, "какая температура?")
    assert "24.5" in result.text
    assert "fake" not in result.text
    ollama.chat.assert_not_called()


@pytest.mark.asyncio
async def test_usd_success_short_circuit(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value={"content": "45.5"})
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "t")

    async def usd_ok(arguments, context):
        return {
            "ok": True,
            "states": [
                {
                    "entity_id": "sensor.cartel_usd_buy",
                    "friendly_name": "Cartel USD Buy",
                    "state": "44.7",
                    "unit": "UAH",
                },
            ],
        }

    ha.execute = usd_ok  # type: ignore[method-assign]
    reg.register(ha)
    agent = Agent(_settings(tmp_path), memory, ollama, reg)
    result = await agent.handle(1, "курс доллара")
    assert "44.7" in result.text
    ollama.chat.assert_not_called()


@pytest.mark.asyncio
async def test_ha_control_prepare_returns_pending(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    ollama.chat = AsyncMock(
        return_value={
            "tool_calls": [
                {
                    "function": {
                        "name": "ha_control",
                        "arguments": {
                            "entity_id": "switch.lamp",
                            "action": "turn_off",
                        },
                    }
                }
            ]
        }
    )
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "t")

    async def ha_no_route(arguments, context):
        return {"ok": False, "error": "no_matching_entities", "states": []}

    ha.execute = ha_no_route  # type: ignore[method-assign]
    reg.register(ha)
    ctrl = HomeAssistantControlClient(
        "http://ha",
        "t",
        allowed_domains=frozenset({"switch"}),
    )
    ctrl_tool = HomeAssistantControlTool(ctrl)
    pending = PendingHaControl(
        entity_id="switch.lamp",
        domain="switch",
        service="turn_off",
        friendly_name="Lamp",
    )

    async def prepare_ok(arguments, context):
        return {"ok": True, "pending": pending}

    ctrl_tool.execute = prepare_ok  # type: ignore[method-assign]
    reg.register(ctrl_tool)
    agent = Agent(_settings(tmp_path, ha_control_enabled=True), memory, ollama, reg)
    result = await agent.handle(1, "нужно выключить лампу в спальне")
    assert result.pending_ha_control == pending
    assert "Lamp" in result.text
    assert "Да" in result.text or "«Да»" in result.text


@pytest.mark.asyncio
async def test_control_intent_disabled_short_circuit(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value={"content": "I cannot control devices"})
    reg = ToolRegistry()
    reg.register(HomeAssistantTool("http://ha", "t"))
    agent = Agent(_settings(tmp_path, ha_control_enabled=False), memory, ollama, reg)
    result = await agent.handle(1, "включи ночник")
    assert "HA_CONTROL_ENABLED" in result.text
    ollama.chat.assert_not_called()


@pytest.mark.asyncio
async def test_control_intent_finds_device_and_pending(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "m.json")
    ollama = AsyncMock()
    reg = ToolRegistry()
    ha = HomeAssistantTool("http://ha", "t")

    async def ha_search(arguments, context):
        q = str(arguments.get("query", ""))
        if q == "light.nochik":
            return {
                "ok": True,
                "states": [
                    {
                        "entity_id": "light.nochik",
                        "friendly_name": "Ночник",
                        "state": "off",
                        "unit": None,
                    }
                ],
            }
        return {"ok": False, "error": "no_matching_entities", "states": []}

    ha.execute = ha_search  # type: ignore[method-assign]
    reg.register(ha)
    ctrl = HomeAssistantControlClient(
        "http://ha",
        "t",
        allowed_domains=frozenset({"light", "switch"}),
    )
    ctrl_tool = HomeAssistantControlTool(ctrl)
    pending = PendingHaControl(
        entity_id="light.nochik",
        domain="light",
        service="turn_on",
        friendly_name="Ночник",
    )

    async def prepare_ok(arguments, context):
        return {"ok": True, "pending": pending}

    ctrl_tool.execute = prepare_ok  # type: ignore[method-assign]
    reg.register(ctrl_tool)
    agent = Agent(_settings(tmp_path, ha_control_enabled=True), memory, ollama, reg)
    result = await agent.handle(1, "включи ночник")

    assert result.pending_ha_control is not None
    assert "Ночник" in result.text
    ollama.chat.assert_not_called()

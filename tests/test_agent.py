from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agent import Agent
from config import Settings
from memory import MemoryStore
from tools import ToolRegistry
from tools_ha import HomeAssistantTool


def _settings(tmp_path) -> Settings:
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

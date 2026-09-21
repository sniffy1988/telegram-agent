from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_control import (
    HomeAssistantControlClient,
    PendingHaControl,
    normalize_action,
)
from tools_ha_control import HomeAssistantControlTool


def test_normalize_action_switch() -> None:
    assert normalize_action("off", "switch") == "turn_off"
    assert normalize_action("turn_on", "light") == "turn_on"
    assert normalize_action("pause", "switch") is None
    assert normalize_action("return_to_base", "vacuum") == "return_to_base"


@pytest.mark.asyncio
async def test_prepare_ok() -> None:
    client = HomeAssistantControlClient(
        "http://ha",
        "token",
        allowed_domains=frozenset({"switch"}),
    )
    state = {
        "entity_id": "switch.kitchen",
        "attributes": {"friendly_name": "Kitchen"},
    }
    with patch.object(client, "fetch_state", AsyncMock(return_value=state)):
        result = await client.prepare("switch.kitchen", "toggle")
    assert result["ok"] is True
    pending = result["pending"]
    assert isinstance(pending, PendingHaControl)
    assert pending.service == "toggle"
    assert pending.friendly_name == "Kitchen"


@pytest.mark.asyncio
async def test_prepare_domain_not_allowed() -> None:
    client = HomeAssistantControlClient(
        "http://ha",
        "token",
        allowed_domains=frozenset({"light"}),
    )
    result = await client.prepare("switch.kitchen", "turn_on")
    assert result == {"ok": False, "error": "domain_not_allowed"}


@pytest.mark.asyncio
async def test_apply_posts_service() -> None:
    client = HomeAssistantControlClient(
        "http://ha",
        "token",
        allowed_domains=frozenset({"switch"}),
    )
    pending = PendingHaControl(
        entity_id="switch.kitchen",
        domain="switch",
        service="turn_off",
        friendly_name="Kitchen",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = None

    with patch("ha_control.httpx.AsyncClient", return_value=mock_cm):
        result = await client.apply(pending)
    assert result == {"ok": True}
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args
    assert "switch/turn_off" in call_kwargs.args[0]
    assert call_kwargs.kwargs["json"] == {"entity_id": "switch.kitchen"}


@pytest.mark.asyncio
async def test_tool_execute_confirmed_apply() -> None:
    client = HomeAssistantControlClient(
        "http://ha",
        "t",
        allowed_domains=frozenset({"switch"}),
    )
    pending = PendingHaControl(
        entity_id="switch.x",
        domain="switch",
        service="turn_on",
        friendly_name="X",
    )
    tool = HomeAssistantControlTool(client)
    mock_apply = AsyncMock(return_value={"ok": True})
    with patch.object(client, "apply", mock_apply):
        out = await tool.execute(
            {},
            {"confirmed_apply": True, "pending_ha_control": pending},
        )
    assert out == {"ok": True}
    mock_apply.assert_awaited_once_with(pending)

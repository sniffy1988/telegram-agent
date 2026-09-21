from __future__ import annotations

from typing import Any

from ha_control import HomeAssistantControlClient


class HomeAssistantControlTool:
    name = "ha_control"
    description = (
        "Control Home Assistant devices (lights, switches, fan, humidifier, vacuum). "
        "Requires user confirmation in Telegram before running."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "Home Assistant entity id, e.g. switch.kitchen",
            },
            "action": {
                "type": "string",
                "description": (
                    "turn_on, turn_off, toggle, start, stop, pause, return_to_base"
                ),
            },
        },
        "required": ["entity_id", "action"],
    }

    def __init__(self, client: HomeAssistantControlClient) -> None:
        self.client = client

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        if context.get("confirmed_apply"):
            pending = context.get("pending_ha_control")
            if pending is None:
                return {"ok": False, "error": "missing_pending"}
            result = await self.client.apply(pending)
            return result
        entity_id = str(arguments.get("entity_id", "")).strip()
        action = str(arguments.get("action", "")).strip()
        return await self.client.prepare(entity_id, action)

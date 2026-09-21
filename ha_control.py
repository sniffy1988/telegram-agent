from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_CONTROL_DOMAINS = frozenset(
    {"light", "switch", "fan", "humidifier", "vacuum", "input_boolean"}
)

DOMAIN_ACTIONS: dict[str, frozenset[str]] = {
    "light": frozenset({"turn_on", "turn_off", "toggle"}),
    "switch": frozenset({"turn_on", "turn_off", "toggle"}),
    "fan": frozenset({"turn_on", "turn_off", "toggle"}),
    "input_boolean": frozenset({"turn_on", "turn_off", "toggle"}),
    "humidifier": frozenset({"turn_on", "turn_off", "toggle"}),
    "vacuum": frozenset({"start", "stop", "pause", "return_to_base"}),
}

ACTION_ALIASES = {
    "on": "turn_on",
    "off": "turn_off",
    "enable": "turn_on",
    "disable": "turn_off",
    "start": "start",
    "stop": "stop",
}


def entity_domain(entity_id: str) -> str:
    if "." not in entity_id:
        return ""
    return entity_id.split(".", 1)[0]


def normalize_action(action: str, domain: str) -> str | None:
    a = action.strip().lower().replace("-", "_")
    a = ACTION_ALIASES.get(a, a)
    allowed = DOMAIN_ACTIONS.get(domain)
    if not allowed or a not in allowed:
        return None
    return a


@dataclass(frozen=True, slots=True)
class PendingHaControl:
    entity_id: str
    domain: str
    service: str
    friendly_name: str


class HomeAssistantControlClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        allowed_domains: frozenset[str],
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.allowed_domains = allowed_domains
        self.timeout = timeout

    async def fetch_state(self, entity_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/states/{entity_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.warning("[ha_control] state fetch failed %s: %s", entity_id, exc)
            return None

    async def prepare(self, entity_id: str, action: str) -> dict[str, Any]:
        if not self.token:
            return {"ok": False, "error": "home_assistant_not_configured"}
        eid = entity_id.strip()
        domain = entity_domain(eid)
        if domain not in self.allowed_domains:
            return {"ok": False, "error": "domain_not_allowed"}
        service = normalize_action(action, domain)
        if not service:
            return {"ok": False, "error": "action_not_allowed"}
        state = await self.fetch_state(eid)
        if state is None:
            return {"ok": False, "error": "entity_not_found"}
        attrs = state.get("attributes") or {}
        name = str(attrs.get("friendly_name") or eid)
        pending = PendingHaControl(
            entity_id=eid,
            domain=domain,
            service=service,
            friendly_name=name,
        )
        return {"ok": True, "pending": pending}

    async def apply(self, pending: PendingHaControl) -> dict[str, Any]:
        url = f"{self.base_url}/api/services/{pending.domain}/{pending.service}"
        payload = {"entity_id": pending.entity_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=payload,
                )
            if resp.status_code >= 400:
                logger.warning(
                    "[ha_control] POST %s HTTP %s", url, resp.status_code
                )
                return {
                    "ok": False,
                    "error": f"home_assistant_http_{resp.status_code}",
                }
            logger.info(
                "[ha_control] applied %s.%s entity=%s",
                pending.domain,
                pending.service,
                pending.entity_id,
            )
            return {"ok": True}
        except httpx.HTTPError as exc:
            logger.warning("[ha_control] apply failed: %s", exc)
            return {"ok": False, "error": "home_assistant_unreachable"}

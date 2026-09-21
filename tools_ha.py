from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = frozenset(
    {"sensor", "binary_sensor", "weather", "number", "climate"}
)

# Not room air — outdoor, forecast, or device/hardware probes.
_NON_INDOOR_TEMP_MARKERS = (
    "open_meteo",
    "saveecobot",
    "outdoor",
    "weather.",
    "cpu",
    "hex",
    "board",
    "battery",
    "deltapro",
    "soil",
    "backup",
    "l009",
    "cap_ax",
    "router",
    "uptime",
    "voltage",
    "disk",
    "memory",
    "usage",
)


def _entity_domain(entity_id: str) -> str:
    if "." not in entity_id:
        return ""
    return entity_id.split(".", 1)[0]


def _is_allowed_entity(entity_id: str) -> bool:
    return _entity_domain(entity_id) in ALLOWED_DOMAINS


def _is_non_indoor_temperature(entity_id: str, blob: str) -> bool:
    return any(m in entity_id or m in blob for m in _NON_INDOOR_TEMP_MARKERS)


def _is_indoor_temperature_state(st: dict[str, Any]) -> bool:
    eid = str(st.get("entity_id", ""))
    attrs = st.get("attributes") or {}
    fname = str(attrs.get("friendly_name", "")).lower()
    blob = f"{eid} {fname}".lower()
    domain = _entity_domain(eid)
    if domain == "climate":
        return attrs.get("current_temperature") is not None
    if domain != "sensor":
        return False
    if attrs.get("device_class") != "temperature":
        return False
    if _is_non_indoor_temperature(eid.lower(), blob):
        return False
    indoor_hints = (
        "indoor",
        "комнат",
        "room",
        "bedroom",
        "living",
        "kitchen",
        "спальн",
        "вітальн",
        "кухн",
        "humidifier",
        "увлажн",
        "purifier",
        "очист",
        "zhimi",
        "deerma",
        "environment",
    )
    return any(h in blob for h in indoor_hints) or "indoor" in eid


def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
    attrs = state.get("attributes") or {}
    unit = attrs.get("unit_of_measurement") or attrs.get("native_unit_of_measurement")
    eid = str(state.get("entity_id") or "")
    display_state = state.get("state")
    if _entity_domain(eid) == "climate":
        ct = attrs.get("current_temperature")
        if ct is not None:
            display_state = ct
            unit = unit or "°C"
    return {
        "entity_id": state.get("entity_id"),
        "friendly_name": attrs.get("friendly_name") or state.get("entity_id"),
        "state": display_state,
        "unit": unit,
        "last_updated": state.get("last_updated"),
    }


class HomeAssistantTool:
    name = "ha_query"
    description = (
        "Read current Home Assistant sensor/weather/number states. "
        "Use for weather, fuel prices, USD/EUR exchange rates, and home facts."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Entity id, friendly name fragment, or topic: weather, indoor, fuel, usd, eur",
            }
        },
        "required": ["query"],
    }

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"ok": False, "error": "empty_query", "states": []}
        if not self.token:
            logger.warning("[ha] skipped: HOME_ASSISTANT_TOKEN not configured")
            return {
                "ok": False,
                "error": "home_assistant_not_configured",
                "states": [],
            }
        try:
            url = f"{self.base_url}/api/states"
            logger.info("[ha] GET %s query=%r", url, query)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"Authorization": f"Bearer {self.token}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code >= 400:
                    logger.warning("[ha] HTTP %s from %s", resp.status_code, url)
                    return {
                        "ok": False,
                        "error": f"home_assistant_http_{resp.status_code}",
                        "states": [],
                    }
                all_states = resp.json()
        except httpx.TimeoutException:
            logger.warning("[ha] timeout url=%s", self.base_url)
            return {"ok": False, "error": "home_assistant_timeout", "states": []}
        except httpx.RequestError as exc:
            logger.warning("[ha] unreachable url=%s err=%s", self.base_url, exc)
            return {"ok": False, "error": "home_assistant_unreachable", "states": []}

        if not isinstance(all_states, list):
            return {"ok": False, "error": "invalid_home_assistant_response", "states": []}

        filtered: list[dict[str, Any]] = []
        for st in all_states:
            if not isinstance(st, dict):
                continue
            eid = st.get("entity_id")
            if not isinstance(eid, str) or not _is_allowed_entity(eid):
                continue
            filtered.append(st)

        q_lower = query.lower()
        topic_keywords = {
            "indoor": (
                "indoor",
                "inside",
                "комнат",
                "помещен",
                "в доме",
                "в квартире",
                "внутри",
                "bedroom",
                "living",
                "kitchen",
            ),
            "weather": (
                "weather",
                "open_meteo",
                "temperature",
                "temperatur",
                "погод",
                "температур",
                "градус",
            ),
            "fuel": ("fuel", "ukr_fuel", "азс", "бензин", "дизел", "socar", "wog", "okko"),
            "usd": ("usd", "dollar", "долар", "cartel", "obmenka"),
            "eur": ("eur", "euro", "євро", "eur/usd"),
        }
        topic: str | None = None
        topic_order = ("indoor", "weather", "fuel", "usd", "eur")
        for t in topic_order:
            kws = topic_keywords[t]
            if q_lower == t or any(k in q_lower for k in kws):
                topic = t
                break

        matches: list[dict[str, Any]] = []
        for st in filtered:
            eid = st.get("entity_id", "")
            attrs = st.get("attributes") or {}
            fname = str(attrs.get("friendly_name", "")).lower()
            blob = f"{eid} {fname}".lower()
            if topic == "indoor" and _is_indoor_temperature_state(st):
                matches.append(_compact_state(st))
            elif topic == "weather" and (
                eid.startswith("weather.")
                or "saveecobot_outdoor" in eid
                or (
                    eid.startswith("sensor.")
                    and "open_meteo" in eid
                    and "soil" not in eid
                    and attrs.get("device_class") == "temperature"
                    and eid.endswith("_temperature")
                )
                or (
                    eid.startswith("sensor.")
                    and "saveecobot" in eid
                    and "outdoor" in blob
                )
            ):
                matches.append(_compact_state(st))
            elif topic == "fuel" and (
                "fuel" in eid or "ukr_fuel" in eid or any(x in blob for x in topic_keywords["fuel"])
            ):
                matches.append(_compact_state(st))
            elif topic == "usd" and any(x in blob for x in topic_keywords["usd"]):
                matches.append(_compact_state(st))
            elif topic == "eur" and any(x in blob for x in topic_keywords["eur"]):
                matches.append(_compact_state(st))
            elif query in eid or q_lower in fname or q_lower in eid:
                matches.append(_compact_state(st))

        if not matches and "." in query:
            eid = query.strip()
            if _is_allowed_entity(eid):
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        headers = {"Authorization": f"Bearer {self.token}"}
                        resp = await client.get(
                            f"{self.base_url}/api/states/{eid}", headers=headers
                        )
                        if resp.status_code == 200:
                            st = resp.json()
                            if isinstance(st, dict) and _is_allowed_entity(eid):
                                matches.append(_compact_state(st))
                        else:
                            return {
                                "ok": False,
                                "error": f"entity_not_found_or_denied",
                                "states": [],
                            }
                except httpx.RequestError:
                    return {
                        "ok": False,
                        "error": "home_assistant_unreachable",
                        "states": [],
                    }
            else:
                return {
                    "ok": False,
                    "error": "entity_domain_not_allowed",
                    "states": [],
                }

        if not matches:
            logger.info(
                "[ha] no matches topic=%s query=%r allowlisted_states=%s",
                topic,
                query,
                len(filtered),
            )
            return {"ok": False, "error": "no_matching_entities", "states": []}

        logger.info(
            "[ha] matched %s entities (topic=%s): %s",
            len(matches),
            topic,
            [m.get("entity_id") for m in matches[:5]],
        )
        return {"ok": True, "states": matches[:15]}

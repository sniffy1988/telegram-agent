from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ha_topics import (
    TOPIC_KEYWORDS,
    entity_matches_eur,
    entity_matches_usd,
    fuel_kinds_from_text,
    fuel_product_kind,
    resolve_tool_topic,
)

logger = logging.getLogger(__name__)

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

_ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$", re.I)


def _entity_domain(entity_id: str) -> str:
    if "." not in entity_id:
        return ""
    return entity_id.split(".", 1)[0]


def _is_allowed_entity(entity_id: str) -> bool:
    """Read-only: any Home Assistant entity id (all domains)."""
    return bool(_ENTITY_ID_RE.match(entity_id.strip()))


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


def _is_air_quality_state(st: dict[str, Any]) -> bool:
    eid = str(st.get("entity_id", "")).lower()
    attrs = st.get("attributes") or {}
    fname = str(attrs.get("friendly_name", "")).lower()
    blob = f"{eid} {fname}"
    dc = str(attrs.get("device_class") or "").lower()
    if dc in ("pm25", "pm10", "aqi", "humidity"):
        return True
    if any(x in blob for x in ("pm2", "pm10", "aqi", "humidity", "saveecobot_outdoor_humidity")):
        return True
    if "open_meteo" in eid and any(
        x in eid for x in ("pm2", "pm10", "european_aqi", "relative_humidity")
    ):
        return True
    if "zhimi" in eid and ("pm25" in eid or "relative_humidity" in eid):
        return True
    return False


_FUEL_NON_PRICE_MARKERS = (
    "prices update",
    "price update",
    "fuel prices update",
    "ukrainian fuel prices update",
)

_FUEL_BLOB_KEYWORDS = tuple(
    k for k in TOPIC_KEYWORDS["fuel"] if k not in ("fuel", "ukr_fuel")
)


def _parse_numeric_state(state: Any) -> float | None:
    if state is None:
        return None
    s = str(state).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _is_fuel_price_state(st: dict[str, Any]) -> bool:
    eid = str(st.get("entity_id", "")).lower()
    domain = _entity_domain(eid)
    if domain in ("automation", "script", "scene", "update"):
        return False
    attrs = st.get("attributes") or {}
    fname = str(attrs.get("friendly_name", "")).lower()
    blob = f"{eid} {fname}"
    if any(m in blob for m in _FUEL_NON_PRICE_MARKERS):
        return False
    if fname.endswith(" update") or eid.endswith("_update"):
        return False
    unit = str(
        attrs.get("unit_of_measurement")
        or attrs.get("native_unit_of_measurement")
        or ""
    ).lower()
    if any(x in unit for x in ("грн", "uah", "₴", "/l", "л")):
        return True
    if _parse_numeric_state(st.get("state")) is not None:
        return True
    if domain == "switch" and str(st.get("state", "")).lower() in ("on", "off"):
        return False
    return False


def _is_fuel_entity_candidate(st: dict[str, Any]) -> bool:
    eid = str(st.get("entity_id", "")).lower()
    attrs = st.get("attributes") or {}
    fname = str(attrs.get("friendly_name", "")).lower()
    blob = f"{eid} {fname}"
    if "ukr_fuel" in eid or "ukr_fuel" in blob:
        return True
    if any(k in blob for k in _FUEL_BLOB_KEYWORDS):
        return True
    return "fuel" in eid and "update" not in eid


def _filter_fuel_matches(
    matches: list[dict[str, Any]], user_text: str
) -> list[dict[str, Any]]:
    kinds = fuel_kinds_from_text(user_text)
    if not kinds:
        return matches
    filtered: list[dict[str, Any]] = []
    for m in matches:
        name = str(m.get("friendly_name") or m.get("n") or "")
        eid = str(m.get("entity_id") or m.get("id") or "")
        kind = fuel_product_kind(name, eid)
        if kind in kinds:
            filtered.append(m)
    return filtered if filtered else matches


def _is_pollen_state(st: dict[str, Any]) -> bool:
    eid = str(st.get("entity_id", "")).lower()
    attrs = st.get("attributes") or {}
    fname = str(attrs.get("friendly_name", "")).lower()
    blob = f"{eid} {fname}"
    if "pollen" in blob or "ragweed" in blob or "амброз" in blob:
        return True
    if "silam" in blob and ("pollen" in blob or "ragweed" in blob or "mugwort" in blob):
        return True
    if eid.startswith("weather.") and "pollen" in eid:
        return True
    return False


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


def _compact_state_minimal(state: dict[str, Any]) -> dict[str, Any]:
    attrs = state.get("attributes") or {}
    name = str(attrs.get("friendly_name") or state.get("entity_id") or "")[:48]
    return {
        "id": state.get("entity_id"),
        "n": name,
        "v": state.get("state"),
    }


class HomeAssistantTool:
    name = "ha_query"
    description = (
        "Read current Home Assistant entity states (read-only, all domains). "
        "Topics: all, weather, indoor, air, pollen, fuel, usd, eur; or entity id / name fragment."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Entity id, friendly name fragment, or topic: "
                    "all, weather, indoor, air, pollen, fuel, usd, eur"
                ),
            }
        },
        "required": ["query"],
    }

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        *,
        all_entities_limit: int = 500,
        topic_match_limit: int = 25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.all_entities_limit = max(1, all_entities_limit)
        self.topic_match_limit = max(1, topic_match_limit)

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
        topic = resolve_tool_topic(query)
        if _is_allowed_entity(query.strip()):
            topic = None
        topic_keywords = TOPIC_KEYWORDS

        use_minimal = topic == "all"
        matches: list[dict[str, Any]] = []
        for st in filtered:
            eid = st.get("entity_id", "")
            attrs = st.get("attributes") or {}
            fname = str(attrs.get("friendly_name", "")).lower()
            blob = f"{eid} {fname}".lower()
            compact = _compact_state_minimal if use_minimal else _compact_state
            if topic == "all":
                matches.append(compact(st))
            elif topic == "indoor" and _is_indoor_temperature_state(st):
                matches.append(compact(st))
            elif topic == "pollen" and _is_pollen_state(st):
                matches.append(compact(st))
            elif topic == "air" and _is_air_quality_state(st):
                matches.append(compact(st))
            elif topic == "weather" and (
                (eid.startswith("weather.") and "pollen" not in eid)
                or "saveecobot_outdoor" in eid
                or (
                    eid.startswith("sensor.")
                    and "open_meteo" in eid
                    and "soil" not in eid
                    and "pollen" not in eid
                    and attrs.get("device_class") == "temperature"
                    and eid.endswith("_temperature")
                )
                or (
                    eid.startswith("sensor.")
                    and "saveecobot" in eid
                    and "outdoor" in blob
                )
            ):
                matches.append(compact(st))
            elif topic == "fuel" and _is_fuel_entity_candidate(st) and _is_fuel_price_state(st):
                matches.append(compact(st))
            elif topic == "usd" and entity_matches_usd(str(eid)):
                matches.append(compact(st))
            elif topic == "eur" and entity_matches_eur(str(eid)):
                matches.append(compact(st))
            elif topic is None and (
                query in eid or q_lower in fname or q_lower in eid
            ):
                matches.append(compact(st))

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
                                fn = _compact_state_minimal if use_minimal else _compact_state
                                matches.append(fn(st))
                        else:
                            return {
                                "ok": False,
                                "error": "entity_not_found_or_denied",
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
                    "error": "invalid_entity_id",
                    "states": [],
                }

        if not matches:
            logger.info(
                "[ha] no matches topic=%s query=%r states_in_ha=%s",
                topic,
                query,
                len(filtered),
            )
            return {"ok": False, "error": "no_matching_entities", "states": []}

        if topic == "fuel":
            user_text = str(context.get("user_text") or context.get("caption") or "")
            matches = _filter_fuel_matches(matches, user_text)

        matches.sort(key=lambda m: str(m.get("entity_id") or m.get("id", "")))
        if topic == "all":
            limit = self.all_entities_limit
        elif topic:
            limit = self.topic_match_limit
        else:
            limit = self.topic_match_limit
        page = matches[:limit]
        logger.info(
            "[ha] matched %s entities (topic=%s, returned=%s): %s",
            len(matches),
            topic,
            len(page),
            [
                m.get("entity_id") or m.get("id")
                for m in page[:5]
            ],
        )
        out: dict[str, Any] = {"ok": True, "states": page}
        if topic == "all" and len(matches) > limit:
            out["total"] = len(matches)
            out["truncated"] = True
        return out

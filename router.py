from __future__ import annotations

import re
from dataclasses import dataclass

from ha_topics import (
    ENTITY_ID_RE,
    FOLLOWUP_OUTDOOR,
    FOLLOWUP_PREFIX,
    FOLLOWUP_REPEAT,
    FUEL_ROUTE,
    PRIMARY_ROUTE_PATTERNS,
    fx_ha_topics_from_text,
    last_ha_topic_from_history,
    message_mentions_fuel,
)

ChatTurn = dict[str, str]


@dataclass(frozen=True, slots=True)
class RoutedToolCall:
    name: str
    arguments: dict[str, str]


def _primary_ha_topic(lower: str) -> str | None:
    for topic, pattern in PRIMARY_ROUTE_PATTERNS:
        if pattern.search(lower):
            return topic
    return None


def _entity_ha_call(text: str) -> RoutedToolCall | None:
    m = ENTITY_ID_RE.search(text)
    if m:
        return RoutedToolCall("ha_query", {"query": m.group(1)})
    return None


def route_tools(
    text: str,
    *,
    has_photo: bool,
) -> list[RoutedToolCall]:
    """Deterministic tool routing before LLM (RU + UK + EN)."""
    calls: list[RoutedToolCall] = []
    lower = text.lower().strip()

    if has_photo:
        calls.append(RoutedToolCall("reverse_image", {}))

    primary = _primary_ha_topic(lower)
    if primary:
        calls.append(RoutedToolCall("ha_query", {"query": primary}))
    else:
        entity_call = _entity_ha_call(text)
        if entity_call:
            calls.append(entity_call)

    # Additional HA themes (can combine with primary).
    if FUEL_ROUTE.search(lower):
        if not any(c.arguments.get("query") == "fuel" for c in calls if c.name == "ha_query"):
            calls.append(RoutedToolCall("ha_query", {"query": "fuel"}))

    for fx_topic in fx_ha_topics_from_text(lower):
        if not any(
            c.name == "ha_query" and c.arguments.get("query") == fx_topic for c in calls
        ):
            calls.append(RoutedToolCall("ha_query", {"query": fx_topic}))

    if re.search(
        r"\b(знайди|search|find|google|новини|news|lookup|шукай)\b", lower
    ):
        q = text.strip()
        for prefix in ("знайди", "find", "search for", "search"):
            if lower.startswith(prefix):
                q = text[len(prefix) :].strip(" :")
                break
        if q:
            calls.append(RoutedToolCall("web_search", {"query": q}))

    if re.search(
        r"\b(картинк|image|photo|picture|фото|зображен)\b", lower
    ) and not has_photo:
        q = text.strip()
        calls.append(RoutedToolCall("image_search", {"query": q}))

    deduped: list[RoutedToolCall] = []
    seen: set[tuple[str, str]] = set()
    for c in calls:
        key = (c.name, str(sorted(c.arguments.items())))
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    return deduped[:4]


def _is_short_followup(text: str) -> bool:
    t = text.strip()
    if len(t) > 45:
        return False
    if not t.endswith("?"):
        return False
    return bool(FOLLOWUP_PREFIX.match(t) or FOLLOWUP_REPEAT.search(t))


def _followup_carries_same_topic(lower: str) -> bool:
    """«а сейчас?» / «а евро?» — да; «а сколько стоит ДП?» — нет."""
    rest = FOLLOWUP_PREFIX.sub("", lower).strip() if FOLLOWUP_PREFIX.match(lower) else lower
    if message_mentions_fuel(lower) or message_mentions_fuel(rest):
        return False
    if re.search(r"(сколько|скільки|ціна|цена|стоит|стоим|кошту)", rest):
        return False
    if FOLLOWUP_REPEAT.search(lower) or FOLLOWUP_REPEAT.search(rest):
        return True
    if len(rest) <= 18 and re.fullmatch(
        r"(евро|євро|eur|доллар|долар|usd|на\s+улице\??|снаружи\??)\??",
        rest,
        re.I,
    ):
        return True
    return len(rest) <= 12


def _contextual_ha_topic(text: str, history: list[ChatTurn]) -> str | None:
    lower = text.lower().strip()
    if message_mentions_fuel(lower):
        return "fuel"
    if re.search(r"(евро|євро|euro|\beur\b)", lower):
        return "eur"
    if re.search(r"(доллар|долар|dollar|\busd\b)", lower):
        return "usd"
    if FOLLOWUP_OUTDOOR.search(lower):
        return "weather"
    last = last_ha_topic_from_history(history)
    if not last:
        return None
    if FOLLOWUP_REPEAT.search(lower) and _followup_carries_same_topic(lower):
        return last
    if FOLLOWUP_PREFIX.match(lower) and _followup_carries_same_topic(lower):
        return last
    return None


def route_tools_with_context(
    text: str,
    *,
    has_photo: bool,
    history: list[ChatTurn],
) -> list[RoutedToolCall]:
    calls = route_tools(text, has_photo=has_photo)
    has_ha = any(c.name == "ha_query" for c in calls)
    if has_ha or not history:
        return calls
    if not _is_short_followup(text):
        return calls
    topic = _contextual_ha_topic(text, history)
    if not topic:
        return calls
    return [RoutedToolCall("ha_query", {"query": topic}), *calls][:4]

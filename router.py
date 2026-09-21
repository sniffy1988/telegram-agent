from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoutedToolCall:
    name: str
    arguments: dict[str, str]


def route_tools(
    text: str,
    *,
    has_photo: bool,
) -> list[RoutedToolCall]:
    """Deterministic tool routing before LLM (EN + UK)."""
    calls: list[RoutedToolCall] = []
    lower = text.lower().strip()

    if has_photo:
        calls.append(RoutedToolCall("reverse_image", {}))

    if re.search(
        r"(погод\w*|weather|forecast|temperature|temperatur|температур\w*|градус\w*)",
        lower,
    ):
        calls.append(RoutedToolCall("ha_query", {"query": "weather"}))

    if re.search(
        r"\b(бензин|дизел|палив|fuel|азс|socar|wog|okko|ukrnafta)\b", lower
    ):
        calls.append(RoutedToolCall("ha_query", {"query": "fuel"}))

    if re.search(
        r"\b(курс|долар|dollar|usd|obmenka|cartel|євро|eur)\b", lower
    ):
        topic = "eur" if re.search(r"\b(eur|євро|euro)\b", lower) else "usd"
        calls.append(RoutedToolCall("ha_query", {"query": topic}))

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


def is_ha_factual_query(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(
            r"(курс|долар|dollar|usd|eur|євро|погод|weather|бензин|fuel|азс|"
            r"температур|temperature|градус)",
            lower,
        )
    )

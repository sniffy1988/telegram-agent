from __future__ import annotations

import re

# Primary HA theme: exactly one per message (router elif chain order).
PRIMARY_TOPIC_ORDER = ("all", "pollen", "air", "indoor", "weather")

# Topic detection inside tools_ha (substring / exact query name).
TOOL_TOPIC_ORDER = ("all", "indoor", "pollen", "air", "weather", "fuel", "usd", "eur")

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "all": (
        "all",
        "все датчик",
        "все sensor",
        "все сущност",
        "список датчик",
        "какие датчик",
        "перечисли датчик",
        "all sensor",
        "everything in ha",
    ),
    "pollen": (
        "pollen",
        "ragweed",
        "ambrosia",
        "амброз",
        "пыльц",
        "silam",
    ),
    "air": (
        "air",
        "pm2",
        "pm10",
        "aqi",
        "влажност",
        "humidity",
        "якість повітря",
        "качество воздуха",
        "загряз",
    ),
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
    "fuel": ("fuel", "ukr_fuel", "азс", "бензин", "дизел", "socar", "wog", "okko", "ukrnafta"),
    "usd": ("usd", "dollar", "долар", "cartel", "obmenka"),
    "eur": ("eur", "euro", "євро", "eur/usd"),
}

# Deterministic Telegram replies (no LLM) for these topics on HA success.
FACTUAL_REPLY_TOPICS = frozenset(
    {"pollen", "weather", "indoor", "air", "usd", "eur", "fuel", "all"}
)

ENTITY_ID_RE = re.compile(r"\b([a-z][a-z0-9_]*\.[a-z0-9_]+)\b", re.I)

PRIMARY_ROUTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "all",
        re.compile(
            r"(все\s+датчик|все\s+сущност|список\s+датчик|какие\s+датчик|перечисли\s+датчик|"
            r"all\s+sensors?|list\s+sensors?|everything\s+in\s+ha)",
            re.I,
        ),
    ),
    (
        "pollen",
        re.compile(r"(амброз|ragweed|пыльц|pollen|silam\s+pollen)", re.I),
    ),
    (
        "air",
        re.compile(
            r"(pm2\.?5|pm10|\baqi\b|влажност|humidity|якість\s+повітря|"
            r"качество\s+воздуха|загряз)",
            re.I,
        ),
    ),
    (
        "indoor",
        re.compile(
            r"(комнат\w*|помещен\w*|indoor|inside|в\s+доме|в\s+квартире|внутри)",
            re.I,
        ),
    ),
    (
        "weather",
        re.compile(
            r"(погод\w*|weather|forecast|temperature|temperatur|температур\w*|градус\w*|"
            r"на\s+улице|outdoor)",
            re.I,
        ),
    ),
)

FUEL_ROUTE = re.compile(
    r"\b(бензин|дизел|палив|fuel|азс|socar|wog|okko|ukrnafta)\b", re.I
)
FX_ROUTE = re.compile(r"\b(курс|долар|dollar|usd|obmenka|cartel|євро|eur)\b", re.I)
EUR_HINT = re.compile(r"\b(eur|євро|euro)\b", re.I)

FOLLOWUP_PREFIX = re.compile(r"^(а|и|ну)\s+", re.I)
FOLLOWUP_OUTDOOR = re.compile(r"(на\s+улице|outdoor|снаружи)", re.I)
FOLLOWUP_REPEAT = re.compile(
    r"(сейчас|ещё\s+раз|еще\s+раз|актуальн|повтори)\??$", re.I
)


def resolve_tool_topic(query: str) -> str | None:
    q_lower = query.lower().strip()
    for topic in TOOL_TOPIC_ORDER:
        kws = TOPIC_KEYWORDS[topic]
        if q_lower == topic or any(k in q_lower for k in kws):
            return topic
    return None


def last_ha_topic_from_history(
    history: list[dict[str, str]], *, has_photo: bool = False
) -> str | None:
    """Import route_tools lazily to avoid circular import."""
    from router import route_tools

    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        content = turn.get("content") or ""
        for call in route_tools(content, has_photo=has_photo):
            if call.name == "ha_query":
                q = call.arguments.get("query")
                if isinstance(q, str) and q.strip():
                    return q.strip().lower()
    return None

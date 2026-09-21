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
    "usd": ("usd", "dollar", "долар", "доллар", "obmenka"),
    "eur": ("eur", "euro", "євро", "eur/usd"),
}

# Entity matching in tools_ha (stricter than routing — "cartel" alone is not USD).
USD_ENTITY_MARKERS = ("cartel_usd", "_usd_", ".usd")
EUR_ENTITY_MARKERS = ("cartel_eur", "_eur_", ".eur")

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
USD_HINT = re.compile(
    r"(usd|\bdollar\b|доллар|долар|бакс|cartel_usd|obmenka|"
    r"дол\.?\s*usa|долlar\s*usa)",
    re.I,
)
EUR_HINT = re.compile(r"\b(eur|євро|euro|евро)\b", re.I)
CARTEL_HINT = re.compile(r"\bcartel\b", re.I)
FX_GENERIC = re.compile(r"\bкурс\b", re.I)

HA_FACTUAL_PATTERNS = re.compile(
    r"(курс|долар|доллар|dollar|usd|eur|євро|евро|погод|weather|температур|"
    r"градус|амброз|ragweed|пыльц|pollen|бензин|fuel|азс|pm2|cartel|obmenka)",
    re.I,
)


def message_expects_ha_facts(text: str) -> bool:
    return bool(HA_FACTUAL_PATTERNS.search(text.strip()))


def fx_ha_topics_from_text(lower: str) -> list[str]:
    """0–2 topics: USD and/or EUR (Cartel sensors are separate entity groups)."""
    if ENTITY_ID_RE.fullmatch(lower.strip()):
        return []
    topics: list[str] = []
    if EUR_HINT.search(lower):
        topics.append("eur")
    if USD_HINT.search(lower):
        topics.append("usd")
    if not topics and CARTEL_HINT.search(lower):
        topics.append("usd")
    if not topics and FX_GENERIC.search(lower):
        topics.append("usd")
    return topics


def entity_matches_usd(entity_id: str) -> bool:
    el = entity_id.lower()
    if "eur" in el and "usd" not in el:
        return False
    return any(m in el for m in USD_ENTITY_MARKERS) or (
        "usd" in el and "cartel" in el
    )


def entity_matches_eur(entity_id: str) -> bool:
    el = entity_id.lower()
    if "open_meteo" in el or "european_aqi" in el:
        return False
    if "usd" in el and "eur" not in el:
        return False
    return any(m in el for m in EUR_ENTITY_MARKERS) or (
        "cartel" in el and "_eur" in el
    )

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

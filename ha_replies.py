from __future__ import annotations

from typing import Any


def _state_lines(states: list[dict[str, Any]], *, title: str, footer: str = "") -> str:
    if not states:
        return f"Нет данных: {title}"
    lines = [f"{title}:", ""]
    for st in states:
        if not isinstance(st, dict):
            continue
        name = str(st.get("friendly_name") or st.get("entity_id") or st.get("id") or "?")
        val = st.get("state", st.get("v"))
        unit = st.get("unit")
        suffix = f" {unit}" if unit else ""
        lines.append(f"• {name}: {val}{suffix}")
    if footer:
        lines.extend(["", footer])
    return "\n".join(lines)


def format_ha_reply(topic: str, payload: dict[str, Any]) -> str:
    states = payload.get("states")
    if not isinstance(states, list):
        states = []

    if topic == "pollen":
        return _state_lines(
            states,
            title="Пыльца (Home Assistant)",
            footer=(
                "В HA ragweed = амброзия (не путать с полынью/mugwort — смотрите имя датчика). "
                "0 — низкий уровень, не «датчика нет»."
            ),
        )

    if topic == "weather":
        return _state_lines(states, title="Погода / температура на улице (Home Assistant)")

    if topic == "indoor":
        return _state_lines(
            states,
            title="Температура в помещениях (Home Assistant)",
            footer="Датчики у устройств (очиститель/увлажнитель), не отдельные комнаты.",
        )

    if topic == "air":
        return _state_lines(states, title="Воздух / влажность / PM (Home Assistant)")

    if topic == "usd":
        return _state_lines(states, title="Курс USD (Home Assistant / Cartel)")

    if topic == "eur":
        return _state_lines(states, title="Курс EUR (Home Assistant / Cartel)")

    if topic == "fuel":
        return _state_lines(states, title="Топливо АЗС (Home Assistant)")

    if topic == "all":
        total = payload.get("total")
        truncated = payload.get("truncated")
        n = len(states)
        header = f"Сущности Home Assistant ({n}"
        if truncated and isinstance(total, int):
            header += f" из {total}, список обрезан"
        header += "):"
        lines = [header, ""]
        for st in states[:80]:
            if not isinstance(st, dict):
                continue
            eid = st.get("id") or st.get("entity_id") or "?"
            name = st.get("n") or st.get("friendly_name") or ""
            val = st.get("v", st.get("state"))
            if name:
                lines.append(f"• {eid} — {name}: {val}")
            else:
                lines.append(f"• {eid}: {val}")
        if truncated:
            lines.append("")
            lines.append("Показана часть списка. Полный дамп — через HA или скрипт в README.")
        return "\n".join(lines)

    return _state_lines(states, title="Home Assistant")

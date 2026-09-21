from __future__ import annotations

from ha_topics import (
    fx_ha_topics_from_text,
    message_mentions_fuel,
    resolve_tool_topic,
)


def test_message_mentions_fuel_dp() -> None:
    assert message_mentions_fuel("а сколько стоит ДП?")
    assert message_mentions_fuel("скільки коштує dp на socar?")


def test_message_mentions_fuel_solyara() -> None:
    assert message_mentions_fuel("сколько стоит соляра?")
    assert resolve_tool_topic("соляра на wog") == "fuel"


def test_resolve_tool_topic_fuel() -> None:
    assert resolve_tool_topic("дп") == "fuel"
    assert resolve_tool_topic("fuel") == "fuel"
    assert resolve_tool_topic("а сколько стоит дизель") == "fuel"


def test_fx_not_inferred_when_fuel_mentioned() -> None:
    assert fx_ha_topics_from_text("сколько стоит дп на азс") == []
    assert fx_ha_topics_from_text("курс доллара") == ["usd"]

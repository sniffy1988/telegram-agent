from __future__ import annotations

import pytest

from router import route_tools, route_tools_with_context


def _ha_queries(calls: list) -> list[str]:
    return [c.arguments["query"] for c in calls if c.name == "ha_query"]


@pytest.mark.parametrize(
    ("text", "expected_ha"),
    [
        ("покажи все сущности в HA", ["all"]),
        ("list sensors", ["all"]),
        ("какая амброзия сейчас?", ["pollen"]),
        ("ragweed level", ["pollen"]),
        ("пыльца silam", ["pollen"]),
        ("а в комнатах?", ["indoor"]),
        ("температура в доме", ["indoor"]),
        ("какая температура сейчас?", ["weather"]),
        ("яка погода зараз?", ["weather"]),
        ("какой pm2.5 на улице", ["air"]),
        ("влажность снаружи", ["air"]),
        ("дизель socar", ["fuel"]),
        ("цена на азс", ["fuel"]),
        ("курс доллара cartel", ["usd"]),
        ("cartel usd", ["usd"]),
        ("сколько стоит доллар", ["usd"]),
        ("курс доллара США", ["usd"]),
        ("курс євро", ["eur"]),
        ("погода и курс доллара", ["weather", "usd"]),
        ("привет", []),
        ("знайди новини про Python", []),
        ("sensor.cartel_usd_buy", ["sensor.cartel_usd_buy"]),
    ],
)
def test_route_matrix(text: str, expected_ha: list[str]) -> None:
    calls = route_tools(text, has_photo=False)
    assert _ha_queries(calls) == expected_ha
    if "знайди" in text:
        assert any(c.name == "web_search" for c in calls)


def test_route_weather_and_usd() -> None:
    calls = route_tools("яка погода зараз?", has_photo=False)
    assert "weather" in _ha_queries(calls)
    calls2 = route_tools("какой сейчас курс доллара?", has_photo=False)
    assert "usd" in _ha_queries(calls2)


def test_route_search_and_photo() -> None:
    calls = route_tools("знайди новини про Python", has_photo=False)
    assert any(c.name == "web_search" for c in calls)
    calls2 = route_tools("", has_photo=True)
    assert any(c.name == "reverse_image" for c in calls2)


def test_pollen_not_polyn() -> None:
    calls = route_tools("сколько полыни", has_photo=False)
    assert "pollen" not in _ha_queries(calls)


def test_contextual_repeat_weather() -> None:
    history = [
        {"role": "user", "content": "какая температура на улице?"},
        {"role": "assistant", "content": "23 C"},
    ]
    calls = route_tools_with_context("а сейчас?", has_photo=False, history=history)
    assert _ha_queries(calls) == ["weather"]


def test_contextual_outdoor() -> None:
    history = [{"role": "user", "content": "привет"}]
    calls = route_tools_with_context("а на улице?", has_photo=False, history=history)
    assert _ha_queries(calls) == ["weather"]


def test_contextual_no_history() -> None:
    calls = route_tools_with_context("а сейчас?", has_photo=False, history=[])
    assert _ha_queries(calls) == []

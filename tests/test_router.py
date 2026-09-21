from __future__ import annotations

from router import is_ha_factual_query, route_tools


def test_route_weather_and_usd() -> None:
    calls = route_tools("яка погода зараз?", has_photo=False)
    assert any(c.name == "ha_query" and c.arguments["query"] == "weather" for c in calls)

    calls2 = route_tools("какой сейчас курс доллара?", has_photo=False)
    assert any(c.name == "ha_query" and c.arguments["query"] == "usd" for c in calls2)


def test_route_search_and_photo() -> None:
    calls = route_tools("знайди новини про Python", has_photo=False)
    assert any(c.name == "web_search" for c in calls)
    calls2 = route_tools("", has_photo=True)
    assert any(c.name == "reverse_image" for c in calls2)


def test_is_ha_factual() -> None:
    assert is_ha_factual_query("курс доллара")

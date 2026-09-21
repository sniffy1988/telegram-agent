from __future__ import annotations

from ha_topics import entity_matches_eur, entity_matches_usd, fx_ha_topics_from_text


def test_fx_topics_dollar_russian() -> None:
    assert fx_ha_topics_from_text("сколько стоит доллар") == ["usd"]


def test_fx_topics_both_currencies() -> None:
    topics = fx_ha_topics_from_text("курс доллара и євро")
    assert topics == ["eur", "usd"]


def test_entity_usd_not_eur() -> None:
    assert entity_matches_usd("sensor.cartel_usd_buy")
    assert not entity_matches_usd("sensor.cartel_eur_buy")
    assert entity_matches_eur("sensor.cartel_eur_buy")

from __future__ import annotations

from ha_control_intent import parse_ha_control_intent


def test_parse_turn_on_russian() -> None:
    assert parse_ha_control_intent("включи ночник") == ("turn_on", "ночник")


def test_parse_turn_off() -> None:
    assert parse_ha_control_intent("выключи switch.kitchen") == (
        "turn_off",
        "switch.kitchen",
    )


def test_parse_not_control() -> None:
    assert parse_ha_control_intent("какая температура?") is None

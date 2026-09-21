from __future__ import annotations

from telegram_utils import StatusStage, split_message, stage_for_tool


def test_split_message() -> None:
    text = "a" * 5000
    parts = split_message(text, 4096)
    assert len(parts) >= 2
    assert sum(len(p) for p in parts) >= 5000


def test_stage_for_tool() -> None:
    assert stage_for_tool("ha_query") == StatusStage.HA
    assert stage_for_tool("web_search") == StatusStage.WEB

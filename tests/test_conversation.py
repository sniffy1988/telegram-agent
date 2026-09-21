from __future__ import annotations

from conversation import append_turn, clear_history, get_history, trim_history


def test_history_trimming() -> None:
    chat_id = 42
    clear_history(chat_id)
    for i in range(10):
        append_turn(chat_id, f"u{i}", f"a{i}", max_messages=6)
    hist = get_history(chat_id)
    assert len(hist) == 6
    assert hist[0]["content"] == "u7"


def test_clear_history() -> None:
    chat_id = 7
    append_turn(chat_id, "hi", "hello", max_messages=6)
    clear_history(chat_id)
    assert get_history(chat_id) == []


def test_trim_helper() -> None:
    msgs = [{"role": "user", "content": str(i)} for i in range(8)]
    trimmed = trim_history(msgs, 6)
    assert len(trimmed) == 6

from __future__ import annotations

from typing import Literal

ChatRole = Literal["user", "assistant"]
ChatTurn = dict[str, str]

_histories: dict[int, list[ChatTurn]] = {}


def get_history(chat_id: int) -> list[ChatTurn]:
    return list(_histories.get(chat_id, []))


def append_turn(
    chat_id: int,
    user_text: str,
    assistant_text: str,
    *,
    max_messages: int,
) -> None:
    history = _histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    if len(history) > max_messages:
        _histories[chat_id] = history[-max_messages:]


def clear_history(chat_id: int) -> None:
    _histories.pop(chat_id, None)


def trim_history(messages: list[ChatTurn], limit: int) -> list[ChatTurn]:
    if len(messages) <= limit:
        return list(messages)
    return list(messages[-limit:])

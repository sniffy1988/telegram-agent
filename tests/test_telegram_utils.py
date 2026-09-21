from __future__ import annotations

from unittest.mock import MagicMock

from telegram import Chat, Message, ReplyParameters, User

from telegram_utils import reply_send_kwargs, split_message, stage_for_tool, StatusStage


def test_split_message() -> None:
    text = "a" * 5000
    parts = split_message(text, 4096)
    assert len(parts) >= 2
    assert sum(len(p) for p in parts) >= 5000


def test_stage_for_tool() -> None:
    assert stage_for_tool("ha_query") == StatusStage.HA
    assert stage_for_tool("web_search") == StatusStage.WEB


def test_reply_send_kwargs_includes_thread() -> None:
    chat = Chat(id=1, type="supergroup")
    user = User(id=2, is_bot=False, first_name="U")
    msg = Message(
        message_id=99,
        date=None,
        chat=chat,
        from_user=user,
        message_thread_id=42,
    )
    kwargs = reply_send_kwargs(msg)
    assert isinstance(kwargs["reply_parameters"], ReplyParameters)
    assert kwargs["reply_parameters"].message_id == 99
    assert kwargs["message_thread_id"] == 42

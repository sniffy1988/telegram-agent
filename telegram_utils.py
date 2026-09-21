from __future__ import annotations

import logging
from enum import Enum

from telegram import Message
from telegram.constants import ChatAction
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE = 4096


class StatusStage(str, Enum):
    QUEUED = "Queued… another request is running."
    GENERATING = "Generating…"
    WEB = "Searching the web…"
    HA = "Looking up Home Assistant…"
    IMAGES = "Finding images…"
    REVERSE = "Reverse-searching photo…"


def split_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return chunks


async def safe_edit_status(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except BadRequest as exc:
        logger.debug("Could not edit status message: %s", exc)


async def send_typing(message: Message) -> None:
    if message.chat:
        await message.chat.send_action(ChatAction.TYPING)


async def send_upload_photo(message: Message) -> None:
    if message.chat:
        await message.chat.send_action(ChatAction.UPLOAD_PHOTO)


def stage_for_tool(tool_name: str) -> StatusStage:
    if tool_name == "ha_query":
        return StatusStage.HA
    if tool_name == "web_search":
        return StatusStage.WEB
    if tool_name == "image_search":
        return StatusStage.IMAGES
    if tool_name == "reverse_image":
        return StatusStage.REVERSE
    return StatusStage.GENERATING

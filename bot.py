from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent import Agent
from config import load_settings
from conversation import clear_history
from memory import MemoryStore
from ollama_client import OllamaClient, _model_lock
from telegram_utils import (
    StatusStage,
    safe_edit_status,
    send_typing,
    send_upload_photo,
    split_message,
)
from tools import ToolRegistry
from tools_ha import HomeAssistantTool
from tools_image import ReverseImageTool
from tools_web import ImageSearchTool, WebSearchTool, download_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

FORGET_CONFIRM_PREFIX = "forget:"


def _allowed_chat(update: Update, allowed: frozenset[int]) -> bool:
    if not allowed:
        return True
    chat = update.effective_chat
    return chat is not None and chat.id in allowed


async def _reply_text(
    update: Update,
    text: str,
    *,
    reply_to: int | None = None,
) -> None:
    if not update.effective_chat:
        return
    msg_id = reply_to
    if msg_id is None and update.effective_message:
        msg_id = update.effective_message.message_id
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        await update.effective_chat.send_message(
            chunk,
            reply_to_message_id=msg_id if i == 0 else msg_id,
        )


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not _allowed_chat(
        update, context.bot_data["allowed_chat_ids"]
    ):
        return
    text = (
        "Привет! Я familyai — локальный домашний ассистент.\n"
        "Помогаю с вопросами, памятью, Home Assistant (только чтение), "
        "поиском в интернете и картинками.\n"
        "Если отправите фото для обратного поиска, изображение может быть "
        "передано внешнему поисковому сервису (best-effort).\n"
        "Команды: /clear, /memory, /forget"
    )
    await update.effective_message.reply_text(text)


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        return
    chat_id = update.effective_chat.id
    clear_history(chat_id)
    memory: MemoryStore = context.bot_data["memory"]
    memory.clear_customer(chat_id)
    await update.effective_message.reply_text(
        "Память для этого чата очищена (история и долгосрочные факты)."
    )


async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        return
    memory: MemoryStore = context.bot_data["memory"]
    summary = memory.format_summary(update.effective_chat.id)
    await update.effective_message.reply_text(summary)


async def forget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Yes", callback_data=f"{FORGET_CONFIRM_PREFIX}yes"),
                InlineKeyboardButton("No", callback_data=f"{FORGET_CONFIRM_PREFIX}no"),
            ]
        ]
    )
    await update.effective_message.reply_text(
        "Удалить всю долгосрочную память и историю для этого чата?",
        reply_markup=keyboard,
    )


async def forget_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        await query.answer()
        return
    await query.answer()
    if query.data == f"{FORGET_CONFIRM_PREFIX}yes":
        chat_id = query.message.chat_id if query.message else None
        if chat_id is not None:
            clear_history(chat_id)
            memory: MemoryStore = context.bot_data["memory"]
            memory.clear_customer(chat_id)
        await query.edit_message_text("Память удалена.")
    else:
        await query.edit_message_text("Отменено.")


async def _process_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_text: str,
    has_photo: bool,
    photo_path: str | None,
    caption: str,
) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        return

    chat_id = update.effective_chat.id
    reply_to = update.effective_message.message_id
    logger.info("[telegram] chat_id=%s received message", chat_id)

    status_msg = await update.effective_message.reply_text(StatusStage.GENERATING.value)

    async def on_status(stage: StatusStage) -> None:
        if stage == StatusStage.QUEUED:
            if _model_lock.locked():
                await safe_edit_status(status_msg, StatusStage.QUEUED.value)
        else:
            await safe_edit_status(status_msg, stage.value)
        if stage == StatusStage.GENERATING:
            await send_typing(update.effective_message)
        if stage in (
            StatusStage.IMAGES,
            StatusStage.REVERSE,
        ):
            await send_upload_photo(update.effective_message)

    typing_task: asyncio.Task | None = None

    async def typing_loop() -> None:
        while True:
            await send_typing(update.effective_message)
            await asyncio.sleep(4)

    typing_task = asyncio.create_task(typing_loop())

    agent: Agent = context.bot_data["agent"]
    settings = context.bot_data["settings"]

    try:
        if _model_lock.locked():
            await safe_edit_status(status_msg, StatusStage.QUEUED.value)

        result = await agent.handle(
            chat_id,
            user_text,
            has_photo=has_photo,
            photo_path=photo_path,
            caption=caption,
            on_status=on_status,
        )

        chunks = split_message(result.text)
        await safe_edit_status(status_msg, chunks[0])
        for extra in chunks[1:]:
            await update.effective_chat.send_message(
                extra, reply_to_message_id=reply_to
            )

        for photo in result.photos[: settings.max_images]:
            data = await download_image(photo.image_url)
            if not data:
                continue
            await send_upload_photo(update.effective_message)
            cap = photo.caption[:1024] if photo.caption else None
            await update.effective_chat.send_photo(
                photo=data,
                caption=cap,
                reply_to_message_id=reply_to,
            )

        logger.info(
            "[telegram] chat_id=%s response sent chars=%s photos=%s",
            chat_id,
            len(result.text),
            len(result.photos),
        )
    except Exception:
        logger.exception("Unhandled error processing message")
        await safe_edit_status(
            status_msg, "Произошла ошибка при обработке сообщения."
        )
    finally:
        if typing_task:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
        if photo_path:
            try:
                Path(photo_path).unlink(missing_ok=True)
            except OSError:
                pass


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.text:
        return
    await _process_message(
        update,
        context,
        user_text=update.effective_message.text,
        has_photo=False,
        photo_path=None,
        caption="",
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.photo:
        return
    photo = update.effective_message.photo[-1]
    file = await photo.get_file()
    suffix = ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    await file.download_to_drive(tmp.name)
    caption = update.effective_message.caption or ""
    await _process_message(
        update,
        context,
        user_text=caption,
        has_photo=True,
        photo_path=tmp.name,
        caption=caption,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning("Update %s caused error %s", update, context.error)


def build_registry(settings) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(HomeAssistantTool(settings.home_assistant_url, settings.home_assistant_token))
    reg.register(WebSearchTool(settings.max_search_results))
    reg.register(ImageSearchTool(settings.max_images))
    reg.register(ReverseImageTool())
    return reg


def main() -> None:
    settings = load_settings()
    memory = MemoryStore(settings.memory_path)
    ollama = OllamaClient(
        settings.ollama_url, settings.ollama_model, settings.ollama_timeout
    )
    registry = build_registry(settings)
    agent = Agent(settings, memory, ollama, registry)

    async def post_init(application: Application) -> None:
        await ollama.open()

    async def post_shutdown(application: Application) -> None:
        await ollama.close()

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["memory"] = memory
    app.bot_data["agent"] = agent
    app.bot_data["ollama"] = ollama
    app.bot_data["allowed_chat_ids"] = settings.telegram_allowed_chat_ids

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("forget", forget_cmd))
    app.add_handler(CallbackQueryHandler(forget_callback, pattern=f"^{FORGET_CONFIRM_PREFIX}"))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()

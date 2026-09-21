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
from healthcheck import log_startup_connectivity
from logging_config import configure_logging
from conversation import clear_history
from memory import MemoryStore
from ollama_client import OllamaClient, _model_lock
from telegram_utils import (
    StatusStage,
    finalize_status_reply,
    reply_send_kwargs,
    safe_edit_status,
    send_typing,
    send_upload_photo,
    split_message,
)
from tools import ToolRegistry
from ha_control import HomeAssistantControlClient
from ha_control_catalog import catalog_allowlist, format_devices_help
from tools_ha import HomeAssistantTool
from tools_ha_control import HomeAssistantControlTool
from tools_image import ReverseImageTool
from tools_web import ImageSearchTool, WebSearchTool, download_image

logger = logging.getLogger(__name__)

FORGET_CONFIRM_PREFIX = "forget:"
HA_CONTROL_CONFIRM_PREFIX = "ha_ctrl:"


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
        "Команды: /clear, /memory, /forget, /chatid"
    )
    await update.effective_message.reply_text(text)


async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Always available (even before TELEGRAM_ALLOWED_CHAT_IDS is set)."""
    if not update.effective_message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    lines = [
        f"chat_id: {chat.id}",
        f"chat_type: {chat.type}",
    ]
    if user:
        lines.append(f"user_id: {user.id}")
    lines.append(
        "Для .env: TELEGRAM_ALLOWED_CHAT_IDS="
        + (str(user.id) if user else str(chat.id))
    )
    await update.effective_message.reply_text("\n".join(lines))


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


async def devices_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        return
    settings = context.bot_data["settings"]
    if not settings.ha_control_enabled:
        await update.effective_message.reply_text(
            "Управление выключено. В .env: HA_CONTROL_ENABLED=1 и перезапуск."
        )
        return
    await update.effective_message.reply_text(
        format_devices_help(settings.ha_control_catalog_path)
    )


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


async def ha_control_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not _allowed_chat(update, context.bot_data["allowed_chat_ids"]):
        await query.answer()
        return
    await query.answer()
    chat_id = query.message.chat_id if query.message else None
    if chat_id is None:
        return
    pending_map = context.bot_data.get("pending_ha_control") or {}
    pending = pending_map.pop(chat_id, None)
    context.bot_data["pending_ha_control"] = pending_map

    if query.data == f"{HA_CONTROL_CONFIRM_PREFIX}no":
        await query.edit_message_text("Управление отменено.")
        return
    if query.data != f"{HA_CONTROL_CONFIRM_PREFIX}yes":
        return
    if pending is None:
        await query.edit_message_text("Нет ожидающего действия (устарело).")
        return
    tool = context.bot_data.get("ha_control_tool")
    if tool is None:
        await query.edit_message_text("Управление HA отключено на сервере.")
        return
    result = await tool.execute(
        {},
        {"confirmed_apply": True, "pending_ha_control": pending},
    )
    if result.get("ok"):
        await query.edit_message_text(
            f"Готово: {pending.service} — {pending.friendly_name}."
        )
    else:
        await query.edit_message_text(
            "Не удалось выполнить команду в Home Assistant."
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
    user_message = update.effective_message
    preview = (user_text or caption or "(photo)")[:120]
    logger.info(
        "[telegram] chat_id=%s message_id=%s photo=%s text=%r",
        chat_id,
        user_message.message_id,
        has_photo,
        preview,
    )

    status_msg = await user_message.get_bot().send_message(
        chat_id=user_message.chat_id,
        text=StatusStage.GENERATING.value,
        **reply_send_kwargs(user_message),
    )

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
        confirm_keyboard = None
        if result.pending_ha_control is not None:
            pending_map = context.bot_data.setdefault("pending_ha_control", {})
            pending_map[chat_id] = result.pending_ha_control
            confirm_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Да",
                            callback_data=f"{HA_CONTROL_CONFIRM_PREFIX}yes",
                        ),
                        InlineKeyboardButton(
                            "Нет",
                            callback_data=f"{HA_CONTROL_CONFIRM_PREFIX}no",
                        ),
                    ]
                ]
            )
        if confirm_keyboard:
            try:
                await status_msg.edit_text(chunks[0], reply_markup=confirm_keyboard)
            except Exception:
                await finalize_status_reply(status_msg, user_message, chunks[0])
                await user_message.get_bot().send_message(
                    chat_id=user_message.chat_id,
                    text="Подтвердите действие:",
                    reply_markup=confirm_keyboard,
                    **reply_send_kwargs(user_message),
                )
        else:
            await finalize_status_reply(status_msg, user_message, chunks[0])
        bot = user_message.get_bot()
        for extra in chunks[1:]:
            await bot.send_message(
                chat_id=user_message.chat_id,
                text=extra,
                **reply_send_kwargs(user_message),
            )

        for photo in result.photos[: settings.max_images]:
            data = await download_image(photo.image_url)
            if not data:
                continue
            await send_upload_photo(user_message)
            cap = photo.caption[:1024] if photo.caption else None
            await bot.send_photo(
                chat_id=user_message.chat_id,
                photo=data,
                caption=cap,
                **reply_send_kwargs(user_message),
            )

        logger.info(
            "[telegram] chat_id=%s response sent chars=%s photos=%s",
            chat_id,
            len(result.text),
            len(result.photos),
        )
    except Exception:
        logger.exception("Unhandled error processing message")
        await finalize_status_reply(
            status_msg,
            user_message,
            "Произошла ошибка при обработке сообщения.",
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
    reg.register(
        HomeAssistantTool(
            settings.home_assistant_url,
            settings.home_assistant_token,
            all_entities_limit=settings.ha_all_entities_limit,
            topic_match_limit=settings.ha_topic_match_limit,
        )
    )
    if settings.ha_control_enabled:
        client = HomeAssistantControlClient(
            settings.home_assistant_url,
            settings.home_assistant_token,
            allowed_domains=settings.ha_control_domains,
        )
        reg.register(HomeAssistantControlTool(client))
    reg.register(WebSearchTool(settings.max_search_results))
    reg.register(ImageSearchTool(settings.max_images))
    reg.register(ReverseImageTool())
    return reg


def main() -> None:
    configure_logging()
    settings = load_settings()
    logger.info(
        "[startup] ollama=%s model=%s ha=%s ha_token=%s ha_control=%s memory=%s",
        settings.ollama_url,
        settings.ollama_model,
        settings.home_assistant_url,
        "set" if settings.home_assistant_token else "missing",
        settings.ha_control_enabled,
        settings.memory_path,
    )
    if settings.ha_control_enabled and not settings.telegram_allowed_chat_ids:
        logger.warning(
            "[startup] HA_CONTROL_ENABLED but TELEGRAM_ALLOWED_CHAT_IDS is empty — "
            "restrict chat IDs before enabling control in production"
        )
    if settings.ha_control_enabled:
        cat_path = settings.ha_control_catalog_path
        allow_n = len(catalog_allowlist(cat_path))
        if allow_n:
            logger.info(
                "[startup] ha_control catalog=%s devices=%s",
                cat_path,
                allow_n,
            )
        elif cat_path.is_file():
            logger.warning("[startup] ha_control catalog empty: %s", cat_path)
        else:
            logger.warning(
                "[startup] ha_control catalog missing: %s (aliases disabled)",
                cat_path,
            )
    memory = MemoryStore(settings.memory_path)
    ollama = OllamaClient(
        settings.ollama_url, settings.ollama_model, settings.ollama_timeout
    )
    registry = build_registry(settings)
    agent = Agent(settings, memory, ollama, registry)

    async def post_init(application: Application) -> None:
        await ollama.open()
        await log_startup_connectivity(settings)

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
    ha_control_tool = registry.get("ha_control")
    if ha_control_tool is not None:
        app.bot_data["ha_control_tool"] = ha_control_tool

    app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("forget", forget_cmd))
    app.add_handler(CommandHandler("devices", devices_cmd))
    app.add_handler(CallbackQueryHandler(forget_callback, pattern=f"^{FORGET_CONFIRM_PREFIX}"))
    app.add_handler(
        CallbackQueryHandler(
            ha_control_callback, pattern=f"^{HA_CONTROL_CONFIRM_PREFIX}"
        )
    )
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()

"""Bot API MAX — официальный REST-клиент для ботов.

Отдельный слой от userbot: :class:`Bot` работает от лица бота через
документированный REST ``botapi.max.ru`` (токен бота), тогда как остальная
библиотека — от лица аккаунта через внутренний протокол.

    from maxion.bot import Bot, filters

    bot = Bot("<token>")

    @bot.on_message(filters.command("start"))
    async def start(bot, update):
        await update.reply("Привет! Я на maxion.")

    @bot.on_callback(filters.payload("yes"))
    async def yes(bot, update):
        await update.answer("Принято")

    bot.run()
"""

from __future__ import annotations

from . import filters
from .client import Bot, BotApiError
from .types import BotCommand, Chat, Message, Recipient, User
from .updates import (
    BotAdded,
    BotStarted,
    MessageCallback,
    MessageCreated,
    Update,
    parse_update,
)

__all__ = [
    "Bot",
    "BotApiError",
    "filters",
    "User",
    "Chat",
    "Message",
    "Recipient",
    "BotCommand",
    "Update",
    "MessageCreated",
    "MessageCallback",
    "BotAdded",
    "BotStarted",
    "parse_update",
]

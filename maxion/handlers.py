"""Обработчики событий.

Каждый обработчик знает, какое событие ловит, и какой фильтр применить.
Колбэк вызывается как ``callback(client, update)``.
"""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from .filters import Filter

Callback = Callable[..., Awaitable[Any]]


class Handler:
    """Базовый обработчик."""

    #: Имя события низкоуровневого роутера.
    event: str = "raw"

    def __init__(self, callback: Callback, filters: Filter | None = None):
        if not inspect.iscoroutinefunction(callback):
            raise TypeError("Обработчик должен быть async-функцией")
        self.callback = callback
        self.filters = filters

    async def check(self, client, update) -> bool:
        if self.filters is None:
            return True
        return await self.filters(client, update)

    def __repr__(self) -> str:
        name = getattr(self.callback, "__name__", "callback")
        return f"<{type(self).__name__} {name} filters={self.filters}>"


class MessageHandler(Handler):
    """Новое сообщение."""

    event = "message"


class EditedMessageHandler(Handler):
    """Изменённое сообщение."""

    event = "edited_message"


class DeletedMessagesHandler(Handler):
    """Удалённые сообщения."""

    event = "message_deleted"


class ChatMemberUpdatedHandler(Handler):
    """Изменения в чате: состав участников, настройки."""

    event = "chat"


class UserStatusHandler(Handler):
    """Пользователь появился в сети или ушёл."""

    event = "presence"


class MessageReactionHandler(Handler):
    """Реакции на сообщении изменились."""

    event = "reactions"


class CallbackQueryHandler(Handler):
    """Ответ на нажатие inline-кнопки бота."""

    event = "callback"


class RawUpdateHandler(Handler):
    """Любой входящий кадр, включая неизвестные опкоды."""

    event = "raw"


__all__ = [
    "Handler",
    "MessageHandler",
    "EditedMessageHandler",
    "DeletedMessagesHandler",
    "ChatMemberUpdatedHandler",
    "UserStatusHandler",
    "MessageReactionHandler",
    "CallbackQueryHandler",
    "RawUpdateHandler",
]

"""События Bot API MAX: разбор Update-объектов.

Каждый update от сервера — словарь с полем ``update_type``. Здесь они
оборачиваются в типизированные события с колбэком ``(bot, update)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import Message, User

if TYPE_CHECKING:  # pragma: no cover
    from .client import Bot


class Update:
    """Базовое событие Bot API."""

    #: имя для роутера (см. :class:`~maxion.bot.dispatcher.Dispatcher`)
    event: str = "raw"

    __slots__ = ("bot", "raw")

    def __init__(self, bot: "Bot", raw: dict[str, Any]):
        self.bot = bot
        self.raw = raw

    @property
    def update_type(self) -> str | None:
        return self.raw.get("update_type")

    @property
    def timestamp(self) -> Any:
        return self.raw.get("timestamp")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.update_type}>"


class MessageCreated(Update):
    """message_created — новое сообщение боту."""

    event = "message"

    @property
    def message(self) -> Message:
        return Message(self.raw.get("message") or {}, self.bot)

    @property
    def text(self) -> str:
        return self.message.text

    @property
    def chat_id(self) -> int | None:
        return self.message.chat_id

    async def reply(self, text: str, **kwargs) -> Message:
        return await self.message.reply(text, **kwargs)

    async def answer(self, text: str, **kwargs) -> Message:
        return await self.message.answer(text, **kwargs)


class MessageEdited(Update):
    """message_edited."""

    event = "edited_message"

    @property
    def message(self) -> Message:
        return Message(self.raw.get("message") or {}, self.bot)


class MessageRemoved(Update):
    """message_removed."""

    event = "removed_message"

    @property
    def message_id(self) -> str | None:
        return self.raw.get("message_id")

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None


class MessageCallback(Update):
    """message_callback — нажата inline-кнопка."""

    event = "callback"

    @property
    def callback_id(self) -> str | None:
        cb = self.raw.get("callback") or {}
        return cb.get("callback_id")

    @property
    def payload(self) -> str | None:
        cb = self.raw.get("callback") or {}
        return cb.get("payload")

    @property
    def user(self) -> User | None:
        cb = self.raw.get("callback") or {}
        raw = cb.get("user")
        return User(raw, self.bot) if isinstance(raw, dict) else None

    @property
    def message(self) -> Message | None:
        raw = self.raw.get("message")
        return Message(raw, self.bot) if isinstance(raw, dict) else None

    async def answer(
        self, text: str | None = None, *, notification: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Отвечает на нажатие кнопки (POST /answers)."""
        return await self.bot.answer_callback(
            self.callback_id, text=text, notification=notification, **kwargs
        )


class BotAdded(Update):
    """bot_added — бота добавили в чат."""

    event = "bot_added"

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def user(self) -> User | None:
        raw = self.raw.get("user")
        return User(raw, self.bot) if isinstance(raw, dict) else None


class BotRemoved(Update):
    """bot_removed — бота убрали из чата."""

    event = "bot_removed"

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None


class BotStarted(Update):
    """bot_started — пользователь нажал «Начать»."""

    event = "bot_started"

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def user(self) -> User | None:
        raw = self.raw.get("user")
        return User(raw, self.bot) if isinstance(raw, dict) else None

    async def answer(self, text: str, **kwargs) -> Message:
        return await self.bot.send_message(text, chat_id=self.chat_id, **kwargs)


class UserAdded(Update):
    """user_added — участник добавлен в чат."""

    event = "user_added"

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def user(self) -> User | None:
        raw = self.raw.get("user")
        return User(raw, self.bot) if isinstance(raw, dict) else None


class UserRemoved(Update):
    """user_removed — участник покинул чат."""

    event = "user_removed"

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def user(self) -> User | None:
        raw = self.raw.get("user")
        return User(raw, self.bot) if isinstance(raw, dict) else None


class ChatTitleChanged(Update):
    """chat_title_changed."""

    event = "chat_title_changed"

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def title(self) -> str | None:
        return self.raw.get("title")


class MessageChatCreated(Update):
    """message_chat_created — из сообщения создан чат."""

    event = "chat_created"


UPDATE_CLASSES: dict[str, type[Update]] = {
    "message_created": MessageCreated,
    "message_edited": MessageEdited,
    "message_removed": MessageRemoved,
    "message_callback": MessageCallback,
    "bot_added": BotAdded,
    "bot_removed": BotRemoved,
    "bot_started": BotStarted,
    "user_added": UserAdded,
    "user_removed": UserRemoved,
    "chat_title_changed": ChatTitleChanged,
    "message_chat_created": MessageChatCreated,
}


def parse_update(bot: "Bot", raw: dict[str, Any]) -> Update:
    """Оборачивает сырой update в подходящий класс."""
    cls = UPDATE_CLASSES.get(str(raw.get("update_type")), Update)
    return cls(bot, raw)


__all__ = [
    "Update",
    "MessageCreated",
    "MessageEdited",
    "MessageRemoved",
    "MessageCallback",
    "BotAdded",
    "BotRemoved",
    "BotStarted",
    "UserAdded",
    "UserRemoved",
    "ChatTitleChanged",
    "MessageChatCreated",
    "UPDATE_CLASSES",
    "parse_update",
]
